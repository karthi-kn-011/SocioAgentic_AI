import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..config import settings
from ..database.models import (
    PublishLog,
    Post,
    ActivityLog,
    PlatformType,
    normalize_platform_name,
)
from ..schemas.analytics import (
    AnalyticsOverviewResponse,
    PublicationLogItem,
    PublicationLogsListResponse,
)
from ..schemas.activity import (
    ActivityLogItem,
    ActivityLogsListResponse,
)


def get_analytics_overview(db: Session) -> AnalyticsOverviewResponse:
    """Calculates overall publication stats, delivery rates, AI review averages, and platform breakdowns."""
    # 1. Total publications attempted
    total_publications = db.query(func.count(PublishLog.id)).scalar() or 0

    # 2. Successful and failed publication counts
    # Both "SUCCESS" and "SIMULATED" indicate successful delivery / mock delivery
    successful_publications = (
        db.query(func.count(PublishLog.id))
        .filter(PublishLog.status.in_(["SUCCESS", "SIMULATED"]))
        .scalar()
        or 0
    )
    failed_publications = (
        db.query(func.count(PublishLog.id))
        .filter(PublishLog.status == "FAILED")
        .scalar()
        or 0
    )

    # 3. Success rate
    if total_publications > 0:
        success_rate = round((successful_publications / total_publications) * 100.0, 1)
    else:
        success_rate = 0.0

    # 4. Average AI review score across reviewed posts (score > 0)
    avg_score_raw = (
        db.query(func.avg(Post.review_score))
        .filter(Post.review_score.isnot(None), Post.review_score > 0)
        .scalar()
    )

    average_ai_score = round(float(avg_score_raw), 1) if avg_score_raw is not None else None

    # 5. Platform breakdown from PublishLog
    platform_rows = (
        db.query(PublishLog.platform, func.count(PublishLog.id))
        .group_by(PublishLog.platform)
        .all()
    )
    platform_breakdown: Dict[str, int] = {}
    for platform_val, count in platform_rows:
        if hasattr(platform_val, "value"):
            p_name = platform_val.value
        else:
            p_name = str(platform_val)
        platform_breakdown[p_name] = count

    return AnalyticsOverviewResponse(
        total_publications=total_publications,
        successful_publications=successful_publications,
        failed_publications=failed_publications,
        success_rate=success_rate,
        average_ai_score=average_ai_score,
        platform_breakdown=platform_breakdown,
        mock_publishing=settings.MOCK_SOCIAL_PUBLISHING,
        mock_slack=settings.SLACK_MOCK_MODE,
        environment=settings.ENVIRONMENT,
    )


def get_publication_logs(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    platform: Optional[str] = None,
    status: Optional[str] = None,
) -> PublicationLogsListResponse:
    """Returns paginated, filtered publication execution logs."""
    query = db.query(PublishLog)

    if platform and platform.strip():
        try:
            canonical_platform = normalize_platform_name(platform.strip())
            query = query.filter(PublishLog.platform == canonical_platform)
        except ValueError:
            query = query.filter(PublishLog.platform == platform.strip().upper())

    if status and status.strip():
        query = query.filter(PublishLog.status == status.strip().upper())

    total = query.count()
    records = query.order_by(PublishLog.id.desc()).offset(skip).limit(limit).all()

    return PublicationLogsListResponse(
        items=[PublicationLogItem.model_validate(r) for r in records],
        total=total,
        skip=skip,
        limit=limit,
    )


def get_activity_logs(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    action: Optional[str] = None,
    actor: Optional[str] = None,
    post_id: Optional[int] = None,
    start_date: Optional[datetime.datetime] = None,
    end_date: Optional[datetime.datetime] = None,
    search: Optional[str] = None,
) -> ActivityLogsListResponse:
    """Returns server-side paginated and filtered activity/audit logs."""
    query = db.query(ActivityLog)

    if action and action.strip() and action.strip().upper() != "ALL":
        query = query.filter(ActivityLog.action == action.strip())

    if actor and actor.strip():
        query = query.filter(ActivityLog.actor.ilike(f"%{actor.strip()}%"))

    if post_id is not None:
        query = query.filter(ActivityLog.post_id == post_id)

    if start_date:
        query = query.filter(ActivityLog.created_at >= start_date)

    if end_date:
        query = query.filter(ActivityLog.created_at <= end_date)

    if search and search.strip():
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ActivityLog.action.ilike(search_pattern),
                ActivityLog.actor.ilike(search_pattern),
                ActivityLog.details.ilike(search_pattern),
            )
        )

    total = query.count()
    records = query.order_by(ActivityLog.id.desc()).offset(skip).limit(limit).all()

    return ActivityLogsListResponse(
        items=[ActivityLogItem.model_validate(r) for r in records],
        total=total,
        skip=skip,
        limit=limit,
    )
