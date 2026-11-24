import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, field_validator


class AnalyticsOverviewResponse(BaseModel):
    total_publications: int
    successful_publications: int
    failed_publications: int
    success_rate: float
    average_ai_score: Optional[float] = None
    platform_breakdown: Dict[str, int]
    mock_publishing: bool
    mock_slack: bool
    environment: str


class PublicationLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    schedule_id: Optional[int] = None
    platform: str
    provider: str
    is_mock: bool
    status: str
    retry_count: int = 0
    idempotency_key: Optional[str] = None
    external_post_id: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    attempted_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    published_at: Optional[datetime.datetime] = None

    @field_validator("platform", mode="before")
    @classmethod
    def serialize_platform(cls, v):
        if hasattr(v, "value"):
            return v.value
        return str(v) if v is not None else ""


class PublicationLogsListResponse(BaseModel):
    items: List[PublicationLogItem]
    total: int
    skip: int = 0
    limit: int = 50
