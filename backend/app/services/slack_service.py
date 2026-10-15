import os
import json
import time
import hmac
import hashlib
import logging
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
import httpx

from ..config import settings
from ..database.models import ApprovalRequest, ApprovalStatus, Post, PostStatus, get_utc_now
from ..database.crud import log_activity

logger = logging.getLogger("SlackService")


def get_slack_signing_secret() -> str:
    """Returns configured Slack signing secret or fallback for mock mode."""
    if settings.SLACK_SIGNING_SECRET:
        return settings.SLACK_SIGNING_SECRET
    if settings.SLACK_MOCK_MODE:
        return "mock_slack_signing_secret_for_dev_mode"
    return ""


class SlackService:
    """Manages Slack Block Kit approval card generation, signature verification,
    notification dispatch, and in-place message updates.
    """

    SIGNATURE_VERSION = "v0"
    REPLAY_WINDOW_SECONDS = 300  # 5 minutes

    @classmethod
    def generate_signature(cls, signing_secret: str, timestamp: str, raw_body: bytes) -> str:
        """Computes RFC HMAC-SHA256 Slack signature: v0=hex(hmac_sha256(secret, 'v0:{timestamp}:{body}'))"""
        body_str = raw_body.decode("utf-8", errors="replace")
        sig_basestring = f"{cls.SIGNATURE_VERSION}:{timestamp}:{body_str}"
        computed_hash = hmac.new(
            signing_secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return f"{cls.SIGNATURE_VERSION}={computed_hash}"

    @classmethod
    def verify_slack_signature(
        cls,
        signing_secret: str,
        request_body: bytes,
        timestamp: Optional[str],
        signature: Optional[str]
    ) -> bool:
        """Verifies an incoming Slack webhook request using HMAC-SHA256 and anti-replay timestamp verification."""
        if not timestamp or not signature or not signing_secret:
            return False

        try:
            req_ts = float(timestamp)
        except (ValueError, TypeError):
            return False

        current_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
        if abs(current_ts - req_ts) > cls.REPLAY_WINDOW_SECONDS:
            logger.warning(f"Slack request rejected: timestamp skew {abs(current_ts - req_ts):.1f}s > {cls.REPLAY_WINDOW_SECONDS}s.")
            return False

        expected_signature = cls.generate_signature(signing_secret, timestamp, request_body)
        return hmac.compare_digest(expected_signature, signature)

    @classmethod
    def build_approval_blocks(cls, post: Post, approval: ApprovalRequest) -> List[Dict[str, Any]]:
        """Constructs an interactive Slack Block Kit message with Approve and Reject buttons."""
        platforms_display = ", ".join(post.target_platforms) if post.target_platforms else "All Platforms"
        tone_display = post.tone or "Professional"
        score_display = f"{post.review_score}/100" if post.review_score is not None else "N/A"

        preview_text = post.raw_content or ""
        if not preview_text and post.platform_contents:
            preview_text = next(iter(post.platform_contents.values()), "")
        if len(preview_text) > 500:
            preview_text = preview_text[:497] + "..."

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"📢 Content Approval Request #{post.id}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Topic:*\n{post.topic or 'Untitled'}"},
                    {"type": "mrkdwn", "text": f"*Platforms:*\n{platforms_display}"},
                    {"type": "mrkdwn", "text": f"*Tone:*\n{tone_display}"},
                    {"type": "mrkdwn", "text": f"*AI Score:*\n{score_display}"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Post Preview:*\n```{preview_text}```"
                }
            },
            {
                "type": "actions",
                "block_id": f"approval_actions_{approval.id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "✅ Approve & Schedule",
                            "emoji": True
                        },
                        "style": "primary",
                        "action_id": "approve_post",
                        "value": str(approval.id)
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "❌ Reject",
                            "emoji": True
                        },
                        "style": "danger",
                        "action_id": "reject_post",
                        "value": str(approval.id)
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Approval ID: `#{approval.id}` | Version: `{post.generation_version or 1}` | Status: `PENDING`"
                    }
                ]
            }
        ]
        return blocks

    @classmethod
    def build_resolved_blocks(
        cls,
        post: Post,
        approval: ApprovalRequest,
        action: str,
        reviewer: str,
        reason: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Constructs a non-interactive resolved Slack Block Kit message replacing the original card."""
        is_approved = action.upper() == "APPROVED" or action.upper() == "APPROVE"
        header_text = f"✅ Post #{post.id} Approved" if is_approved else f"❌ Post #{post.id} Rejected"

        platforms_display = ", ".join(post.target_platforms) if post.target_platforms else "All Platforms"
        fields = [
            {"type": "mrkdwn", "text": f"*Topic:*\n{post.topic or 'Untitled'}"},
            {"type": "mrkdwn", "text": f"*Platforms:*\n{platforms_display}"},
            {"type": "mrkdwn", "text": f"*Decision:*\n{'APPROVED' if is_approved else 'REJECTED'}"},
            {"type": "mrkdwn", "text": f"*Reviewer:*\n{reviewer}"}
        ]

        if not is_approved and reason:
            fields.append({"type": "mrkdwn", "text": f"*Rejection Reason:*\n{reason}"})

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": header_text,
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": fields
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Approval ID: `#{approval.id}` | Responded: `{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}`"
                    }
                ]
            }
        ]
        return blocks

    @classmethod
    def dispatch_approval_card(cls, db: Session, approval_id: int) -> Dict[str, Any]:
        """Dispatches an interactive approval card to the configured Slack channel.
        Respects SLACK_MOCK_MODE to prevent outbound network calls.
        """
        approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not approval:
            raise HTTPException(status_code=404, detail=f"Approval request #{approval_id} not found.")

        post = db.query(Post).filter(Post.id == approval.post_id).first()
        if not post:
            raise HTTPException(status_code=404, detail=f"Post #{approval.post_id} not found.")

        blocks = cls.build_approval_blocks(post=post, approval=approval)
        fallback_text = f"Content approval required for Post #{post.id}: {post.topic}"

        now_utc = get_utc_now()

        if settings.SLACK_MOCK_MODE:
            mock_ts = f"mock_ts_{int(now_utc.timestamp())}_{approval.id}"
            approval.message_ts = mock_ts
            approval.channel = "slack"
            log_activity(
                db=db,
                action="SLACK_NOTIFICATION_DISPATCHED",
                details=f"Mock Slack approval card dispatched for Post #{post.id} to {settings.SLACK_DEFAULT_CHANNEL}.",
                post_id=post.id,
                actor="SlackService"
            )
            db.commit()
            logger.info(f"[MOCK SLACK] Dispatched approval card for Post #{post.id} (Approval #{approval.id}, ts={mock_ts}).")
            return {
                "success": True,
                "mock": True,
                "channel": settings.SLACK_DEFAULT_CHANNEL,
                "message_ts": mock_ts,
                "blocks": blocks,
                "text": fallback_text
            }

        # Real Slack delivery
        if not settings.SLACK_BOT_TOKEN:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SLACK_BOT_TOKEN is not configured."
            )

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"},
                    json={
                        "channel": settings.SLACK_DEFAULT_CHANNEL,
                        "text": fallback_text,
                        "blocks": blocks
                    }
                )
                data = res.json()
                if not data.get("ok"):
                    error_msg = data.get("error", "Unknown Slack API error")
                    logger.error(f"Slack postMessage failed: {error_msg}")
                    raise HTTPException(status_code=502, detail=f"Slack API error: {error_msg}")

                real_ts = data.get("ts")
                approval.message_ts = real_ts
                approval.channel = "slack"
                log_activity(
                    db=db,
                    action="SLACK_NOTIFICATION_DISPATCHED",
                    details=f"Slack approval card posted for Post #{post.id} to {settings.SLACK_DEFAULT_CHANNEL} (ts={real_ts}).",
                    post_id=post.id,
                    actor="SlackService"
                )
                db.commit()
                return {
                    "success": True,
                    "mock": False,
                    "channel": settings.SLACK_DEFAULT_CHANNEL,
                    "message_ts": real_ts,
                    "blocks": blocks,
                    "text": fallback_text
                }
        except httpx.RequestError as e:
            logger.error(f"Network error contacting Slack: {e}")
            raise HTTPException(status_code=502, detail=f"Network error contacting Slack: {str(e)}")

    @classmethod
    def update_slack_message(
        cls,
        response_url: Optional[str],
        blocks: List[Dict[str, Any]],
        text: str
    ) -> Dict[str, Any]:
        """Updates the original Slack message in-place via response_url."""
        if not response_url:
            return {"success": False, "reason": "No response_url provided."}

        if settings.SLACK_MOCK_MODE:
            logger.info(f"[MOCK SLACK] Updated Slack message in-place via response_url: {response_url}")
            return {"success": True, "mock": True, "text": text}

        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    response_url,
                    json={
                        "replace_original": True,
                        "text": text,
                        "blocks": blocks
                    }
                )
                return {"success": res.is_success, "status_code": res.status_code}
        except Exception as e:
            logger.warning(f"Failed to post in-place update to response_url {response_url}: {e}")
            return {"success": False, "error": str(e)}
