from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..legal_defaults import DEFAULT_LEGAL_DOCUMENTS, DEFAULT_LEGAL_UPDATED_AT
from ..models import LegalDocument, User
from ..schemas import LegalDocumentOut, LegalDocumentUpdate

router = APIRouter(prefix="/legal-documents", tags=["legal documents"])


def _document_out(key: str, item: LegalDocument | None) -> LegalDocumentOut:
    fallback = DEFAULT_LEGAL_DOCUMENTS[key]
    return LegalDocumentOut(
        key=key,
        title=item.title if item else fallback["title"],
        content=item.content if item else fallback["content"],
        updated_at=item.updated_at if item else DEFAULT_LEGAL_UPDATED_AT,
    )


@router.get("", response_model=list[LegalDocumentOut])
def list_legal_documents(db: Session = Depends(get_db)):
    stored = {
        item.key: item
        for item in db.scalars(select(LegalDocument).where(LegalDocument.key.in_(DEFAULT_LEGAL_DOCUMENTS))).all()
    }
    return [_document_out(key, stored.get(key)) for key in DEFAULT_LEGAL_DOCUMENTS]


@router.put("/{document_key}", response_model=LegalDocumentOut)
def update_legal_document(
    document_key: str,
    payload: LegalDocumentUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if document_key not in DEFAULT_LEGAL_DOCUMENTS:
        raise HTTPException(status_code=404, detail="Documento legal no encontrado")
    content = payload.content.strip()
    if len(content) < 100:
        raise HTTPException(status_code=422, detail="El documento debe contener al menos 100 caracteres")
    item = db.scalar(select(LegalDocument).where(LegalDocument.key == document_key))
    if item:
        item.content = content
        item.updated_by_id = current_user.id
    else:
        definition = DEFAULT_LEGAL_DOCUMENTS[document_key]
        item = LegalDocument(
            key=document_key,
            title=definition["title"],
            content=content,
            updated_by_id=current_user.id,
        )
        db.add(item)
    db.commit()
    db.refresh(item)
    return _document_out(document_key, item)
