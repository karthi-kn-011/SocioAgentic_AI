import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..config import settings
from ..database.database import get_db
from ..schemas.common import HealthStatus

logger = logging.getLogger("HealthRouter")

router = APIRouter(prefix="/health", tags=["System Health"])

@router.get("", response_model=HealthStatus, status_code=status.HTTP_200_OK)
@router.get("/", response_model=HealthStatus, status_code=status.HTTP_200_OK, include_in_schema=False)
async def check_system_health(db: Session = Depends(get_db)):
    """Comprehensive health check validating database connectivity and runtime modes."""
    db_connected = False
    try:
        db.execute(text("SELECT 1"))
        db_connected = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")

    return HealthStatus(
        status="healthy" if db_connected else "degraded",
        service=settings.APP_NAME,
        environment=settings.ENVIRONMENT,
        database_connected=db_connected,
        mock_publishing=settings.MOCK_SOCIAL_PUBLISHING,
        mock_slack=settings.SLACK_MOCK_MODE,
        version="1.0.0"
    )

@router.get("/activity")
def get_activity_feed(limit: int = 50, db: Session = Depends(get_db)):
    """Returns recent real activity logs from the database."""
    from ..database.models import ActivityLog
    logs = db.query(ActivityLog).order_by(ActivityLog.id.desc()).limit(limit).all()
    return [
        {
            "id": l.id,
            "post_id": l.post_id,
            "action": l.action,
            "actor": l.actor,
            "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None
        }
        for l in logs
    ]

