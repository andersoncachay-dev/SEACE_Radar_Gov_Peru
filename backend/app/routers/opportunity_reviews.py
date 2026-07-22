from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_source_access, source_access_condition
from ..models import Opportunity, OpportunityReview, OpportunityReviewComment, User
from ..schemas import OpportunityReviewCommentIn, OpportunityReviewCommentOut, OpportunityReviewDetailOut, OpportunityReviewOut

router = APIRouter(prefix="/opportunity-reviews", tags=["tracking"])


def _parse_ids(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


def _load_opportunity(db: Session, opportunity_id: int, current_user: User) -> Opportunity:
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Proceso no encontrado")
    require_source_access(current_user, opportunity.source)
    return opportunity


def _comment_out(db: Session, comment: OpportunityReviewComment) -> OpportunityReviewCommentOut:
    author_name = ""
    if comment.author_id:
        author = db.get(User, comment.author_id)
        author_name = author.full_name if author else ""
    return OpportunityReviewCommentOut(
        id=comment.id,
        author_id=comment.author_id,
        author_name=author_name,
        comment=comment.comment,
        created_at=comment.created_at,
    )


@router.get("", response_model=list[OpportunityReviewOut])
def list_reviews(
    opportunity_ids: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(OpportunityReview, Opportunity).join(Opportunity, Opportunity.id == OpportunityReview.opportunity_id)
    condition = source_access_condition(Opportunity.source, current_user)
    if condition is not None:
        query = query.where(condition)
    ids = _parse_ids(opportunity_ids)
    if ids:
        query = query.where(OpportunityReview.opportunity_id.in_(ids))
    query = query.where(OpportunityReview.status == "standby")
    rows = db.execute(query).all()
    return [OpportunityReviewOut(opportunity_id=review.opportunity_id, status=review.status) for review, _opportunity in rows]


@router.get("/{opportunity_id}", response_model=OpportunityReviewDetailOut)
def get_review(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opportunity = _load_opportunity(db, opportunity_id, current_user)
    review = db.scalar(select(OpportunityReview).where(OpportunityReview.opportunity_id == opportunity.id))
    comments = list(
        db.scalars(
            select(OpportunityReviewComment)
            .where(OpportunityReviewComment.opportunity_id == opportunity.id)
            .order_by(OpportunityReviewComment.created_at)
        )
    )
    return OpportunityReviewDetailOut(
        opportunity_id=opportunity.id,
        status=review.status if review else "resolved",
        comments=[_comment_out(db, comment) for comment in comments],
    )


@router.post("/{opportunity_id}", response_model=OpportunityReviewDetailOut)
def start_review(
    opportunity_id: int,
    payload: OpportunityReviewCommentIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opportunity = _load_opportunity(db, opportunity_id, current_user)
    review = db.scalar(select(OpportunityReview).where(OpportunityReview.opportunity_id == opportunity.id))
    if review is None:
        review = OpportunityReview(opportunity_id=opportunity.id, status="standby", created_by_id=current_user.id)
        db.add(review)
    else:
        review.status = "standby"
        review.resolved_at = None
        review.resolved_by_id = None
    comment_text = payload.comment.strip()
    if comment_text:
        db.add(OpportunityReviewComment(opportunity_id=opportunity.id, author_id=current_user.id, comment=comment_text))
    db.commit()
    return get_review(opportunity_id, current_user, db)


@router.post("/{opportunity_id}/comments", response_model=OpportunityReviewDetailOut)
def add_comment(
    opportunity_id: int,
    payload: OpportunityReviewCommentIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opportunity = _load_opportunity(db, opportunity_id, current_user)
    comment_text = payload.comment.strip()
    if not comment_text:
        raise HTTPException(status_code=422, detail="El comentario no puede estar vacio")
    db.add(OpportunityReviewComment(opportunity_id=opportunity.id, author_id=current_user.id, comment=comment_text))
    db.commit()
    return get_review(opportunity_id, current_user, db)


@router.post("/{opportunity_id}/resolve", response_model=OpportunityReviewDetailOut)
def resolve_review(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opportunity = _load_opportunity(db, opportunity_id, current_user)
    review = db.scalar(select(OpportunityReview).where(OpportunityReview.opportunity_id == opportunity.id))
    if not review:
        raise HTTPException(status_code=404, detail="No hay revision registrada para este proceso")
    review.status = "resolved"
    review.resolved_at = datetime.utcnow()
    review.resolved_by_id = current_user.id
    db.commit()
    return get_review(opportunity_id, current_user, db)
