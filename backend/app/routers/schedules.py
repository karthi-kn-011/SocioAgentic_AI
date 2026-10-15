import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.database.database import get_db
from backend.app.database.models import ScheduledPost, Post, PublishLog
from backend.app.services.schedule_service import ScheduleService
from backend.app.services.publishing_service import PublishingService
from backend.app.schemas.schedule import (
    ScheduleCreateRequest,
    ScheduleRescheduleRequest,
    ScheduleCancelRequest,
    ScheduledPostResponse,
    ScheduleActionResponse,
    ScheduleListResponse,
    PublishLogResponse,
)

router = APIRouter(prefix="/schedules", tags=["Schedules"])

def _enrich_scheduled_response(sched: ScheduledPost) -> ScheduledPostResponse:
    post = sched.post
    platform_name = sched.platform or (post.platform.value if post and hasattr(post.platform, "value") else str(post.platform if post else "TWITTER"))
    from backend.app.database.models import normalize_platform_name
    canonical_platform = normalize_platform_name(platform_name, allow_none=True, default_if_none="TWITTER")

    content = None
    if post:
        if hasattr(post, "get_platform_content"):
            content = post.get_platform_content(canonical_platform, strict=True)
            if not content:
                content = post.get_platform_content(canonical_platform, strict=False)
        elif hasattr(post, "content"):
            content = post.content

    current_targets = post.target_platforms if post and isinstance(post.target_platforms, list) else [canonical_platform]

    historical_published = []
    sibling_schedules = []
    if post and hasattr(post, "scheduled_posts") and post.scheduled_posts:
        for s in post.scheduled_posts:
            if s.status == "PUBLISHED" and s.platform and s.platform not in historical_published:
                historical_published.append(s.platform)
            if s.status != "CANCELLED":
                try:
                    s_plat = normalize_platform_name(s.platform, allow_none=True, default_if_none=s.platform)
                except ValueError:
                    s_plat = s.platform
                sibling_schedules.append({
                    "id": s.id,
                    "platform": s_plat,
                    "status": s.status,
                    "scheduled_at": s.scheduled_at.isoformat() if s.scheduled_at else None,
                    "published_at": s.published_at.isoformat() if s.published_at else None,
                })

    all_platform_contents = {}
    if post:
        for p_name in current_targets:
            c_text = post.get_platform_content(p_name, strict=True)
            if c_text:
                all_platform_contents[p_name] = c_text
        if hasattr(post, "platform_contents") and isinstance(post.platform_contents, dict):
            for k, v in post.platform_contents.items():
                try:
                    norm_k = normalize_platform_name(k, allow_none=True, default_if_none=k)
                except ValueError:
                    norm_k = k
                if norm_k not in all_platform_contents and v:
                    cleaned = post.get_platform_content(norm_k, strict=False)
                    if cleaned:
                        all_platform_contents[norm_k] = cleaned

    return ScheduledPostResponse(
        id=sched.id,
        post_id=sched.post_id,
        platform=canonical_platform,
        target_platforms=current_targets,
        current_target_platforms=current_targets,
        historical_published_platforms=historical_published,
        job_id=sched.job_id,
        scheduled_at=sched.scheduled_at,
        timezone=sched.timezone or "UTC",
        status=sched.status,
        retry_count=sched.retry_count,
        last_error=sched.last_error,
        idempotency_key=sched.idempotency_key,
        published_at=sched.published_at,
        cancelled_at=sched.cancelled_at,
        created_at=sched.created_at,
        updated_at=sched.updated_at,
        post_content=content,
        platform_contents=all_platform_contents,
        sibling_schedules=sibling_schedules,
        post_theme=post.theme if post else None,
        post_workflow_status=post.status.value if post and hasattr(post.status, "value") else str(post.status if post else None),
        quality_score=post.quality_score if post else None,
    )

@router.post("", response_model=ScheduledPostResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(req: ScheduleCreateRequest, db: Session = Depends(get_db)):
    """Schedule an approved post for publishing."""
    try:
        sched = ScheduleService.schedule_post(
            db=db,
            post_id=req.post_id,
            scheduled_at=req.scheduled_at,
            timezone=req.timezone,
            platform=req.platform,
            platforms=req.platforms or req.target_platforms,
            idempotency_key=req.idempotency_key,
            actor="User",
        )
        return _enrich_scheduled_response(sched)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.get("", response_model=ScheduleListResponse)
def list_schedules(
    start_date: Optional[datetime.datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime.datetime] = Query(None, description="End date filter"),
    platform: Optional[str] = Query(None, description="Platform filter"),
    status: Optional[str] = Query(None, description="Status filter: SCHEDULED, PUBLISHED, etc."),
    include_cancelled: bool = Query(False, description="Whether to include cancelled schedules"),
    db: Session = Depends(get_db),
):
    """Retrieve scheduled posts with optional filters for calendar or list views."""
    schedules = ScheduleService.get_calendar_schedules(
        db=db,
        start_date=start_date,
        end_date=end_date,
        platform=platform,
        status=status,
        include_cancelled=include_cancelled,
    )
    items = [_enrich_scheduled_response(s) for s in schedules]
    return ScheduleListResponse(success=True, count=len(items), data=items)

@router.get("/upcoming", response_model=ScheduleListResponse)
def get_upcoming_schedules(
    limit: int = Query(10, ge=1, le=50, description="Max upcoming posts to retrieve"),
    db: Session = Depends(get_db),
):
    """Fetch next upcoming scheduled posts."""
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    schedules = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.status == "SCHEDULED", ScheduledPost.scheduled_at >= now_utc)
        .order_by(ScheduledPost.scheduled_at.asc())
        .limit(limit)
        .all()
    )
    items = [_enrich_scheduled_response(s) for s in schedules]
    return ScheduleListResponse(success=True, count=len(items), data=items)

@router.get("/{schedule_id}", response_model=ScheduledPostResponse)
def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """Fetch details of a scheduled post by ID."""
    sched = ScheduleService.get_schedule(db, schedule_id)
    if not sched:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Schedule {schedule_id} not found")
    return _enrich_scheduled_response(sched)

@router.put("/{schedule_id}", response_model=ScheduledPostResponse)
def reschedule_post(
    schedule_id: int,
    req: ScheduleRescheduleRequest,
    db: Session = Depends(get_db),
):
    """Reschedule an existing scheduled post."""
    try:
        updated = ScheduleService.reschedule_post(
            db=db,
            schedule_id=schedule_id,
            new_scheduled_at=req.scheduled_at,
            new_timezone=req.timezone,
            platform=req.platform,
            platforms=req.platforms or req.target_platforms,
            idempotency_key=req.idempotency_key,
            actor="User",
        )
        return _enrich_scheduled_response(updated)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.delete("/{schedule_id}", response_model=ScheduleActionResponse)
def cancel_schedule(
    schedule_id: int,
    cancel_all: bool = Query(False, description="Whether to cancel all sibling platform schedules for this post"),
    req: Optional[ScheduleCancelRequest] = None,
    db: Session = Depends(get_db),
):
    """Cancel a scheduled post and return post to APPROVED status if no active schedules remain."""
    reason = req.reason if req else None
    cancel_all_flag = cancel_all or (req.cancel_all_platforms if req and hasattr(req, "cancel_all_platforms") else False)
    try:
        cancelled = ScheduleService.cancel_schedule(
            db=db,
            schedule_id=schedule_id,
            reason=reason,
            actor="User",
            cancel_all_platforms=cancel_all_flag,
        )
        return ScheduleActionResponse(
            success=True,
            message="Schedule cancelled successfully.",
            schedule=_enrich_scheduled_response(cancelled),
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.post("/{schedule_id}/publish-now", response_model=ScheduleActionResponse)
def publish_now(schedule_id: int, db: Session = Depends(get_db)):
    """Immediately trigger publishing of a scheduled post."""
    try:
        success, message = PublishingService.publish_now(db=db, schedule_id=schedule_id, actor="User")
        sched = ScheduleService.get_schedule(db, schedule_id)
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message)
        return ScheduleActionResponse(
            success=True,
            message=message,
            schedule=_enrich_scheduled_response(sched) if sched else None,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)

@router.get("/{schedule_id}/logs", response_model=List[PublishLogResponse])
def get_schedule_logs(schedule_id: int, db: Session = Depends(get_db)):
    """Get all publication audit log attempts for a schedule."""
    logs = (
        db.query(PublishLog)
        .filter(PublishLog.schedule_id == schedule_id)
        .order_by(PublishLog.id.desc())
        .all()
    )
    return [
        PublishLogResponse(
            id=l.id,
            post_id=l.post_id,
            schedule_id=l.schedule_id,
            platform=l.platform.value if hasattr(l.platform, "value") else str(l.platform),
            provider=l.provider or "MockPublisher",
            is_mock=bool(l.is_mock),
            status=l.status,
            retry_count=l.retry_count or 0,
            external_post_id=l.external_post_id,
            response_payload=l.response_payload,
            error_message=l.error_message,
            attempted_at=l.attempted_at,
            completed_at=l.completed_at,
            published_at=l.published_at,
        )
        for l in logs
    ]
