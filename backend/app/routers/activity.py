import datetime
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..schemas.activity import ActivityLogsListResponse
from ..services.analytics_service import get_activity_logs

logger = logging.getLogger("ActivityRouter")

router = APIRouter(prefix="/activity", tags=["Activity"])


@router.get("", response_model=ActivityLogsListResponse, status_code=status.HTTP_200_OK)
@router.get("/", response_model=ActivityLogsListResponse, status_code=status.HTTP_200_OK, include_in_schema=False)
def list_activity_logs(
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=500, description="Page size limit"),
    action: Optional[str] = Query(None, description="Filter by event action (e.g. POST_PUBLISHED)"),
    actor: Optional[str] = Query(None, description="Filter by actor name"),
    post_id: Optional[int] = Query(None, description="Filter by associated post ID"),
    start_date: Optional[datetime.datetime] = Query(None, description="Filter events on or after ISO timestamp"),
    end_date: Optional[datetime.datetime] = Query(None, description="Filter events on or before ISO timestamp"),
    search: Optional[str] = Query(None, description="Free-text search across action, actor, and details"),
    db: Session = Depends(get_db),
):
    """Returns server-side paginated and filtered activity and audit trail logs."""
    return get_activity_logs(
        db=db,
        skip=skip,
        limit=limit,
        action=action,
        actor=actor,
        post_id=post_id,
        start_date=start_date,
        end_date=end_date,
        search=search,
    )
