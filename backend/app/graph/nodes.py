import datetime
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from .state import ContentWorkflowState
from ..config import settings
from ..database.models import Post, PostStatus, ApprovalRequest, ApprovalStatus, ActivityLog
from ..database.crud import log_activity
from ..services.content_context import ContentContextService
from ..agents.provider_factory import LLMProviderFactory
from ..agents.mock_provider import MockProvider
from ..agents.content_reviewer import ContentReviewerAgent
from ..schemas.post import PostVariant, QualityRubricResult, ContentGenerationContext

logger = logging.getLogger("WorkflowNodes")


def get_utc_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


async def generate_node(state: ContentWorkflowState) -> Dict[str, Any]:
    """Orchestrates generation of multi-platform post variants using the configured LLM provider."""
    timestamps = state.get("timestamps", {})
    timestamps["generation_started_at"] = get_utc_iso()

    # Build rich context using existing ContentContextService
    context: ContentGenerationContext = ContentContextService.build_context(
        topic=state["topic"],
        theme=state.get("theme", "Thought Leadership"),
        platforms=state.get("platforms", ["TWITTER", "LINKEDIN"]),
        tone=state.get("tone", "Professional & Engaging"),
        target_audience=state.get("target_audience", "General Professionals"),
        content_type=state.get("content_type", "Quick Insight"),
        desired_length=state.get("desired_length", "Medium"),
        keywords=state.get("keywords", []),
        cta_preference=state.get("cta_preference"),
        previous_content=state.get("previous_content"),
        variation_index=state.get("regeneration_count", 0) + state.get("correction_count", 0)
    )

    provider_name = state.get("provider") or settings.active_llm_provider
    provider = LLMProviderFactory.get_provider(provider_name)
    provider_used = provider.provider_name

    try:
        variants = await provider.generate_variants(context)
    except Exception as e:
        logger.warning(f"Active provider '{provider_used}' failed during workflow ({e}). Falling back to MockProvider.")
        mock_provider = MockProvider()
        provider_used = mock_provider.provider_name
        variants = await mock_provider.generate_variants(context)

    variants_dict = {
        k: v.model_dump() if isinstance(v, PostVariant) else v
        for k, v in variants.items()
    }

    timestamps["generation_completed_at"] = get_utc_iso()

    return {
        "variants": variants_dict,
        "provider_used": provider_used,
        "workflow_status": PostStatus.AI_REVIEW.value,
        "timestamps": timestamps
    }


async def review_node(state: ContentWorkflowState) -> Dict[str, Any]:
    """Evaluates generated content across the 7 quality dimensions using ContentReviewerAgent."""
    timestamps = state.get("timestamps", {})
    timestamps["review_started_at"] = get_utc_iso()

    provider = LLMProviderFactory.get_provider(state.get("provider"))
    reviewer = ContentReviewerAgent(provider=provider, threshold=settings.AI_QUALITY_THRESHOLD)

    # Convert variants back to PostVariant instances for reviewer
    variants_objs: Dict[str, PostVariant] = {}
    for p, v in state.get("variants", {}).items():
        if isinstance(v, dict):
            content_str = v.get("content", "")
            variants_objs[p] = PostVariant(
                platform=v.get("platform", p),
                content=content_str,
                character_count=v.get("character_count", len(content_str)),
                character_limit=v.get("character_limit", 280 if p == "TWITTER" else 3000),
                hook_type=v.get("hook_type", "Insight"),
                hashtags=v.get("hashtags", []),
                call_to_action=v.get("call_to_action")
            )
        elif isinstance(v, PostVariant):
            variants_objs[p] = v
        else:
            s = str(v)
            variants_objs[p] = PostVariant(platform=p, content=s, character_count=len(s), character_limit=280 if p == "TWITTER" else 3000)


    context = ContentContextService.build_context(
        topic=state["topic"],
        theme=state.get("theme", "Thought Leadership"),
        platforms=state.get("platforms", ["TWITTER", "LINKEDIN"]),
        tone=state.get("tone", "Professional & Engaging"),
        target_audience=state.get("target_audience", "General Professionals")
    )

    quality: QualityRubricResult = await reviewer.review_variants(variants_objs, context)

    timestamps["review_completed_at"] = get_utc_iso()

    return {
        "quality_score": quality.composite_score,
        "quality_passed": quality.passed,
        "review_feedback": quality.critique_feedback,
        "dimension_scores": {
            "grammar_score": quality.grammar_score,
            "topic_relevance_score": quality.topic_relevance_score,
            "theme_adherence_score": quality.theme_adherence_score,
            "platform_suitability_score": quality.platform_suitability_score,
            "naturalness_score": quality.naturalness_score,
            "engagement_score": quality.engagement_score,
            "safety_score": quality.safety_score,
        },
        "issues_detected": quality.issues_detected,
        "timestamps": timestamps
    }


async def self_correction_node(state: ContentWorkflowState) -> Dict[str, Any]:
    """Iteratively refines drafts scoring below quality threshold with targeted corrective feedback."""
    count = state.get("correction_count", 0) + 1
    logger.info(f"Triggering AI self-correction (Attempt {count}/{settings.AI_MAX_CORRECTION_ATTEMPTS}) for topic: {state.get('topic')}")

    # Build corrective context incorporating detected issues
    critique_notes = "; ".join(state.get("issues_detected", [])) or state.get("review_feedback", "")
    context = ContentContextService.build_context(
        topic=state["topic"],
        theme=state.get("theme", "Thought Leadership"),
        platforms=state.get("platforms", ["TWITTER", "LINKEDIN"]),
        tone=state.get("tone", "Professional & Engaging"),
        target_audience=state.get("target_audience", "General Professionals"),
        keywords=state.get("keywords", []),
        variation_index=state.get("regeneration_count", 0) + count
    )

    provider = LLMProviderFactory.get_provider(state.get("provider"))
    try:
        corrected_variants = await provider.generate_variants(context)
        variants_dict = {k: v.model_dump() for k, v in corrected_variants.items()}
    except Exception as e:
        logger.warning(f"Self-correction generation failed: {e}. Preserving existing variants.")
        variants_dict = state.get("variants", {})

    return {
        "variants": variants_dict,
        "correction_count": count,
        "workflow_status": PostStatus.AI_REVIEW.value
    }


def should_self_correct(state: ContentWorkflowState) -> str:
    """Conditional router: evaluates whether to self-correct or transition to human approval."""
    passed = state.get("quality_passed", False)
    attempts = state.get("correction_count", 0)
    max_attempts = settings.AI_MAX_CORRECTION_ATTEMPTS

    if not passed and attempts < max_attempts:
        return "self_correct"
    return "send_to_approval"
