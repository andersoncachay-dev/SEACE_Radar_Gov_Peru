from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import Document, User
from ..schemas import DocumentOut
from ..security import parse_access_token
from ..services.document_service import discover_documents_for_opportunity

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
def list_documents(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return list(db.scalars(select(Document).order_by(Document.created_at.desc()).limit(300)).all())


@router.get("/opportunity/{opportunity_id}", response_model=list[DocumentOut])
def list_opportunity_documents(
    opportunity_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Document).where(Document.opportunity_id == opportunity_id).order_by(Document.created_at.desc())
    return list(db.scalars(query).all())


@router.post("/opportunity/{opportunity_id}/discover", response_model=list[DocumentOut])
def discover_documents(
    opportunity_id: int,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return discover_documents_for_opportunity(db, opportunity_id)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if not token or not parse_access_token(token):
        raise HTTPException(status_code=401, detail="Invalid token")
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = Path(doc.local_path)
    if doc.status != "downloaded" or not path.exists():
        raise HTTPException(status_code=404, detail="Local file not available")
    return FileResponse(path, media_type=doc.mime_type or "application/octet-stream", filename=doc.filename or path.name)
