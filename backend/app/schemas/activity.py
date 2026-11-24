import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ActivityLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: Optional[int] = None
    action: str
    actor: str
    details: Optional[str] = None
    created_at: Optional[datetime.datetime] = None


class ActivityLogsListResponse(BaseModel):
    items: List[ActivityLogItem]
    total: int
    skip: int = 0
    limit: int = 50
