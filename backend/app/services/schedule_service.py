import uuid
import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.app.database.models import (
    ScheduledPost,
    Post,
    PostWorkflowStatus,
    ScheduleStatus,
    ApprovalRequest,
    ApprovalStatus,
    VALID_SCHEDULE_TRANSITIONS,
    ActivityLog,
    get_utc_now,
)
import logging
from backend.app.config import get_settings

logger = logging.getLogger(__name__)

class ScheduleService:
    """Service managing scheduling, rescheduling, cancellation, and due queries for posts."""

    @staticmethod
    def _validate_timezone(tz_name: str) -> str:
        if not tz_name:
            return "UTC"
        try:
            ZoneInfo(tz_name)
            return tz_name
        except Exception:
            # Fallback to UTC if timezone is invalid
            return "UTC"

    @classmethod
    def schedule_post(
        cls,
        db: Session,
        post_id: int,
        scheduled_at: datetime.datetime,
        timezone: str = "UTC",
        platform: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
        allow_past: bool = False,
        actor: str = "User",
    ) -> ScheduledPost:
        """Schedule an approved post for publication across designated target platforms."""
        post = db.query(Post).filter(Post.id == post_id).first()
        if not post:
            raise ValueError(f"Post with id {post_id} not found.")

        # Ensure post is approved before scheduling (or return existing schedule idempotently)
        post_status = (post.status.value if hasattr(post.status, "value") else str(post.status)).lower()
        if "approved" not in post_status:
            if "scheduled" in post_status:
                existing_active = db.query(ScheduledPost).filter(
                    ScheduledPost.post_id == post.id,
                    ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
                ).all()
                if existing_active:
                    logger.info("Post %s is already scheduled; returning existing active schedule idempotently.", post_id)
                    return existing_active[0]
                else:
                    # Reconciliation: post has status 'scheduled' but 0 active schedules (all were cancelled)
                    # Verify whether the post was approved by human:
                    latest_approval = db.query(ApprovalRequest).filter(
                        ApprovalRequest.post_id == post.id
                    ).order_by(ApprovalRequest.id.desc()).first()
                    if latest_approval and latest_approval.status == ApprovalStatus.APPROVED.value:
                        post.status = PostWorkflowStatus.APPROVED.value
                        db.commit()
                        logger.info("Reconciled post %s to APPROVED because all previous schedules were cancelled and post has approval.", post_id)
                    else:
                        raise ValueError(f"Cannot schedule post in status '{post.status}'. Only approved posts can be scheduled.")
            else:
                raise ValueError(
                    f"Cannot schedule post in status '{post.status}'. Only approved posts can be scheduled."
                )

        tz_str = cls._validate_timezone(timezone)
        now_utc = get_utc_now()

        # Normalize scheduled_at to UTC
        if scheduled_at.tzinfo is None:
            # Localize using specified timezone then convert to UTC
            try:
                local_dt = scheduled_at.replace(tzinfo=ZoneInfo(tz_str))
                utc_dt = local_dt.astimezone(datetime.timezone.utc)
            except Exception:
                utc_dt = scheduled_at.replace(tzinfo=datetime.timezone.utc)
        else:
            utc_dt = scheduled_at.astimezone(datetime.timezone.utc)

        # Naive UTC for SQLite storage
        utc_naive = utc_dt.replace(tzinfo=None)

        if not allow_past and utc_naive <= now_utc.replace(tzinfo=None):
            raise ValueError("Scheduled time must be in the future.")

        # Determine target platform list
        targets: List[str] = []
        if platform:
            targets = [platform]
        elif platforms and isinstance(platforms, list) and len(platforms) > 0:
            targets = platforms
        elif post.target_platforms and isinstance(post.target_platforms, list) and len(post.target_platforms) > 0:
            targets = post.target_platforms
        else:
            p_val = post.platform.value if hasattr(post.platform, "value") else str(post.platform or "TWITTER")
            targets = [p_val]

        from backend.app.database.models import normalize_platform_name
        canonical_targets = []
        for t in targets:
            c = normalize_platform_name(t)
            if c not in canonical_targets:
                canonical_targets.append(c)

        if not canonical_targets:
            raise ValueError("At least one valid publication target platform must be specified.")

        # Strict content validation: reject scheduling for platforms with missing or empty content
        for target in canonical_targets:
            if hasattr(post, "has_platform_content") and not post.has_platform_content(target):
                raise ValueError(
                    f"Cannot schedule post #{post.id} for platform '{target}': No platform-specific content found for '{target}'."
                )

        # Prevent duplicate identical schedules:
        existing_active = db.query(ScheduledPost).filter(
            ScheduledPost.post_id == post.id,
            ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
        ).all()
        active_platforms = {s.platform for s in existing_active if s.platform}

        scheduled_posts_created = []
        ts = int(utc_naive.timestamp())
        now_naive = now_utc.replace(tzinfo=None)

        for target in canonical_targets:
            # Deterministic, stable idempotency key and job ID (no random suffix on retries)
            base_idempotency_key = (
                f"{idempotency_key}_{target.lower()}"
                if idempotency_key
                else f"sched_{post_id}_{target.lower()}_{ts}"
            )
            base_job_id = f"job_{post_id}_{target.lower()}_{ts}"

            # Check if this exact idempotency key or job_id already exists in the database
            existing_by_key = db.query(ScheduledPost).filter(
                (ScheduledPost.idempotency_key == base_idempotency_key) | (ScheduledPost.job_id == base_job_id)
            ).first()

            if existing_by_key:
                if existing_by_key.status in (ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value):
                    scheduled_posts_created.append(existing_by_key)
                    continue
                # If existing record was CANCELLED, preserve it in history and allocate fresh unique keys for this new schedule attempt
                attempt_suffix = 1
                unique_key = f"{base_idempotency_key}_r{attempt_suffix}"
                unique_job = f"{base_job_id}_r{attempt_suffix}"
                while db.query(ScheduledPost).filter(
                    (ScheduledPost.idempotency_key == unique_key) | (ScheduledPost.job_id == unique_job)
                ).first() is not None:
                    attempt_suffix += 1
                    unique_key = f"{base_idempotency_key}_r{attempt_suffix}"
                    unique_job = f"{base_job_id}_r{attempt_suffix}"
                target_idempotency_key = unique_key
                job_id = unique_job
            else:
                target_idempotency_key = base_idempotency_key
                job_id = base_job_id

            # If target already active on this post, reuse without creating duplicate active row
            if target in active_platforms:
                existing_sched = next(s for s in existing_active if s.platform == target)
                scheduled_posts_created.append(existing_sched)
                continue

            sched = ScheduledPost(
                post_id=post.id,
                platform=target,
                target_platforms=[target],
                job_id=job_id,
                scheduled_at=utc_naive,
                run_at=utc_naive,
                timezone=tz_str,
                status=ScheduleStatus.SCHEDULED.value,
                retry_count=0,
                idempotency_key=target_idempotency_key,
                created_at=now_naive,
                updated_at=now_naive,
            )
            db.add(sched)
            scheduled_posts_created.append(sched)

        if not scheduled_posts_created:
            if existing_active:
                return existing_active[0]
            # Fallback single creation with deterministic key
            target = canonical_targets[0] if canonical_targets else "TWITTER"
            target_idempotency_key = f"sched_{post_id}_{target.lower()}_{ts}"
            sched = ScheduledPost(
                post_id=post.id,
                platform=target,
                target_platforms=[target],
                job_id=f"job_{post_id}_{target.lower()}_{ts}",
                scheduled_at=utc_naive,
                run_at=utc_naive,
                timezone=tz_str,
                status=ScheduleStatus.SCHEDULED.value,
                retry_count=0,
                idempotency_key=target_idempotency_key,
                created_at=now_naive,
                updated_at=now_naive,
            )
            db.add(sched)
            scheduled_posts_created.append(sched)

        # Update post workflow status and current target platforms
        post.status = PostWorkflowStatus.SCHEDULED.value
        post.target_platforms = canonical_targets

        # Log activity
        log = ActivityLog(
            post_id=post.id,
            action="POST_SCHEDULED",
            details=f"Post scheduled for {utc_naive.isoformat()} UTC ({tz_str}) across platforms: {', '.join(canonical_targets)}",
            actor=actor,
        )
        db.add(log)

        db.commit()
        for s in scheduled_posts_created:
            db.refresh(s)
        return scheduled_posts_created[0]

    @classmethod
    def reschedule_post(
        cls,
        db: Session,
        schedule_id: int,
        new_scheduled_at: datetime.datetime,
        new_timezone: Optional[str] = None,
        platform: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None,
        allow_past: bool = False,
        actor: str = "User",
    ) -> ScheduledPost:
        """Reschedule a post that is currently in SCHEDULED or PUBLISH_FAILED status,
        supporting updates to date, time, timezone, and publication targets.
        """
        sched = db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
        if not sched:
            raise ValueError(f"Schedule with id {schedule_id} not found.")

        current_status = sched.status.upper() if sched.status else ""
        if current_status == ScheduleStatus.PUBLISHED.value:
            raise ValueError("Cannot reschedule an already published post (PUBLISHED).")
        if current_status == ScheduleStatus.PUBLISHING.value:
            raise ValueError("Cannot reschedule post while publication is in progress (PUBLISHING).")
        if current_status == ScheduleStatus.CANCELLED.value:
            raise ValueError("Cannot reschedule a cancelled post (CANCELLED). Please schedule as a new post.")
        if current_status not in (ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISH_FAILED.value):
            raise ValueError(
                f"Cannot reschedule post in '{sched.status}' status. Only SCHEDULED or PUBLISH_FAILED posts can be rescheduled."
            )

        tz_str = cls._validate_timezone(new_timezone or sched.timezone)
        now_utc = get_utc_now()
        now_naive = now_utc.replace(tzinfo=None)

        if new_scheduled_at.tzinfo is None:
            try:
                local_dt = new_scheduled_at.replace(tzinfo=ZoneInfo(tz_str))
                utc_dt = local_dt.astimezone(datetime.timezone.utc)
            except Exception:
                utc_dt = new_scheduled_at.replace(tzinfo=datetime.timezone.utc)
        else:
            utc_dt = new_scheduled_at.astimezone(datetime.timezone.utc)

        utc_naive = utc_dt.replace(tzinfo=None)

        if not allow_past and utc_naive <= now_naive:
            raise ValueError("New scheduled time must be in the future.")

        post = sched.post
        from backend.app.database.models import normalize_platform_name

        desired_raw = None
        if platforms is not None and isinstance(platforms, list):
            desired_raw = platforms
        elif platform is not None:
            desired_raw = [platform]

        primary_schedule = sched

        # 1. Fetch all existing schedules for this content item
        all_schedules = (
            db.query(ScheduledPost)
            .filter(ScheduledPost.post_id == sched.post_id)
            .all()
        )

        # Enforce safe concurrency: reject rescheduling if any target is currently PUBLISHING
        publishing_schedules = [s for s in all_schedules if s.status == ScheduleStatus.PUBLISHING.value]
        if publishing_schedules:
            raise ValueError("Cannot reschedule while one or more platform publications are in progress (PUBLISHING).")

        published_schedules = [s for s in all_schedules if s.status == ScheduleStatus.PUBLISHED.value]
        published_platforms = {s.platform for s in published_schedules if s.platform}

        active_schedules = [
            s for s in all_schedules
            if s.status in (ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISH_FAILED.value)
        ]
        active_by_platform = {s.platform: s for s in active_schedules if s.platform}

        if desired_raw is not None:
            # 2. Normalize and strictly validate requested platform names
            canonical_desired = []
            for p in desired_raw:
                c_name = normalize_platform_name(p)
                if c_name not in canonical_desired:
                    canonical_desired.append(c_name)

            if not canonical_desired:
                raise ValueError("At least one valid publication target platform must be specified.")

            # 3. Strict content validation: ensure post has valid content for all requested targets
            if post:
                for target in canonical_desired:
                    if hasattr(post, "has_platform_content") and not post.has_platform_content(target):
                        raise ValueError(
                            f"Cannot reschedule post #{post.id} for platform '{target}': No platform-specific content found for '{target}'."
                        )

            # A. Retain and update existing active schedules matching desired targets
            retained_schedules = []
            for target in canonical_desired:
                if target in active_by_platform:
                    s = active_by_platform[target]
                    s.scheduled_at = utc_naive
                    s.run_at = utc_naive
                    s.timezone = tz_str
                    s.status = ScheduleStatus.SCHEDULED.value
                    s.updated_at = now_naive
                    s.last_error = None
                    retained_schedules.append(s)

            # B. Remove active targets no longer requested (cancel them, never delete)
            for active_p, s in active_by_platform.items():
                if active_p not in canonical_desired:
                    s.status = ScheduleStatus.CANCELLED.value
                    s.cancelled_at = now_naive
                    s.updated_at = now_naive

            # C. Add new target schedules not yet present in active or published sets
            ts = int(utc_naive.timestamp())
            added_schedules = []
            for target in canonical_desired:
                if target not in active_by_platform and target not in published_platforms:
                    target_idempotency_key = (
                        f"{idempotency_key}_{target.lower()}"
                        if idempotency_key
                        else f"sched_{sched.post_id}_{target.lower()}_{ts}"
                    )
                    job_id = f"job_{sched.post_id}_{target.lower()}_{ts}"

                    new_sched = ScheduledPost(
                        post_id=sched.post_id,
                        platform=target,
                        target_platforms=[target],
                        job_id=job_id,
                        scheduled_at=utc_naive,
                        run_at=utc_naive,
                        timezone=tz_str,
                        status=ScheduleStatus.SCHEDULED.value,
                        retry_count=0,
                        idempotency_key=target_idempotency_key,
                        created_at=now_naive,
                        updated_at=now_naive,
                    )
                    db.add(new_sched)
                    added_schedules.append(new_sched)

            # Update post target_platforms to represent ONLY current intended targets
            if post:
                post.target_platforms = canonical_desired

            # Determine primary return schedule
            if sched in retained_schedules:
                primary_schedule = sched
            elif retained_schedules:
                primary_schedule = retained_schedules[0]
            elif added_schedules:
                primary_schedule = added_schedules[0]

        else:
            # Single schedule date/time/timezone update
            sched.scheduled_at = utc_naive
            sched.run_at = utc_naive
            sched.timezone = tz_str
            sched.status = ScheduleStatus.SCHEDULED.value
            sched.updated_at = now_naive
            sched.last_error = None
            primary_schedule = sched

        # Ensure post status is SCHEDULED
        if post:
            post.status = PostWorkflowStatus.SCHEDULED.value

        target_info = f" with targets: {', '.join(canonical_desired)}" if desired_raw is not None else ""
        log = ActivityLog(
            post_id=sched.post_id,
            action="POST_RESCHEDULED",
            details=f"Post rescheduled to {utc_naive.isoformat()} UTC ({tz_str}){target_info}",
            actor=actor,
        )
        db.add(log)

        db.commit()
        db.refresh(primary_schedule)
        return primary_schedule

    @classmethod
    def cancel_schedule(
        cls,
        db: Session,
        schedule_id: int,
        reason: Optional[str] = None,
        actor: str = "User",
        cancel_all_platforms: bool = False,
    ) -> ScheduledPost:
        """Cancel a scheduled post and return the post to APPROVED status if no other active schedules."""
        sched = db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
        if not sched:
            raise ValueError(f"Schedule with id {schedule_id} not found.")

        current_status = sched.status.upper() if sched.status else ""
        if current_status == ScheduleStatus.PUBLISHED.value:
            raise ValueError("Cannot cancel an already published post (PUBLISHED).")
        if current_status == ScheduleStatus.PUBLISHING.value:
            raise ValueError("Cannot cancel schedule while publication is in progress (PUBLISHING).")

        now_utc = get_utc_now()
        now_naive = now_utc.replace(tzinfo=None)

        if current_status != ScheduleStatus.CANCELLED.value:
            sched.status = ScheduleStatus.CANCELLED.value
            sched.cancelled_at = now_naive
            sched.updated_at = now_naive

        # If cancel_all_platforms is True, cancel all sibling active schedules for this post
        if cancel_all_platforms:
            other_active = db.query(ScheduledPost).filter(
                ScheduledPost.post_id == sched.post_id,
                ScheduledPost.id != sched.id,
                ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
            ).all()
            for other_s in other_active:
                other_s.status = ScheduleStatus.CANCELLED.value
                other_s.cancelled_at = now_naive
                other_s.updated_at = now_naive

        db.flush()

        # Revert or update parent post status based on remaining active schedules
        post = sched.post or db.query(Post).filter(Post.id == sched.post_id).first()
        if post:
            remaining_active = db.query(ScheduledPost).filter(
                ScheduledPost.post_id == sched.post_id,
                ScheduledPost.status.in_([ScheduleStatus.SCHEDULED.value, ScheduleStatus.PUBLISHING.value])
            ).all()

            if remaining_active:
                # Other platform schedules are still active; post remains SCHEDULED
                post.status = PostWorkflowStatus.SCHEDULED.value
                active_platforms = [s.platform for s in remaining_active if s.platform]
                if active_platforms:
                    post.target_platforms = active_platforms
            else:
                # No active schedules remaining; check if any were published
                any_published = db.query(ScheduledPost).filter(
                    ScheduledPost.post_id == sched.post_id,
                    ScheduledPost.status == ScheduleStatus.PUBLISHED.value
                ).first()
                if any_published:
                    post.status = PostWorkflowStatus.PUBLISHED.value
                else:
                    post.status = PostWorkflowStatus.APPROVED.value

        details = f"Schedule #{schedule_id} ({sched.platform}) cancelled. Reason: {reason}" if reason else f"Schedule #{schedule_id} ({sched.platform}) cancelled."
        log = ActivityLog(
            post_id=sched.post_id,
            action="SCHEDULE_CANCELLED",
            details=details,
            actor=actor,
        )
        db.add(log)

        db.commit()
        db.refresh(sched)
        if post:
            db.refresh(post)
        return sched

    @classmethod
    def get_due_posts(cls, db: Session, cutoff_time: Optional[datetime.datetime] = None) -> List[ScheduledPost]:
        """Fetch all scheduled posts due for publishing up to cutoff_time."""
        cutoff = cutoff_time or get_utc_now()
        if cutoff.tzinfo is not None:
            cutoff = cutoff.replace(tzinfo=None)

        return (
            db.query(ScheduledPost)
            .filter(
                ScheduledPost.status == ScheduleStatus.SCHEDULED.value,
                ScheduledPost.scheduled_at <= cutoff,
            )
            .order_by(ScheduledPost.scheduled_at.asc())
            .all()
        )

    @classmethod
    def claim_due_post(cls, db: Session, schedule_id: int) -> bool:
        """Atomically transition a scheduled post from SCHEDULED to PUBLISHING.

        Guarantees that multiple concurrent workers or scheduler intervals
        cannot execute the same scheduled post twice.
        """
        now_naive = get_utc_now().replace(tzinfo=None)

        rows_updated = (
            db.query(ScheduledPost)
            .filter(
                ScheduledPost.id == schedule_id,
                ScheduledPost.status == ScheduleStatus.SCHEDULED.value,
            )
            .update(
                {
                    ScheduledPost.status: ScheduleStatus.PUBLISHING.value,
                    ScheduledPost.updated_at: now_naive,
                },
                synchronize_session="fetch",
            )
        )
        db.commit()

        if rows_updated > 0:
            # Also update post status
            sched = db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
            if sched and sched.post:
                sched.post.status = PostWorkflowStatus.PUBLISHING.value
                db.commit()
            return True

        return False

    @classmethod
    def get_calendar_schedules(
        cls,
        db: Session,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        platform: Optional[str] = None,
        status: Optional[str] = None,
        include_cancelled: bool = False,
    ) -> List[ScheduledPost]:
        """Query scheduled posts for calendar display or listing with optional filters.
        Excludes CANCELLED schedules by default to keep the active calendar clean.
        """
        query = db.query(ScheduledPost)

        if start_date:
            s_naive = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
            query = query.filter(ScheduledPost.scheduled_at >= s_naive)

        if end_date:
            e_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date
            query = query.filter(ScheduledPost.scheduled_at <= e_naive)

        if platform:
            query = query.filter(ScheduledPost.platform == platform.upper())

        if status:
            query = query.filter(ScheduledPost.status == status.upper())
        elif not include_cancelled:
            # Clean active calendar: never show cancelled posts
            query = query.filter(ScheduledPost.status != ScheduleStatus.CANCELLED.value)

        return query.order_by(ScheduledPost.scheduled_at.asc()).all()

    @classmethod
    def get_schedule(cls, db: Session, schedule_id: int) -> Optional[ScheduledPost]:
        return db.query(ScheduledPost).filter(ScheduledPost.id == schedule_id).first()
