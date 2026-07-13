from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import SearchProfile, User
from ..schemas import SearchProfileCreate, SearchProfileOut

router = APIRouter(prefix="/search-profiles", tags=["search profiles"])


@router.get("", response_model=list[SearchProfileOut])
def list_profiles(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(SearchProfile).order_by(SearchProfile.created_at.desc())).all())


@router.post("", response_model=SearchProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(payload: SearchProfileCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = SearchProfile(**payload.dict(), owner_id=current_user.id)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/{profile_id}/active", response_model=SearchProfileOut)
def set_profile_active(profile_id: int, is_active: bool, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.get(SearchProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Search profile not found")
    profile.is_active = is_active
    db.commit()
    db.refresh(profile)
    return profile
