from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field

class ApprovalDecisionRequest(BaseModel):
    """Payload when a human reviewer approves a post."""
    reviewer: Optional[str] = "Human Reviewer"
    review_notes: Optional[str] = None

class ApprovalRejectionRequest(BaseModel):
    """Payload when a human reviewer rejects a post."""
    rejection_reason: str = Field(..., min_length=2, description="Mandatory reason explaining why the post was rejected.")
    reviewer: Optional[str] = "Human Reviewer"
    review_notes: Optional[str] = None

class ApprovalRegenerateRequest(BaseModel):
    """Payload when requesting regeneration from the approval queue."""
    feedback: Optional[str] = None
    reviewer: Optional[str] = "Human Reviewer"
    provider: Optional[str] = None

class ApprovalItemResponse(BaseModel):
    id: int
    post_id: int
    channel: str = "web"
    status: str
    reviewer: Optional[str] = None
    feedback: Optional[str] = None
    rejection_reason: Optional[str] = None
    review_notes: Optional[str] = None
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    # Enriched post details for convenient display in HITL Review queue
    topic: Optional[str] = None
    theme: Optional[str] = None
    tone: Optional[str] = None
    content_type: Optional[str] = None
    target_platforms: Optional[List[str]] = Field(default_factory=list)
    platform_contents: Optional[Dict[str, Any]] = Field(default_factory=dict)
    review_score: Optional[int] = None
    review_feedback: Optional[str] = None
    review_passed: Optional[bool] = None
    regeneration_count: int = 0
    generation_version: int = 1
    post_status: Optional[str] = None

    # Schedule metadata if post was scheduled or published
    schedule_id: Optional[int] = None
    schedule_status: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    scheduled_timezone: Optional[str] = None
    published_at: Optional[datetime] = None
    external_post_id: Optional[str] = None

    # Multi-platform publication state breakdown
    publication_state: Optional[str] = "UNSCHEDULED"
    published_targets: Optional[List[str]] = Field(default_factory=list)
    scheduled_targets: Optional[List[str]] = Field(default_factory=list)
    failed_targets: Optional[List[str]] = Field(default_factory=list)

    model_config = {"from_attributes": True}

class ApprovalActionResponse(BaseModel):
    success: bool
    action: str
    approval_id: int
    post_id: int
    approval_status: str
    post_status: str
    message: str
    details: Optional[Dict[str, Any]] = None
