import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..schemas.analytics import (
    AnalyticsOverviewResponse,
    PublicationLogsListResponse,
)
from ..services.analytics_service import (
    get_analytics_overview,
    get_publication_logs,
)

logger = logging.getLogger("AnalyticsRouter")

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/overview", response_model=AnalyticsOverviewResponse, status_code=status.HTTP_200_OK)
def get_overview(db: Session = Depends(get_db)):
    """Returns aggregated publication statistics, delivery rate, average AI score, and platform breakdown."""
    return get_analytics_overview(db)


@router.get("/publications", response_model=PublicationLogsListResponse, status_code=status.HTTP_200_OK)
def list_publication_logs(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=500, description="Page size limit"),
    platform: Optional[str] = Query(None, description="Optional platform filter (e.g. TWITTER, LINKEDIN)"),
    status: Optional[str] = Query(None, description="Optional status filter (e.g. SUCCESS, FAILED)"),
    db: Session = Depends(get_db),
):
    """Returns paginated publication execution audit logs directly from PublishLog records."""
    return get_publication_logs(
        db=db,
        skip=skip,
        limit=limit,
        platform=platform,
        status=status,
    )
