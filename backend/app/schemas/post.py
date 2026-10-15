from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class ContentGenerationContext(BaseModel):
    """Rich multi-factor generation context provided to LLM providers."""
    topic: str = Field(..., min_length=2, max_length=1000, description="Core topic or user seed idea")
    theme: str = Field("Thought Leadership", description="Content archetype (Educational, Promotional, Thought Leadership, etc.)")
    platforms: List[str] = Field(default_factory=lambda: ["TWITTER", "LINKEDIN", "META_FACEBOOK", "META_INSTAGRAM"])
    tone: str = Field("Professional & Engaging", description="Voice persona")
    target_audience: str = Field("General Professionals", description="Target audience segment")
    content_type: str = Field("Quick Insight", description="Post format archetype")
    desired_length: str = Field("Medium", description="Short, Medium, or Long")
    keywords: List[str] = Field(default_factory=list, description="Priority topical keywords to integrate")
    hashtags_preference: List[str] = Field(default_factory=list, description="Preferred hashtags")
    cta_preference: Optional[str] = Field(None, description="Preferred call to action")
    previous_content: Optional[Dict[str, str]] = Field(None, description="Prior generation draft to vary away from")
    variation_index: int = Field(0, description="Increments on regeneration to force alternate hook and angle")

class PostVariant(BaseModel):
    """Structured output for a platform-specific post draft."""
    platform: str
    content: str
    character_count: int
    character_limit: int
    hook_type: str = "Insight"
    hashtags: List[str] = Field(default_factory=list)
    call_to_action: Optional[str] = None

class QualityRubricResult(BaseModel):
    """Evaluation scorecard across the 7 quality critique dimensions."""
    grammar_score: int = 90
    topic_relevance_score: int = 90
    theme_adherence_score: int = 90
    platform_suitability_score: int = 90
    naturalness_score: int = 90
    engagement_score: int = 88
    safety_score: int = 98
    composite_score: int = 90
    passed: bool = True
    critique_feedback: str = "Content successfully passed all quality guidelines."
    issues_detected: List[str] = Field(default_factory=list)

class StructuredPostGeneration(BaseModel):
    """Complete structured generation payload."""
    post_id: Optional[int] = None
    topic: str
    theme: str
    tone: str
    target_audience: str
    content_type: str
    desired_length: str
    generation_version: int = 1
    provider_used: str = "mock"
    variants: Dict[str, PostVariant] = Field(default_factory=dict)
    quality: QualityRubricResult = Field(default_factory=QualityRubricResult)
    recommended_time: Optional[str] = None
    status: str = "DRAFT"

class GeneratePostRequest(BaseModel):
    """API request payload to trigger generation."""
    topic: str = Field(..., min_length=2, max_length=1000)
    theme: Optional[str] = "Thought Leadership"
    platforms: Optional[List[str]] = Field(default_factory=lambda: ["TWITTER", "LINKEDIN", "META_FACEBOOK", "META_INSTAGRAM"])
    tone: Optional[str] = "Professional & Engaging"
    target_audience: Optional[str] = "General Professionals"
    content_type: Optional[str] = "Quick Insight"
    desired_length: Optional[str] = "Medium"
    keywords: Optional[List[str]] = Field(default_factory=list)
    cta_preference: Optional[str] = None
    provider: Optional[str] = None
    regenerate_post_id: Optional[int] = None
