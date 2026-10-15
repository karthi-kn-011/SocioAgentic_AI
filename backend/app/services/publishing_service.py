import logging
import datetime
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from backend.app.database.models import (
    ScheduledPost,
    Post,
    PostWorkflowStatus,
    ScheduleStatus,
    PublishLog,
    ActivityLog,
    PlatformType,
    get_utc_now,
)
from backend.app.publishers.registry import PublisherRegistry
from backend.app.services.schedule_service import ScheduleService
from backend.app.config import get_settings

logger = logging.getLogger(__name__)

class PublishingService:
    """Orchestrates publisher execution, idempotency, retries, and publication logging."""

    @classmethod
    def execute_publish(
        cls,
        db: Session,
        schedule_id: int,
        require_claim: bool = True,
        actor: str = "Scheduler",
    ) -> Tuple[bool, Optional[str]]:
        """Execute publication for a specific scheduled post with atomic claiming and retry handling.

        Args:
            db: SQLAlchemy session.
            schedule_id: ID of the ScheduledPost.
            require_claim: If True, executes atomic claim before proceeding.
            actor: Initiating actor (e.g. 'Scheduler' or 'User').

        Returns:
            Tuple of (success_boolean, message_or_error)
        """
        settings = get_settings()
        max_retries = getattr(settings, "MAX_PUBLISH_RETRIES", 3)

        if require_claim:
            claimed = ScheduleService.claim_due_post(db, schedule_id)
            if not claimed:
                logger.info("Schedule %s was not claimed (already in progress or cancelled)", schedule_id)
                return False, "Post could not be claimed; may be already processing or cancelled."

        # Fetch post and schedule
        sched = db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
        if not sched or not sched.post:
            return False, "Schedule or associated Post not found."

        post = sched.post
        platform_raw = None
        if sched.target_platforms and isinstance(sched.target_platforms, list) and len(sched.target_platforms) > 0:
            platform_raw = sched.target_platforms[0]
        elif sched.platform:
            platform_raw = sched.platform
        elif hasattr(post, "platform"):
            platform_raw = post.platform.value if hasattr(post.platform, "value") else str(post.platform)

        from backend.app.database.models import normalize_platform_name, normalize_platform_type
        platform_name = normalize_platform_name(platform_raw, allow_none=True, default_if_none="TWITTER")
        platform_enum = normalize_platform_type(platform_name)

        now_utc = get_utc_now()
        now_naive = now_utc.replace(tzinfo=None)

        # Create initial audit PublishLog entry
        log_entry = PublishLog(
            post_id=post.id,
            schedule_id=sched.id,
            platform=platform_enum,
            provider="MockPublisher",
            is_mock=True,
            status="IN_PROGRESS",
            retry_count=sched.retry_count,
            idempotency_key=sched.idempotency_key,
            attempted_at=now_naive,
            published_at=now_naive,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)

        # Resolve platform publisher
        publisher = PublisherRegistry.get(platform_name)

        try:
            result = publisher.publish(post=post, scheduled_post=sched)
        except Exception as exc:
            logger.exception("Unexpected publisher exception for schedule %s: %s", schedule_id, exc)
            from backend.app.publishers.base import PublishResult
            result = PublishResult(
                status="FAILED",
                platform=platform_name,
                provider=publisher.__class__.__name__,
                is_mock=True,
                error_message=f"Publisher runtime error: {str(exc)}",
            )

        # Process publication outcome
        if result.status in ("SUCCESS", "SIMULATED"):
            sched.status = ScheduleStatus.PUBLISHED.value
            sched.published_at = now_naive
            sched.executed_at = now_naive
            sched.updated_at = now_naive
            sched.last_error = None

            # Publish all sibling active schedules for this post so all targets are published
            other_active_schedules = db.query(ScheduledPost).filter(
                ScheduledPost.post_id == post.id,
                ScheduledPost.id != sched.id,
                ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
            ).all()

            for other_s in other_active_schedules:
                other_p_raw = None
                if other_s.target_platforms and isinstance(other_s.target_platforms, list) and len(other_s.target_platforms) > 0:
                    other_p_raw = other_s.target_platforms[0]
                elif other_s.platform:
                    other_p_raw = other_s.platform
                other_p_name = normalize_platform_name(other_p_raw, allow_none=True, default_if_none="TWITTER")
                other_p_enum = normalize_platform_type(other_p_name)
                other_pub = PublisherRegistry.get(other_p_name)
                try:
                    other_res = other_pub.publish(post=post, scheduled_post=other_s)
                except Exception as exc:
                    from backend.app.publishers.base import PublishResult
                    other_res = PublishResult(
                        status="FAILED",
                        platform=other_p_name,
                        provider=other_pub.__class__.__name__,
                        is_mock=True,
                        error_message=f"Publisher runtime error: {str(exc)}",
                    )
                if other_res.status in ("SUCCESS", "SIMULATED"):
                    other_s.status = ScheduleStatus.PUBLISHED.value
                    other_s.published_at = now_naive
                    other_s.executed_at = now_naive
                    other_s.updated_at = now_naive
                    other_s.last_error = None
                else:
                    other_s.retry_count += 1
                    other_s.last_error = other_res.error_message
                    other_s.updated_at = now_naive

                sib_log = PublishLog(
                    post_id=post.id,
                    schedule_id=other_s.id,
                    platform=other_p_enum,
                    provider=other_res.provider,
                    is_mock=other_res.is_mock,
                    status=other_res.status,
                    retry_count=other_s.retry_count,
                    idempotency_key=other_s.idempotency_key,
                    external_post_id=other_res.external_post_id,
                    response_payload=other_res.response_payload,
                    error_message=other_res.error_message,
                    attempted_at=now_naive,
                    completed_at=now_naive if other_res.status in ("SUCCESS", "SIMULATED") else None,
                    published_at=now_naive if other_res.status in ("SUCCESS", "SIMULATED") else None,
                )
                db.add(sib_log)

            # Flush status updates before checking remaining active schedules
            db.flush()
            remaining_active = db.query(ScheduledPost).filter(
                ScheduledPost.post_id == post.id,
                ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
            ).first()

            if not remaining_active:
                post.status = PostWorkflowStatus.PUBLISHED.value
                post.published_at = now_naive
            else:
                post.status = PostWorkflowStatus.SCHEDULED.value

            log_entry.status = result.status
            log_entry.provider = result.provider
            log_entry.is_mock = result.is_mock
            log_entry.external_post_id = result.external_post_id
            log_entry.response_payload = result.response_payload
            log_entry.completed_at = now_naive
            log_entry.error_message = None

            activity = ActivityLog(
                post_id=post.id,
                action="POST_PUBLISHED",
                details=(
                    f"Published to {platform_name} via {result.provider}. "
                    f"ExtID: {result.external_post_id} (Mock: {result.is_mock})"
                ),
                actor=actor,
            )
            db.add(activity)
            db.commit()

            logger.info("Successfully published schedule %s (ExtID: %s)", schedule_id, result.external_post_id)
            return True, f"Published successfully with ID {result.external_post_id}"

        else:
            # Publish failed
            sched.retry_count += 1
            sched.last_error = result.error_message or "Unknown publication failure"
            sched.updated_at = now_naive

            log_entry.status = "FAILED"
            log_entry.provider = result.provider
            log_entry.is_mock = result.is_mock
            log_entry.error_message = result.error_message
            log_entry.completed_at = now_naive

            if sched.retry_count < max_retries:
                # Return to SCHEDULED for next poll interval / retry
                sched.status = ScheduleStatus.SCHEDULED.value
                post.status = PostWorkflowStatus.SCHEDULED.value

                activity = ActivityLog(
                    post_id=post.id,
                    action="PUBLISH_RETRYING",
                    details=(
                        f"Publish attempt {sched.retry_count}/{max_retries} failed: "
                        f"{result.error_message}. Re-queued for retry."
                    ),
                    actor=actor,
                )
                db.add(activity)
                db.commit()

                logger.warning(
                    "Schedule %s failed attempt %s/%s. Re-queued.",
                    schedule_id,
                    sched.retry_count,
                    max_retries,
                )
                return False, f"Attempt {sched.retry_count}/{max_retries} failed: {result.error_message}"

            else:
                # Retries exhausted
                sched.status = ScheduleStatus.PUBLISH_FAILED.value
                other_active = db.query(ScheduledPost).filter(
                    ScheduledPost.post_id == post.id,
                    ScheduledPost.id != sched.id,
                    ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
                ).first()
                if not other_active:
                    post.status = PostWorkflowStatus.FAILED.value
                else:
                    post.status = PostWorkflowStatus.SCHEDULED.value

                activity = ActivityLog(
                    post_id=post.id,
                    action="PUBLISH_EXHAUSTED",
                    details=(
                        f"Publishing failed after {sched.retry_count} retries. "
                        f"Terminal error: {result.error_message}"
                    ),
                    actor=actor,
                )
                db.add(activity)
                db.commit()

                logger.error("Schedule %s exhausted all %s retries.", schedule_id, max_retries)
                return False, f"Publishing failed permanently: {result.error_message}"

    @classmethod
    def publish_now(cls, db: Session, schedule_id: int, actor: str = "User") -> Tuple[bool, str]:
        """Manually trigger immediate publishing of an existing schedule."""
        sched = db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
        if not sched:
            raise ValueError(f"Schedule with id {schedule_id} not found.")

        current_status = sched.status.upper() if sched.status else ""
        if current_status == ScheduleStatus.PUBLISHED.value:
            raise ValueError("Post has already been published.")
        if current_status == ScheduleStatus.PUBLISHING.value:
            raise ValueError("Post is currently in the process of being published.")
        if current_status == ScheduleStatus.CANCELLED.value:
            raise ValueError("Cannot publish a cancelled schedule.")

        # Attempt atomic claim
        claimed = ScheduleService.claim_due_post(db, schedule_id)
        if not claimed:
            # If it was in PUBLISH_FAILED, claim_due_post looks for SCHEDULED, so set to SCHEDULED first
            if current_status == ScheduleStatus.PUBLISH_FAILED.value:
                sched.status = ScheduleStatus.SCHEDULED.value
                db.commit()
                claimed = ScheduleService.claim_due_post(db, schedule_id)

        if not claimed:
            raise ValueError("Could not claim schedule for immediate publishing.")

        success, message = cls.execute_publish(db, schedule_id, require_claim=False, actor=actor)
        return success, message or ""

    @classmethod
    def process_due_posts(cls, db: Session, cutoff_time: Optional[datetime.datetime] = None) -> int:
        """Scan and process all posts currently due for publication."""
        due_posts = ScheduleService.get_due_posts(db, cutoff_time)
        processed_count = 0

        for sched in due_posts:
            try:
                success, _ = cls.execute_publish(db, sched.id, require_claim=True, actor="Scheduler")
                if success:
                    processed_count += 1
            except Exception as e:
                logger.error("Error processing due schedule %s: %s", sched.id, e)

        return processed_count
