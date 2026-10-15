import enum
import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey, Boolean, JSON, Float
from sqlalchemy.orm import relationship
from .database import Base

def get_utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

class PostWorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    AI_REVIEW = "ai_review"
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    REGENERATING = "regenerating"
    FAILED = "failed"
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            vl = value.lower()
            if vl in ("pending_approval", "pending"):
                return cls.AWAITING_HUMAN_APPROVAL
            if vl == "reviewing":
                return cls.AI_REVIEW
            for m in cls:
                if m.value == vl or m.name.lower() == vl:
                    return m
        return super()._missing_(value)

PostStatus = PostWorkflowStatus
PostStatus.PENDING_APPROVAL = PostStatus.AWAITING_HUMAN_APPROVAL
PostStatus.REVIEWING = PostStatus.AI_REVIEW

class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            vu = value.upper()
            for m in cls:
                if m.value == vu or m.name == vu:
                    return m
        return super()._missing_(value)

VALID_APPROVAL_TRANSITIONS = {
    ApprovalStatus.PENDING: {ApprovalStatus.APPROVED, ApprovalStatus.REJECTED, ApprovalStatus.CANCELLED},
    ApprovalStatus.APPROVED: set(),
    ApprovalStatus.REJECTED: set(),
    ApprovalStatus.CANCELLED: set(),
}

from typing import Optional, List, Dict, Any

SUPPORTED_PLATFORMS = {"TWITTER", "LINKEDIN", "META_FACEBOOK", "META_INSTAGRAM"}

PLATFORM_ALIASES = {
    "TWITTER": "TWITTER",
    "X": "TWITTER",
    "LINKEDIN": "LINKEDIN",
    "FACEBOOK": "META_FACEBOOK",
    "META_FACEBOOK": "META_FACEBOOK",
    "FB": "META_FACEBOOK",
    "INSTAGRAM": "META_INSTAGRAM",
    "META_INSTAGRAM": "META_INSTAGRAM",
    "IG": "META_INSTAGRAM",
}

class PlatformType(str, enum.Enum):
    TWITTER = "TWITTER"
    LINKEDIN = "LINKEDIN"
    META_FACEBOOK = "META_FACEBOOK"
    META_INSTAGRAM = "META_INSTAGRAM"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            vu = value.strip().upper()
            if vu in PLATFORM_ALIASES:
                canon = PLATFORM_ALIASES[vu]
                for m in cls:
                    if m.value == canon:
                        return m
        return super()._missing_(value)

def normalize_platform_name(val: Any, allow_none: bool = False, default_if_none: Optional[str] = None) -> str:
    """Normalizes any platform string/alias to its canonical PlatformType string.

    Rejects unsupported platform names explicitly with ValueError.
    Preserves default only when input is omitted/None and default_if_none is provided.
    """
    if val is None or (isinstance(val, str) and not val.strip()):
        if default_if_none is not None or allow_none:
            return default_if_none or "TWITTER"
        raise ValueError("Platform name cannot be empty or null.")

    if hasattr(val, "value"):
        val = val.value

    val_str = str(val).strip().upper()
    if val_str in PLATFORM_ALIASES:
        return PLATFORM_ALIASES[val_str]

    supported_list = ", ".join(sorted(SUPPORTED_PLATFORMS))
    raise ValueError(f"Unsupported platform '{val}'. Supported platforms are: {supported_list}.")

def normalize_platform_type(val: Any) -> PlatformType:
    """Normalizes any platform representation to PlatformType enum."""
    name = normalize_platform_name(val)
    return PlatformType(name)

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(500), nullable=False)
    theme = Column(String(100), default="Thought Leadership")
    tone = Column(String(100), default="Professional & Engaging")
    raw_content = Column(Text, nullable=True)
    platform_contents = Column(JSON, default=dict)
    target_platforms = Column(JSON, default=list)
    status = Column(Enum(PostStatus, values_callable=lambda x: [e.value for e in x]), default=PostStatus.DRAFT, index=True)

    # Versioning & Iterations
    regeneration_count = Column(Integer, default=0)
    generation_version = Column(Integer, default=1)

    # Review Metrics
    review_score = Column(Integer, default=0)
    review_feedback = Column(Text, nullable=True)
    review_passed = Column(Boolean, default=False)

    # Scheduling & Execution
    scheduled_time = Column(DateTime, nullable=True, index=True)
    published_at = Column(DateTime, nullable=True)

    # LangGraph Thread Correlation ID
    thread_id = Column(String(100), nullable=True, index=True)

    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    # Relationships
    approvals = relationship("ApprovalRequest", back_populates="post", cascade="all, delete-orphan")
    scheduled_posts = relationship("ScheduledPost", back_populates="post", cascade="all, delete-orphan")
    publish_logs = relationship("PublishLog", back_populates="post", cascade="all, delete-orphan")
    analytics_metrics = relationship("AnalyticsMetrics", back_populates="post", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="post")

    def get_platform_content(self, platform_name: Optional[str] = None, strict: bool = True) -> Optional[str]:
        """Returns the platform-specific text content for the designated platform.

        Strict validation:
        - When strict=True: strictly searches for platform_name's variant in platform_contents.
          Does NOT silently fall back to other platform variants or generic topic text.
          If platform_contents is not present (legacy Phase 5 single-platform record)
          and the platform matches the post's primary platform, returns raw_content.
        - Rejects empty, whitespace-only, and invalid content by returning None.
        """
        def _clean_text(val):
            if val is None:
                return None
            if isinstance(val, dict):
                val = val.get("content") or val.get("text") or val.get("raw_content")
            if not isinstance(val, str):
                val = str(val) if val is not None else ""
            cleaned = val.strip()
            return cleaned if cleaned else None

        target_platform = platform_name or self.platform
        try:
            norm = normalize_platform_name(target_platform, allow_none=True, default_if_none="TWITTER")
        except ValueError:
            return None

        # Look in platform_contents
        if self.platform_contents and isinstance(self.platform_contents, dict):
            matching_aliases = [k for k, v in PLATFORM_ALIASES.items() if v == norm]
            candidates = [norm, norm.lower()] + matching_aliases + [a.lower() for a in matching_aliases]

            for c in candidates:
                if c in self.platform_contents:
                    txt = _clean_text(self.platform_contents[c])
                    if txt:
                        return txt

        # Legacy compatibility: if post was saved without platform_contents (e.g. Phase 5 tests)
        # and this query is for the post's primary platform, return raw_content
        post_primary = normalize_platform_name(self.platform, allow_none=True, default_if_none="TWITTER")
        if (not self.platform_contents or not isinstance(self.platform_contents, dict)) and norm == post_primary:
            txt = _clean_text(self.raw_content)
            if txt:
                return txt

        # Non-strict fallback (e.g. for display when no variant found)
        if not strict:
            txt = _clean_text(self.raw_content)
            if txt:
                return txt
            return self.topic or None

        return None

    def has_platform_content(self, platform_name: str) -> bool:
        """Checks whether valid, non-empty platform content exists for the given platform."""
        return self.get_platform_content(platform_name, strict=True) is not None

    @property
    def content(self) -> str:
        if self.raw_content and self.raw_content.strip():
            return self.raw_content.strip()
        cnt = self.get_platform_content(self.platform, strict=False)
        return cnt or self.topic or ""

    @content.setter
    def content(self, value: str):
        self.raw_content = value
        if not self.topic:
            self.topic = value[:100] if value else "Untitled Post"

    @property
    def platform(self) -> str:
        if self.target_platforms and isinstance(self.target_platforms, list) and len(self.target_platforms) > 0:
            return normalize_platform_name(self.target_platforms[0], allow_none=True, default_if_none="TWITTER")
        return "TWITTER"

    @platform.setter
    def platform(self, value):
        norm = normalize_platform_name(value)
        if not self.target_platforms or not isinstance(self.target_platforms, list):
            self.target_platforms = [norm]
        elif norm not in self.target_platforms:
            self.target_platforms = [norm] + [p for p in self.target_platforms if p != norm]

    @property
    def quality_score(self) -> int:
        return self.review_score or 0

    @quality_score.setter
    def quality_score(self, value: int):
        self.review_score = value

    @property
    def version(self) -> int:
        return self.generation_version or 1

    @version.setter
    def version(self, value: int):
        self.generation_version = value

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    channel = Column(String(50), default="web")  # "web", "slack"
    message_ts = Column(String(100), nullable=True)
    status = Column(String(50), default=ApprovalStatus.PENDING.value)  # PENDING, APPROVED, REJECTED, CANCELLED
    reviewer = Column(String(100), nullable=True)
    feedback = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    review_notes = Column(Text, nullable=True)
    requested_at = Column(DateTime, default=get_utc_now)
    reviewed_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    post = relationship("Post", back_populates="approvals")


class SocialAccount(Base):
    __tablename__ = "social_accounts"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(Enum(PlatformType), nullable=False, index=True)
    account_name = Column(String(150), nullable=False)
    account_id = Column(String(150), nullable=True)
    encrypted_access_token = Column(Text, nullable=True)
    encrypted_refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

class ScheduleStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    CANCELLED = "CANCELLED"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            vu = value.upper()
            if vu in ("PENDING", "PENDING_PUBLISH"):
                return cls.SCHEDULED
            if vu in ("RUNNING", "IN_PROGRESS"):
                return cls.PUBLISHING
            if vu in ("COMPLETED", "SUCCESS"):
                return cls.PUBLISHED
            if vu in ("FAILED", "ERROR"):
                return cls.PUBLISH_FAILED
            for m in cls:
                if m.value == vu or m.name == vu:
                    return m
        return super()._missing_(value)

VALID_SCHEDULE_TRANSITIONS = {
    ScheduleStatus.SCHEDULED: {ScheduleStatus.PUBLISHING, ScheduleStatus.CANCELLED},
    ScheduleStatus.PUBLISHING: {ScheduleStatus.PUBLISHED, ScheduleStatus.PUBLISH_FAILED},
    ScheduleStatus.PUBLISH_FAILED: {ScheduleStatus.SCHEDULED, ScheduleStatus.CANCELLED},
    ScheduleStatus.PUBLISHED: set(),
    ScheduleStatus.CANCELLED: set(),
}

class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(50), nullable=True, default="TWITTER")
    target_platforms = Column(JSON, default=list)
    job_id = Column(String(100), unique=True, index=True, nullable=True)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    run_at = Column(DateTime, nullable=True, index=True)  # Legacy compatibility
    timezone = Column(String(50), default="UTC")
    status = Column(String(50), default=ScheduleStatus.SCHEDULED.value, index=True)  # SCHEDULED, PUBLISHING, PUBLISHED, PUBLISH_FAILED, CANCELLED
    retry_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    idempotency_key = Column(String(128), unique=True, index=True, nullable=True)
    published_at = Column(DateTime, nullable=True)
    executed_at = Column(DateTime, nullable=True)  # Legacy compatibility
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    post = relationship("Post", back_populates="scheduled_posts")
    publish_logs = relationship("PublishLog", back_populates="scheduled_post")

    def __init__(self, **kwargs):
        if "scheduled_at" in kwargs and "run_at" not in kwargs:
            kwargs["run_at"] = kwargs["scheduled_at"]
        elif "run_at" in kwargs and "scheduled_at" not in kwargs:
            kwargs["scheduled_at"] = kwargs["run_at"]
        super().__init__(**kwargs)

class PublishLog(Base):
    __tablename__ = "publish_logs"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    schedule_id = Column(Integer, ForeignKey("scheduled_posts.id", ondelete="SET NULL"), nullable=True, index=True)
    platform = Column(Enum(PlatformType), nullable=False, index=True)
    provider = Column(String(100), default="MockPublisher")
    is_mock = Column(Boolean, default=True)
    status = Column(String(50), nullable=False)  # SUCCESS, FAILED, SIMULATED
    retry_count = Column(Integer, default=0)
    idempotency_key = Column(String(128), nullable=True, index=True)
    external_post_id = Column(String(255), nullable=True)
    response_payload = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    attempted_at = Column(DateTime, default=get_utc_now)
    completed_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, default=get_utc_now)

    post = relationship("Post", back_populates="publish_logs")
    scheduled_post = relationship("ScheduledPost", back_populates="publish_logs")

class AnalyticsMetrics(Base):
    __tablename__ = "analytics_metrics"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(Enum(PlatformType), nullable=False)
    metric_type = Column(String(50), nullable=False)  # impressions, likes, shares, comments, clicks
    metric_value = Column(Integer, default=0)
    data_source = Column(String(50), default="platform_api")  # platform_api, mock_simulated, unavailable
    recorded_at = Column(DateTime, default=get_utc_now)

    post = relationship("Post", back_populates="analytics_metrics")

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    details = Column(String(500), nullable=True)
    actor = Column(String(100), default="System")
    created_at = Column(DateTime, default=get_utc_now)

    post = relationship("Post", back_populates="activity_logs")

class OAuthState(Base):
    """Database-backed OAuth state & PKCE persistence with expiration."""
    __tablename__ = "oauth_states"

    state = Column(String(128), primary_key=True, index=True)
    platform = Column(String(50), nullable=False)
    code_verifier = Column(Text, nullable=True)
    redirect_uri = Column(Text, nullable=True)
    expires_at = Column(Float, nullable=False)  # Epoch timestamp in seconds
    created_at = Column(DateTime, default=get_utc_now)
