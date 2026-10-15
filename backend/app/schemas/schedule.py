import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

class ScheduleCreateRequest(BaseModel):
    post_id: int = Field(..., description="ID of the approved post to schedule")
    scheduled_at: datetime.datetime = Field(..., description="Target publication datetime (ISO 8601)")
    timezone: str = Field(default="UTC", description="Timezone name, e.g. UTC, America/New_York")
    platform: Optional[str] = Field(default=None, description="Target publication platform, e.g. TWITTER, LINKEDIN")
    platforms: Optional[List[str]] = Field(default=None, description="Optional list of target platforms to schedule")
    target_platforms: Optional[List[str]] = Field(default=None, description="Optional list of target platforms to schedule")
    idempotency_key: Optional[str] = Field(default=None, description="Optional client idempotency key for deduplication")

class ScheduleRescheduleRequest(BaseModel):
    scheduled_at: datetime.datetime = Field(..., description="New publication datetime (ISO 8601)")
    timezone: Optional[str] = Field(default=None, description="Updated timezone if changed")
    platform: Optional[str] = Field(default=None, description="Optional single updated target platform")
    platforms: Optional[List[str]] = Field(default=None, description="Optional list of updated target platforms")
    target_platforms: Optional[List[str]] = Field(default=None, description="Optional list of updated target platforms")
    idempotency_key: Optional[str] = Field(default=None, description="Optional client idempotency key for deduplication")

class ScheduleCancelRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Optional cancellation reason")
    cancel_all_platforms: Optional[bool] = Field(default=False, description="Whether to cancel all sibling platform schedules for this post")

class PublishLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    schedule_id: Optional[int] = None
    platform: str
    provider: str
    is_mock: bool
    status: str
    retry_count: int = 0
    external_post_id: Optional[str] = None
    response_payload: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    attempted_at: Optional[datetime.datetime] = None
    completed_at: Optional[datetime.datetime] = None
    published_at: Optional[datetime.datetime] = None

class ScheduledPostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    post_id: int
    platform: str
    target_platforms: Optional[List[str]] = None
    current_target_platforms: Optional[List[str]] = None
    historical_published_platforms: Optional[List[str]] = None
    job_id: Optional[str] = None
    scheduled_at: datetime.datetime
    timezone: str = "UTC"
    status: str
    retry_count: int = 0
    last_error: Optional[str] = None
    idempotency_key: Optional[str] = None
    published_at: Optional[datetime.datetime] = None
    cancelled_at: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    # Enriched post details for calendar UI convenience
    post_content: Optional[str] = None
    platform_contents: Optional[Dict[str, Any]] = None
    sibling_schedules: Optional[List[Dict[str, Any]]] = None
    post_theme: Optional[str] = None
    post_workflow_status: Optional[str] = None
    quality_score: Optional[int] = None

class ScheduleActionResponse(BaseModel):
    success: bool
    message: str
    schedule: Optional[ScheduledPostResponse] = None

class ScheduleListResponse(BaseModel):
    success: bool
    count: int
    data: List[ScheduledPostResponse]
