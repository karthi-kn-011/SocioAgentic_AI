import datetime
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from ..database.models import (
    ApprovalRequest,
    ApprovalStatus,
    Post,
    PostStatus,
    PostWorkflowStatus,
    ActivityLog,
    VALID_APPROVAL_TRANSITIONS,
    get_utc_now
)
from ..database.crud import log_activity
from ..config import settings
from ..schemas.approval import (
    ApprovalItemResponse,
    ApprovalActionResponse,
    ApprovalDecisionRequest,
    ApprovalRejectionRequest,
    ApprovalRegenerateRequest
)
from ..schemas.post import GeneratePostRequest
from .content_service import ContentService

logger = logging.getLogger("ApprovalService")


class ApprovalService:
    """Manages the lifecycle of Human-in-the-Loop review and approval decisions.
    Enforces atomic state transitions, concurrency safety, and persistent audit logging.
    """

    @classmethod
    def get_pending_approvals(cls, db: Session, skip: int = 0, limit: int = 200) -> List[ApprovalItemResponse]:
        """Retrieves all approval requests currently in PENDING status, enriched with post content."""
        requests = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.status == ApprovalStatus.PENDING.value)
            .order_by(ApprovalRequest.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [cls._enrich_approval_item(item) for item in requests]

    @classmethod
    def get_approval_by_id(cls, db: Session, approval_id: int) -> ApprovalItemResponse:
        """Retrieves an approval request by its primary key."""
        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not req:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval request #{approval_id} not found."
            )
        return cls._enrich_approval_item(req)

    @classmethod
    def get_approval_history(cls, db: Session, skip: int = 0, limit: int = 200) -> List[ApprovalItemResponse]:
        """Retrieves historical approval requests (APPROVED, REJECTED, CANCELLED)."""
        requests = (
            db.query(ApprovalRequest)
            .filter(ApprovalRequest.status != ApprovalStatus.PENDING.value)
            .order_by(ApprovalRequest.responded_at.desc().nullslast(), ApprovalRequest.id.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [cls._enrich_approval_item(item) for item in requests]

    @classmethod
    def approve_post(
        cls,
        db: Session,
        approval_id: int,
        reviewer: str = "Human Reviewer",
        review_notes: Optional[str] = None
    ) -> ApprovalActionResponse:
        """Approves a post awaiting human review.
        Enforces atomic validation to protect against concurrent duplicate approvals.
        """
        now = get_utc_now()
        # Atomic CAS update to prevent race conditions on concurrent approvals
        updated_rows = (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value
            )
            .update({
                "status": ApprovalStatus.APPROVED.value,
                "reviewer": reviewer,
                "review_notes": review_notes,
                "reviewed_at": now,
                "responded_at": now
            }, synchronize_session=False)
        )

        if updated_rows == 0:
            existing = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Approval request #{approval_id} not found."
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve request in '{existing.status}' state. Expected 'PENDING'."
            )

        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        post = db.query(Post).filter(Post.id == req.post_id).first()
        if post:
            post.status = PostStatus.APPROVED

        # Record Activity Log
        log_activity(
            db=db,
            action="APPROVAL_APPROVED",
            details=f"Post #{post.id if post else req.post_id} approved by {reviewer}. Notes: {review_notes or 'None'}",
            post_id=post.id if post else req.post_id,
            actor=reviewer
        )

        db.commit()
        db.refresh(req)
        if post:
            db.refresh(post)

        logger.info(f"Post #{req.post_id} successfully APPROVED by {reviewer}.")
        return ApprovalActionResponse(
            success=True,
            action="APPROVE",
            approval_id=req.id,
            post_id=req.post_id,
            approval_status=req.status,
            post_status=post.status.value if post and hasattr(post.status, "value") else (str(post.status) if post else "approved"),
            message=f"Post #{req.post_id} successfully approved and marked ready for scheduling."
        )

    @classmethod
    def reject_post(
        cls,
        db: Session,
        approval_id: int,
        rejection_reason: str,
        reviewer: str = "Human Reviewer",
        review_notes: Optional[str] = None
    ) -> ApprovalActionResponse:
        """Rejects a post awaiting human review, recording the mandatory reason."""
        if not rejection_reason or not rejection_reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid rejection_reason is mandatory to reject a post."
            )

        now = get_utc_now()
        # Atomic CAS update to prevent race conditions on concurrent rejections
        updated_rows = (
            db.query(ApprovalRequest)
            .filter(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == ApprovalStatus.PENDING.value
            )
            .update({
                "status": ApprovalStatus.REJECTED.value,
                "reviewer": reviewer,
                "rejection_reason": rejection_reason.strip(),
                "review_notes": review_notes,
                "reviewed_at": now,
                "responded_at": now
            }, synchronize_session=False)
        )

        if updated_rows == 0:
            existing = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Approval request #{approval_id} not found."
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject request in '{existing.status}' state. Expected 'PENDING'."
            )

        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        post = db.query(Post).filter(Post.id == req.post_id).first()
        if post:
            post.status = PostStatus.REJECTED

        # Record Activity Log
        log_activity(
            db=db,
            action="APPROVAL_REJECTED",
            details=f"Post #{post.id if post else req.post_id} rejected by {reviewer}. Reason: {rejection_reason.strip()}",
            post_id=post.id if post else req.post_id,
            actor=reviewer
        )

        db.commit()
        db.refresh(req)
        if post:
            db.refresh(post)

        logger.info(f"Post #{req.post_id} REJECTED by {reviewer}. Reason: {rejection_reason}")
        return ApprovalActionResponse(
            success=True,
            action="REJECT",
            approval_id=req.id,
            post_id=req.post_id,
            approval_status=req.status,
            post_status=post.status.value if post and hasattr(post.status, "value") else (str(post.status) if post else "rejected"),
            message=f"Post #{req.post_id} rejected: {rejection_reason}"
        )

    @classmethod
    async def regenerate_post(
        cls,
        db: Session,
        approval_id: int,
        reviewer: str = "Human Reviewer",
        feedback: Optional[str] = None,
        provider: Optional[str] = None
    ) -> ApprovalActionResponse:
        """Regenerates a post from the approval queue with a new angle, enforcing regeneration ceilings."""
        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not req:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Approval request #{approval_id} not found."
            )

        post = db.query(Post).filter(Post.id == req.post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Associated post #{req.post_id} not found."
            )

        # Check maximum regeneration ceiling
        max_limit = settings.MAX_REGENERATIONS
        if (post.regeneration_count or 0) >= max_limit:
            log_activity(
                db=db,
                action="REGENERATION_LIMIT_REACHED",
                details=f"Post #{post.id} reached maximum regeneration ceiling ({max_limit}).",
                post_id=post.id,
                actor=reviewer
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum regeneration limit ({max_limit}) reached for Post #{post.id}. Existing content preserved."
            )

        post.status = PostStatus.REGENERATING
        db.commit()

        # Log regeneration intent
        target_iter = (post.regeneration_count or 0) + 1
        log_activity(
            db=db,
            action="CONTENT_REGENERATED",
            details=f"Regeneration iteration #{target_iter} initiated by {reviewer}. Feedback: {feedback or 'None'}",
            post_id=post.id,
            actor=reviewer
        )
        db.commit()

        # Detect provider originally used on this post if available
        last_log = db.query(ActivityLog).filter(
            ActivityLog.post_id == post.id,
            ActivityLog.action.in_(["CONTENT_GENERATED", "GENERATE_POST_VARIANTS"])
        ).order_by(ActivityLog.id.desc()).first()
        detected_provider = provider or (last_log.actor if last_log and last_log.actor in ("mock", "gemini", "groq") else None)

        # Call existing ContentService with regeneration flag and previous content
        gen_request = GeneratePostRequest(
            topic=post.topic,
            theme=post.theme or "Thought Leadership",
            platforms=post.target_platforms or ["TWITTER", "LINKEDIN"],
            tone=post.tone or "Professional & Engaging",
            provider=detected_provider,
            regenerate_post_id=post.id
        )

        try:
            generation_result = await ContentService.generate_post(gen_request, db)
        except Exception as e:
            post.status = PostStatus.AWAITING_HUMAN_APPROVAL
            db.commit()
            log_activity(
                db=db,
                action="WORKFLOW_FAILED",
                details=f"Regeneration failed for Post #{post.id}: {str(e)}",
                post_id=post.id,
                actor="System"
            )
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Regeneration failed: {str(e)}"
            )

        # Reset approval request to PENDING for the newly generated copy
        now = get_utc_now()
        req.status = ApprovalStatus.PENDING.value
        req.feedback = feedback
        req.reviewer = None
        req.rejection_reason = None
        req.requested_at = now
        req.responded_at = None
        req.reviewed_at = None

        post.status = PostStatus.AWAITING_HUMAN_APPROVAL
        db.commit()
        db.refresh(req)
        db.refresh(post)

        return ApprovalActionResponse(
            success=True,
            action="REGENERATE",
            approval_id=req.id,
            post_id=post.id,
            approval_status=req.status,
            post_status=post.status.value if hasattr(post.status, "value") else str(post.status),
            message=f"Post #{post.id} regenerated (Version {post.generation_version}). Awaiting human review.",
            details={
                "version": post.generation_version,
                "regeneration_count": post.regeneration_count,
                "quality_score": post.review_score,
                "variants": post.platform_contents
            }
        )

    @classmethod
    def _enrich_approval_item(cls, item: ApprovalRequest) -> ApprovalItemResponse:
        """Enriches an ApprovalRequest model with its parent Post and active schedule metadata."""
        p = item.post

        active_sched = None
        published_targets = []
        scheduled_targets = []
        failed_targets = []
        publication_state = "UNSCHEDULED"

        if p and p.scheduled_posts:
            # Prefer active / non-cancelled schedule, else None (cancelled means no active schedule)
            non_cancelled = [s for s in p.scheduled_posts if s.status != "CANCELLED"]
            active_sched = non_cancelled[-1] if non_cancelled else None

            # Collect latest schedule status per platform
            platform_latest = {}
            for s in p.scheduled_posts:
                plat = s.platform or "TWITTER"
                platform_latest[plat] = s

            for plat, s in platform_latest.items():
                if s.status == "PUBLISHED":
                    if plat not in published_targets:
                        published_targets.append(plat)
                elif s.status in ("SCHEDULED", "PUBLISHING"):
                    if plat not in scheduled_targets:
                        scheduled_targets.append(plat)
                elif s.status == "PUBLISH_FAILED":
                    if plat not in failed_targets:
                        failed_targets.append(plat)

            all_targets = p.target_platforms if (p.target_platforms and len(p.target_platforms) > 0) else list(platform_latest.keys())
            total_targets = len(all_targets) if all_targets else 1

            if len(published_targets) >= total_targets and total_targets > 0:
                publication_state = "PUBLISHED"
            elif len(published_targets) > 0 and len(scheduled_targets) > 0:
                publication_state = "PARTIALLY_PUBLISHED"
            elif len(published_targets) > 0 and len(failed_targets) > 0:
                publication_state = "PARTIALLY_FAILED"
            elif len(published_targets) > 0:
                if len(published_targets) == len(platform_latest):
                    publication_state = "PUBLISHED"
                else:
                    publication_state = "PARTIALLY_PUBLISHED"
            elif len(scheduled_targets) > 0:
                publication_state = "SCHEDULED"
            elif len(failed_targets) > 0:
                publication_state = "PUBLISH_FAILED"
            else:
                publication_state = "UNSCHEDULED"

        # If post status itself is explicitly published
        p_status_str = (p.status.value if hasattr(p.status, "value") else str(p.status)).lower() if (p and p.status) else ""
        if p_status_str == "published" and publication_state == "UNSCHEDULED":
            publication_state = "PUBLISHED"

        latest_publish_log = None
        if p and p.publish_logs:
            latest_publish_log = p.publish_logs[-1]

        # Determine published timestamp from post, schedule, or publish log
        published_ts = None
        if p and p.published_at:
            published_ts = p.published_at
        elif active_sched and active_sched.published_at:
            published_ts = active_sched.published_at
        elif p and p.scheduled_posts:
            pub_scheds = [s for s in p.scheduled_posts if s.status == "PUBLISHED" and s.published_at]
            if pub_scheds:
                published_ts = pub_scheds[-1].published_at
        if not published_ts and latest_publish_log and latest_publish_log.status in ("SUCCESS", "SIMULATED"):
            published_ts = latest_publish_log.published_at or latest_publish_log.attempted_at

        return ApprovalItemResponse(
            id=item.id,
            post_id=item.post_id,
            channel=item.channel or "web",
            status=item.status,
            reviewer=item.reviewer,
            feedback=item.feedback,
            rejection_reason=item.rejection_reason,
            review_notes=item.review_notes,
            requested_at=item.requested_at or item.created_at,
            reviewed_at=item.reviewed_at or item.responded_at,
            created_at=item.created_at,
            topic=p.topic if p else None,
            theme=p.theme if p else None,
            tone=p.tone if p else None,
            target_platforms=p.target_platforms if p else [],
            platform_contents=p.platform_contents if p else {},
            review_score=p.review_score if p else None,
            review_feedback=p.review_feedback if p else None,
            review_passed=p.review_passed if p else None,
            regeneration_count=p.regeneration_count if p else 0,
            generation_version=p.generation_version if p else 1,
            post_status=p.status.value if (p and hasattr(p.status, "value")) else (str(p.status) if p else None),
            schedule_id=active_sched.id if active_sched else None,
            schedule_status=active_sched.status if active_sched else None,
            scheduled_at=active_sched.scheduled_at if active_sched else None,
            scheduled_timezone=active_sched.timezone if active_sched else None,
            published_at=published_ts,
            external_post_id=latest_publish_log.external_post_id if latest_publish_log else None,
            publication_state=publication_state,
            published_targets=published_targets,
            scheduled_targets=scheduled_targets,
            failed_targets=failed_targets,
        )
