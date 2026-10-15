import json
import urllib.parse
import datetime
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import ApprovalRequest, ApprovalStatus, Post, ActivityLog
from ..database.crud import log_activity
from ..services.approval_service import ApprovalService
from ..services.slack_service import SlackService, get_slack_signing_secret
from ..config import settings

logger = logging.getLogger("SlackRouter")

router = APIRouter(prefix="/slack", tags=["Slack Integration"])


@router.post("/interactions")
async def handle_slack_interaction(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handles incoming interactive button callbacks from Slack Block Kit messages.
    Enforces HMAC-SHA256 signature verification over raw body bytes and 300s timestamp replay protection.
    Provides idempotent approval/rejection handling and in-place message updates.
    """
    raw_body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")

    # 1. Header Existence Validation
    if not timestamp or not signature:
        logger.warning("Slack interaction rejected: missing X-Slack-Request-Timestamp or X-Slack-Signature header.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required Slack signature headers (X-Slack-Request-Timestamp or X-Slack-Signature)."
        )

    # 2. Signing Secret Verification
    signing_secret = get_slack_signing_secret()
    if not signing_secret:
        logger.error("Slack interaction rejected: SLACK_SIGNING_SECRET is not configured on the server.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Slack signing secret is not configured on the server."
        )

    # 3. Timestamp Replay Window Check (300 seconds)
    try:
        req_ts = float(timestamp)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Slack-Request-Timestamp header format."
        )

    current_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    if abs(current_ts - req_ts) > SlackService.REPLAY_WINDOW_SECONDS:
        logger.warning(f"Slack interaction rejected: replay attack protection triggered. Skew={abs(current_ts - req_ts):.1f}s")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Slack request timestamp is stale (exceeds {SlackService.REPLAY_WINDOW_SECONDS}s replay protection window)."
        )

    # 4. HMAC-SHA256 Signature Verification
    if not SlackService.verify_slack_signature(signing_secret, raw_body, timestamp, signature):
        logger.warning("Slack interaction rejected: HMAC-SHA256 signature mismatch.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Slack request signature."
        )

    # 5. Form Payload Parsing
    body_text = raw_body.decode("utf-8", errors="replace")
    parsed_form = urllib.parse.parse_qs(body_text)

    if "payload" in parsed_form:
        try:
            payload_data = json.loads(parsed_form["payload"][0])
        except Exception as e:
            logger.error(f"Malformed JSON in Slack payload: {e}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON in Slack payload.")
    else:
        try:
            payload_data = json.loads(body_text)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing or malformed payload in Slack interaction.")

    actions = payload_data.get("actions", [])
    if not actions:
        return JSONResponse({"status": "no_actions_found"})

    action = actions[0]
    action_id = action.get("action_id")
    value = action.get("value")

    try:
        approval_id = int(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid approval ID value in action: {value}")

    # 6. Fetch Approval Request & Post
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Approval request #{approval_id} not found.")

    post = db.query(Post).filter(Post.id == approval.post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Associated post #{approval.post_id} not found.")

    user = payload_data.get("user", {})
    username = user.get("username") or user.get("name") or user.get("id") or "Slack User"
    reviewer_name = f"Slack: @{username}"
    response_url = payload_data.get("response_url")

    # 7. Idempotent Action Handling
    if action_id == "approve_post":
        if approval.status == ApprovalStatus.PENDING.value:
            ApprovalService.approve_post(
                db=db,
                approval_id=approval_id,
                reviewer=reviewer_name,
                review_notes="Approved via Slack interactive card."
            )
            log_activity(
                db=db,
                action="SLACK_INTERACTION_PROCESSED",
                details=f"Slack user @{username} approved Post #{post.id}.",
                post_id=post.id,
                actor=reviewer_name
            )
            db.commit()
            logger.info(f"Post #{post.id} successfully APPROVED via Slack by @{username}.")
        else:
            # Duplicate / already resolved action -> idempotent no-op
            log_activity(
                db=db,
                action="SLACK_INTERACTION_IDEMPOTENT_IGNORED",
                details=f"Duplicate Slack approval ignored for Post #{post.id}. Current status: {approval.status}.",
                post_id=post.id,
                actor=reviewer_name
            )
            db.commit()
            logger.info(f"Duplicate Slack approval ignored for Post #{post.id} (already {approval.status}).")

    elif action_id == "reject_post":
        if approval.status == ApprovalStatus.PENDING.value:
            reason = action.get("reason") or "Rejected by human reviewer via Slack interactive card."
            ApprovalService.reject_post(
                db=db,
                approval_id=approval_id,
                rejection_reason=reason,
                reviewer=reviewer_name,
                review_notes="Rejected via Slack interactive card."
            )
            log_activity(
                db=db,
                action="SLACK_INTERACTION_PROCESSED",
                details=f"Slack user @{username} rejected Post #{post.id}. Reason: {reason}",
                post_id=post.id,
                actor=reviewer_name
            )
            db.commit()
            logger.info(f"Post #{post.id} successfully REJECTED via Slack by @{username}.")
        else:
            # Duplicate / already resolved action -> idempotent no-op
            log_activity(
                db=db,
                action="SLACK_INTERACTION_IDEMPOTENT_IGNORED",
                details=f"Duplicate Slack rejection ignored for Post #{post.id}. Current status: {approval.status}.",
                post_id=post.id,
                actor=reviewer_name
            )
            db.commit()
            logger.info(f"Duplicate Slack rejection ignored for Post #{post.id} (already {approval.status}).")
    else:
        logger.warning(f"Unrecognized Slack action_id: {action_id}")
        return JSONResponse({"status": "unrecognized_action", "action_id": action_id})

    # 8. Refresh database records & build resolved Block Kit message
    db.refresh(approval)
    db.refresh(post)

    resolved_blocks = SlackService.build_resolved_blocks(
        post=post,
        approval=approval,
        action=approval.status,
        reviewer=approval.reviewer or reviewer_name,
        reason=approval.rejection_reason
    )
    resolved_text = f"Post #{post.id} {approval.status} by {approval.reviewer or reviewer_name}."

    # 9. Asynchronous In-Place Update via response_url if available
    if response_url:
        SlackService.update_slack_message(
            response_url=response_url,
            blocks=resolved_blocks,
            text=resolved_text
        )

    # 10. Synchronous response replacing original message in Slack client
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "response_type": "in_channel",
            "replace_original": True,
            "text": resolved_text,
            "blocks": resolved_blocks
        }
    )


@router.post("/dispatch/{approval_id}")
def dispatch_slack_approval(
    approval_id: int,
    db: Session = Depends(get_db)
):
    """Manually dispatches or re-dispatches a Slack interactive approval card for a post."""
    return SlackService.dispatch_approval_card(db=db, approval_id=approval_id)


@router.get("/preview/{approval_id}")
def preview_slack_blocks(
    approval_id: int,
    db: Session = Depends(get_db)
):
    """Generates and returns the Slack Block Kit payload for an approval request without sending it."""
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail=f"Approval request #{approval_id} not found.")

    post = db.query(Post).filter(Post.id == approval.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail=f"Associated post #{approval.post_id} not found.")

    blocks = SlackService.build_approval_blocks(post=post, approval=approval)
    return {
        "approval_id": approval.id,
        "post_id": post.id,
        "mock_mode": settings.SLACK_MOCK_MODE,
        "default_channel": settings.SLACK_DEFAULT_CHANNEL,
        "blocks": blocks
    }
