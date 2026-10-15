import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database.database import get_db
from ..schemas.approval import (
    ApprovalItemResponse,
    ApprovalActionResponse,
    ApprovalDecisionRequest,
    ApprovalRejectionRequest,
    ApprovalRegenerateRequest
)
from ..services.approval_service import ApprovalService

logger = logging.getLogger("ApprovalsRouter")

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("/pending", response_model=List[ApprovalItemResponse])
def get_pending_approvals(
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    """Retrieves all pending social post approval requests with enriched content metadata."""
    return ApprovalService.get_pending_approvals(db=db, skip=skip, limit=limit)


@router.get("/history", response_model=List[ApprovalItemResponse])
def get_approval_history(
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    """Retrieves resolved approval requests (Approved, Rejected, Cancelled)."""
    return ApprovalService.get_approval_history(db=db, skip=skip, limit=limit)


@router.get("/{approval_id}", response_model=ApprovalItemResponse)
def get_approval_details(
    approval_id: int,
    db: Session = Depends(get_db)
):
    """Retrieves details of a specific approval request by its ID."""
    return ApprovalService.get_approval_by_id(db=db, approval_id=approval_id)


@router.post("/{approval_id}/approve", response_model=ApprovalActionResponse)
def approve_post(
    approval_id: int,
    payload: Optional[ApprovalDecisionRequest] = None,
    db: Session = Depends(get_db)
):
    """Approves a pending post, transitioning Post to APPROVED and recording reviewer audit logs."""
    reviewer = payload.reviewer if payload and payload.reviewer else "Human Reviewer"
    review_notes = payload.review_notes if payload else None
    return ApprovalService.approve_post(
        db=db,
        approval_id=approval_id,
        reviewer=reviewer,
        review_notes=review_notes
    )


@router.post("/{approval_id}/reject", response_model=ApprovalActionResponse)
def reject_post(
    approval_id: int,
    payload: ApprovalRejectionRequest,
    db: Session = Depends(get_db)
):
    """Rejects a pending post, requiring a mandatory rejection reason and transitioning Post to REJECTED."""
    reviewer = payload.reviewer if payload.reviewer else "Human Reviewer"
    return ApprovalService.reject_post(
        db=db,
        approval_id=approval_id,
        rejection_reason=payload.rejection_reason,
        reviewer=reviewer,
        review_notes=payload.review_notes
    )


@router.post("/{approval_id}/regenerate", response_model=ApprovalActionResponse)
async def regenerate_post(
    approval_id: int,
    payload: Optional[ApprovalRegenerateRequest] = None,
    db: Session = Depends(get_db)
):
    """Requests regeneration of a post with an alternate angle, respecting max regeneration limits."""
    reviewer = payload.reviewer if payload and payload.reviewer else "Human Reviewer"
    feedback = payload.feedback if payload else None
    provider = payload.provider if payload else None
    return await ApprovalService.regenerate_post(
        db=db,
        approval_id=approval_id,
        reviewer=reviewer,
        feedback=feedback,
        provider=provider
    )
