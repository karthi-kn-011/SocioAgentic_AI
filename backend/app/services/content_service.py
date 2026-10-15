import logging
import uuid
from typing import Optional, Dict
from sqlalchemy.orm import Session

from ..schemas.post import (
    GeneratePostRequest,
    StructuredPostGeneration,
    PostVariant,
    QualityRubricResult
)
from ..graph.state import ContentWorkflowState
from ..graph.workflow import content_graph
from ..database.models import (
    Post,
    PostStatus,
    ApprovalRequest,
    ApprovalStatus,
    ActivityLog,
    get_utc_now
)
from ..database.crud import log_activity
from ..config import settings

logger = logging.getLogger("ContentService")


class ContentService:
    """End-to-end orchestration service using LangGraph for generating, reviewing,
    self-correcting, persisting, and submitting social media posts for human approval.
    """

    @classmethod
    async def generate_post(
        cls,
        request: GeneratePostRequest,
        db: Session
    ) -> StructuredPostGeneration:
        """Executes full LangGraph orchestration workflow:
        context building -> LLM generation -> 7-dimension quality review -> self-correction -> DB persistence -> ApprovalRequest creation.
        """
        previous_content: Optional[Dict[str, str]] = None
        variation_index = 0
        existing_post: Optional[Post] = None

        # Check if this is a regeneration request
        if request.regenerate_post_id:
            existing_post = db.query(Post).filter(Post.id == request.regenerate_post_id).first()
            if existing_post and existing_post.platform_contents:
                previous_content = {
                    k: v.get("content", "") if isinstance(v, dict) else str(v)
                    for k, v in existing_post.platform_contents.items()
                }
                variation_index = existing_post.regeneration_count or ((existing_post.review_score % 4) + 1)

        # 1. Initialize LangGraph Workflow State
        from ..database.models import normalize_platform_name
        raw_platforms = request.platforms or ["TWITTER", "LINKEDIN"]
        norm_platforms = []
        for p in raw_platforms:
            c = normalize_platform_name(p)
            if c not in norm_platforms:
                norm_platforms.append(c)

        thread_id = str(uuid.uuid4())
        initial_state: ContentWorkflowState = {
            "post_id": existing_post.id if existing_post else None,
            "thread_id": thread_id,
            "topic": request.topic,
            "theme": request.theme or "Thought Leadership",
            "platforms": norm_platforms,
            "tone": request.tone or "Professional & Engaging",
            "target_audience": request.target_audience or "General Professionals",
            "content_type": request.content_type or "Quick Insight",
            "desired_length": request.desired_length or "Medium",
            "keywords": request.keywords or [],
            "cta_preference": request.cta_preference,
            "provider": request.provider or settings.active_llm_provider,
            "previous_content": previous_content,
            "regeneration_count": variation_index,
            "correction_count": 0,
            "timestamps": {}
        }

        # 2. Execute Orchestrated LangGraph StateGraph
        logger.info(f"Invoking LangGraph content workflow for topic: '{request.topic[:40]}...' [Thread: {thread_id}]")
        final_state = await content_graph.ainvoke(initial_state)

        # 3. Extract and parse generated variants and quality rubric
        raw_variants = final_state.get("variants", {})
        variants: Dict[str, PostVariant] = {}
        for p, v in raw_variants.items():
            if isinstance(v, dict):
                variants[p] = PostVariant(**v)
            elif isinstance(v, PostVariant):
                variants[p] = v
            else:
                variants[p] = PostVariant(platform=p, content=str(v), character_count=len(str(v)), character_limit=3000)

        dim_scores = final_state.get("dimension_scores", {})
        quality = QualityRubricResult(
            grammar_score=dim_scores.get("grammar_score", 95),
            topic_relevance_score=dim_scores.get("topic_relevance_score", 95),
            theme_adherence_score=dim_scores.get("theme_adherence_score", 90),
            platform_suitability_score=dim_scores.get("platform_suitability_score", 90),
            naturalness_score=dim_scores.get("naturalness_score", 90),
            engagement_score=dim_scores.get("engagement_score", 85),
            safety_score=dim_scores.get("safety_score", 98),
            composite_score=final_state.get("quality_score", 90),
            passed=final_state.get("quality_passed", True),
            critique_feedback=final_state.get("review_feedback", "Quality checks passed."),
            issues_detected=final_state.get("issues_detected", [])
        )

        provider_used_name = final_state.get("provider_used", "mock")
        platform_contents_dict = {k: v.model_dump() for k, v in variants.items()}

        # 4. Durable Persistence to Database
        now = get_utc_now()
        first_content = next(iter(variants.values())).content if variants else ""
        if existing_post:
            post_record = existing_post
            post_record.topic = request.topic
            post_record.theme = initial_state["theme"]
            post_record.tone = initial_state["tone"]
            post_record.raw_content = first_content
            post_record.platform_contents = platform_contents_dict
            post_record.target_platforms = initial_state["platforms"]
            post_record.review_score = quality.composite_score
            post_record.review_feedback = quality.critique_feedback
            post_record.review_passed = quality.passed
            post_record.thread_id = thread_id
            post_record.status = PostStatus.AWAITING_HUMAN_APPROVAL
            post_record.generation_version = (post_record.generation_version or 1) + 1
            post_record.regeneration_count = (post_record.regeneration_count or 0) + 1
        else:
            post_record = Post(
                topic=request.topic,
                theme=initial_state["theme"],
                tone=initial_state["tone"],
                raw_content=first_content,
                platform_contents=platform_contents_dict,
                target_platforms=initial_state["platforms"],
                status=PostStatus.AWAITING_HUMAN_APPROVAL,
                regeneration_count=0,
                generation_version=1,
                review_score=quality.composite_score,
                review_feedback=quality.critique_feedback,
                review_passed=quality.passed,
                thread_id=thread_id
            )
            db.add(post_record)
            db.flush()

        # 5. Create or Reset Pending Approval Request in Relational Database
        existing_approval = db.query(ApprovalRequest).filter(ApprovalRequest.post_id == post_record.id).first()
        if existing_approval:
            existing_approval.status = ApprovalStatus.PENDING.value
            existing_approval.rejection_reason = None
            existing_approval.reviewer = None
            existing_approval.requested_at = now
            existing_approval.reviewed_at = None
            existing_approval.responded_at = None
        else:
            approval = ApprovalRequest(
                post_id=post_record.id,
                channel="web",
                status=ApprovalStatus.PENDING.value,
                requested_at=now
            )
            db.add(approval)

        # 6. Audit Logging
        log_activity(
            db=db,
            action="GENERATE_POST_VARIANTS",
            details=f"Generated variants for {len(variants)} platforms via {provider_used_name}. Score: {quality.composite_score}/100",
            post_id=post_record.id,
            actor=provider_used_name
        )
        log_activity(
            db=db,
            action="CONTENT_GENERATED",
            details=f"Generated variants for {len(variants)} platforms via {provider_used_name}. Score: {quality.composite_score}/100",
            post_id=post_record.id,
            actor=provider_used_name
        )
        log_activity(
            db=db,
            action="APPROVAL_REQUESTED",
            details=f"Post #{post_record.id} submitted to human approval queue.",
            post_id=post_record.id,
            actor="LangGraph Workflow Engine"
        )


        db.commit()
        db.refresh(post_record)

        return StructuredPostGeneration(
            post_id=post_record.id,
            topic=request.topic,
            theme=initial_state["theme"],
            tone=initial_state["tone"],
            target_audience=initial_state["target_audience"],
            content_type=initial_state["content_type"],
            desired_length=initial_state["desired_length"],
            generation_version=post_record.generation_version or (variation_index + 1),
            provider_used=provider_used_name,
            variants=variants,
            quality=quality,
            status=post_record.status.value if hasattr(post_record.status, "value") else str(post_record.status)
        )
