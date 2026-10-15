from typing import TypedDict, Optional, Dict, Any, List

class ContentWorkflowState(TypedDict, total=False):
    """LangGraph workflow state tracking the complete lifecycle of a post.
    All persistent application state is anchored to the relational database.
    """
    # Core Post Identifiers
    post_id: Optional[int]
    approval_request_id: Optional[int]
    thread_id: Optional[str]

    # Generation Context Signals
    topic: str
    theme: str
    tone: str
    target_audience: str
    content_type: str
    desired_length: str
    platforms: List[str]
    keywords: List[str]
    cta_preference: Optional[str]

    # Generation Versioning & Tracking
    generation_version: int
    regeneration_count: int
    max_regenerations: int
    correction_count: int
    previous_content: Optional[Dict[str, str]]

    # AI Provider & Model Metadata
    provider: str
    model: str
    provider_used: str

    # Output Variants & Review Data
    variants: Dict[str, Any]
    quality_score: int
    quality_passed: bool
    review_feedback: Optional[str]
    dimension_scores: Dict[str, int]
    issues_detected: List[str]

    # Workflow Status
    # Standard states: draft, ai_review, awaiting_human_approval, approved, rejected, regenerating, failed
    workflow_status: str

    # Human-in-the-Loop Actions & Decisions
    human_action: Optional[str]  # "approve", "reject", "regenerate"
    reviewer: Optional[str]
    rejection_reason: Optional[str]
    review_notes: Optional[str]

    # Execution Metadata & Audit
    timestamps: Dict[str, str]
    error: Optional[str]
