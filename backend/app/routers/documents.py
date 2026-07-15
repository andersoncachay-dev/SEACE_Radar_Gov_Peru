from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user, require_source_access, source_access_condition
from ..models import Document, Opportunity, User
from ..schemas import DocumentOut
from ..security import parse_access_token
from ..services.document_service import discover_documents_for_opportunity

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = select(Document).join(Opportunity, Document.opportunity_id == Opportunity.id)
    access_condition = source_access_condition(Opportunity.source, current_user)
    if access_condition is not None:
        query = query.where(access_condition)
    return list(db.scalars(query.order_by(Document.created_at.desc()).limit(300)).all())


@router.get("/opportunity/{opportunity_id}", response_model=list[DocumentOut])
def list_opportunity_documents(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    require_source_access(current_user, opportunity.source)
    query = select(Document).where(Document.opportunity_id == opportunity_id).order_by(Document.created_at.desc())
    docs = list(db.scalars(query).all())
    if any(doc.status == "downloaded" for doc in docs):
        docs = [
            doc
            for doc in docs
            if doc.status == "downloaded" or (doc.title or "").lower().startswith("ruta protegida")
        ]
    return sorted(
        docs,
        key=lambda doc: (
            0 if (doc.title or "").lower().startswith("ficha mercado publico") else 1,
            0 if doc.status == "downloaded" else 1,
            (doc.title or doc.filename or "").lower(),
        ),
    )


@router.post("/opportunity/{opportunity_id}/discover", response_model=list[DocumentOut])
def discover_documents(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    opportunity = db.get(Opportunity, opportunity_id)
    if not opportunity:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    require_source_access(current_user, opportunity.source)
    return discover_documents_for_opportunity(db, opportunity_id)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    email = parse_access_token(token) if token else None
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token")
    current_user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if not current_user:
        raise HTTPException(status_code=401, detail="Inactive or missing user")
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.opportunity_id:
        opportunity = db.get(Opportunity, doc.opportunity_id)
        if opportunity:
            require_source_access(current_user, opportunity.source)
    path = Path(doc.local_path)
    if doc.status != "downloaded" or not path.exists():
        raise HTTPException(status_code=404, detail="Local file not available")
    return FileResponse(path, media_type=doc.mime_type or "application/octet-stream", filename=doc.filename or path.name)
