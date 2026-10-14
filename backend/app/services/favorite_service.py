"""Per-user favorites across both modules.

Kinds and the stable key each one stores:
- ``opportunity``: Radar ``Opportunity.id`` (rows are never rebuilt).
- ``hist_contratacion``: ``HistContracting.source_key``. "Contratos por vencer"
  rows star the same award, so one key covers Historial and Por vencer.
- ``hist_recurrente``: ``"{entity_ruc}|{supplier_ruc}"``.
- ``hist_pac``: ``"{year}|{entity_code}|{reference_number}|{item_number}"``.
The Histórico keys match HistAlert.ref_key, so they survive monthly re-imports.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import UserFavorite

FAVORITE_KINDS = ("opportunity", "hist_contratacion", "hist_recurrente", "hist_pac")


def list_favorites(db: Session, user_id: int, kind: str | None = None) -> list[UserFavorite]:
    query = select(UserFavorite).where(UserFavorite.user_id == user_id)
    if kind:
        query = query.where(UserFavorite.kind == kind)
    return list(db.scalars(query.order_by(UserFavorite.created_at.desc(), UserFavorite.id.desc())).all())


def favorite_keys(db: Session, user_id: int) -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {kind: [] for kind in FAVORITE_KINDS}
    for kind, ref_key in db.execute(select(UserFavorite.kind, UserFavorite.ref_key).where(UserFavorite.user_id == user_id)).all():
        keys.setdefault(kind, []).append(ref_key)
    return keys


def add_favorite(db: Session, user_id: int, kind: str, ref_key: str, label: str = "") -> UserFavorite:
    existing = db.scalar(
        select(UserFavorite).where(UserFavorite.user_id == user_id, UserFavorite.kind == kind, UserFavorite.ref_key == ref_key)
    )
    if existing:
        if label and existing.label != label:
            existing.label = label[:300]
            db.commit()
        return existing
    favorite = UserFavorite(user_id=user_id, kind=kind, ref_key=ref_key, label=label[:300])
    db.add(favorite)
    db.commit()
    db.refresh(favorite)
    return favorite


def remove_favorite(db: Session, user_id: int, kind: str, ref_key: str) -> None:
    db.execute(delete(UserFavorite).where(UserFavorite.user_id == user_id, UserFavorite.kind == kind, UserFavorite.ref_key == ref_key))
    db.commit()
