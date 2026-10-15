import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..database.models import Post, PostStatus
from ..schemas.post import (
    GeneratePostRequest,
    StructuredPostGeneration,
    PostVariant,
    QualityRubricResult
)
from ..services.content_service import ContentService
from ..schemas.common import StandardResponse

logger = logging.getLogger("PostsRouter")

router = APIRouter(prefix="/posts", tags=["Posts"])


@router.post("/generate", response_model=StructuredPostGeneration, status_code=status.HTTP_201_CREATED)
async def generate_post(
    request: GeneratePostRequest,
    db: Session = Depends(get_db)
):
    """Generates multi-platform social media post variants using the active LLM provider (Groq / Gemini / Mock).
    Performs context building, generation, quality review, and database persistence.
    """
    try:
        result = await ContentService.generate_post(request, db)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.exception(f"Error during post generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {str(e)}"
        )


@router.post("/regenerate", response_model=StructuredPostGeneration)
async def regenerate_post(
    request: GeneratePostRequest,
    db: Session = Depends(get_db)
):
    """Regenerates post variants with alternate hook, angle, and structural strategy."""
    if not request.regenerate_post_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="regenerate_post_id must be provided to regenerate a post."
        )
    try:
        return await ContentService.generate_post(request, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=List[dict])
def list_posts(
    status_filter: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Lists recent posts with optional status filtering."""
    query = db.query(Post).order_by(Post.created_at.desc())
    if status_filter:
        try:
            status_enum = PostStatus(status_filter)
            query = query.filter(Post.status == status_enum)
        except Exception:
            query = query.filter(Post.status == status_filter)
    posts = query.limit(limit).all()

    return [
        {
            "id": p.id,
            "topic": p.topic,
            "tone": p.tone,
            "status": p.status.value if hasattr(p.status, "value") else str(p.status),
            "review_score": p.review_score,
            "review_passed": p.review_passed,
            "target_platforms": p.target_platforms or [],
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "platform_contents": p.platform_contents or {}
        }
        for p in posts
    ]


@router.get("/{post_id}", response_model=dict)
def get_post(post_id: int, db: Session = Depends(get_db)):
    """Retrieves a single post by ID."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return {
        "id": post.id,
        "topic": post.topic,
        "tone": post.tone,
        "status": post.status.value if hasattr(post.status, "value") else str(post.status),
        "review_score": post.review_score,
        "review_feedback": post.review_feedback,
        "review_passed": post.review_passed,
        "target_platforms": post.target_platforms or [],
        "platform_contents": post.platform_contents or {},
        "created_at": post.created_at.isoformat() if post.created_at else None
    }
