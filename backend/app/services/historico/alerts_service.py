"""Prioritised Histórico Perú alerts: expiring contracts, due recurring
purchases and PAC items about to be called.

Alerts are keyed by (kind, ref_key) so a monthly re-import updates the same
row: its workflow status survives, a dismissal holds until the due date
changes, and rows that no longer qualify are deactivated rather than deleted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import HistAlert, HistContracting, HistExpiring, HistPacItem, HistRecurring
from .derive import PATTERN_SINGLE

HIGH_AMOUNT = 500_000.0  # soles; lifts 91–180 day expirations to P2
PRIORITY_LABELS = {"P1": "Crítica", "P2": "Alta", "P3": "Media", "P4": "Baja"}


@dataclass(frozen=True)
class Candidate:
    kind: str
    ref_key: str
    priority: str
    score: float
    title: str
    detail: str
    entity_name: str
    department: str
    amount: float
    due_date: date | None
    expiring_id: int | None = None
    recurring_id: int | None = None
    pac_item_id: int | None = None


def _amount_weight(amount: float) -> float:
    return math.log10(max(amount, 0) + 1) * 5


def expiring_priority(days: int, amount: float) -> str | None:
    if days < 0 or days > 365:
        return None
    if days <= 30:
        return "P1"
    if days <= 90:
        return "P2"
    if days <= 180:
        return "P2" if amount >= HIGH_AMOUNT else "P3"
    return "P4"


def recurring_priority(days: int, pattern: str) -> str | None:
    if pattern == PATTERN_SINGLE:
        return None
    if 0 <= days <= 30:
        return "P2"
    if days < 0 or days <= 90:
        return "P3"
    return None


def pac_priority(item: HistPacItem, today: date) -> str | None:
    if not item.situation.startswith("Por convocar"):
        return None
    months_ahead = (item.year - today.year) * 12 + item.planned_month - today.month
    if 0 <= months_ahead <= 1 and not item.already_awarded:
        return "P2"
    return "P4"


def _expiring_candidates(db: Session) -> list[Candidate]:
    rows = db.execute(select(HistExpiring, HistContracting).join(HistContracting, HistContracting.id == HistExpiring.contracting_id)).all()
    candidates = []
    for expiring, award in rows:
        priority = expiring_priority(expiring.days_to_end, award.amount)
        if not priority:
            continue
        score = (365 - expiring.days_to_end) / 365 * 60 + _amount_weight(award.amount) + (10 if expiring.is_real_date else 0) - (15 if expiring.possibly_renewed else 0)
        renewed = " Posible renovado: la entidad ya adjudicó un proceso posterior similar." if expiring.possibly_renewed else ""
        candidates.append(Candidate(
            kind="vencimiento",
            ref_key=award.source_key,
            priority=priority,
            score=round(score, 2),
            title=f"Vence en {expiring.days_to_end} días · {award.nomenclature or award.description[:60]}",
            detail=f"{award.description[:240]} — proveedor actual {award.supplier_name or 'sin dato'}. Fecha: {expiring.date_source}.{renewed}",
            entity_name=award.entity_name,
            department=award.department,
            amount=award.amount,
            due_date=expiring.end_date,
            expiring_id=expiring.id,
        ))
    return candidates


def _recurring_candidates(db: Session) -> list[Candidate]:
    candidates = []
    for item in db.scalars(select(HistRecurring)).all():
        priority = recurring_priority(item.days_to_next, item.pattern)
        if not priority:
            continue
        overdue = item.days_to_next < 0
        urgency = 50 if overdue else (90 - item.days_to_next) / 90 * 50
        candidates.append(Candidate(
            kind="recurrente",
            ref_key=f"{item.entity_ruc}|{item.supplier_ruc}",
            priority=priority,
            score=round(urgency + _amount_weight(item.amount_12m_supplier), 2),
            title=("Compra atrasada" if overdue else f"Próxima compra en {item.days_to_next} días") + f" · {item.supplier_name}",
            detail=f"{item.pattern}: {item.orders_12m} órdenes en 12 meses (S/ {item.amount_12m_supplier:,.0f}). Última: {item.last_order_description[:200]}",
            entity_name=item.entity_name,
            department=item.department,
            amount=item.amount_12m_supplier,
            due_date=item.next_purchase_date,
            recurring_id=item.id,
        ))
    return candidates


def _pac_candidates(db: Session, today: date) -> list[Candidate]:
    candidates = []
    for item in db.scalars(select(HistPacItem).where(HistPacItem.relevance == "ok")).all():
        priority = pac_priority(item, today)
        if not priority:
            continue
        due = date(item.year, min(max(item.planned_month, 1), 12), 1)
        candidates.append(Candidate(
            kind="pac",
            ref_key=f"{item.year}|{item.entity_code}|{item.reference_number}|{item.item_number}",
            priority=priority,
            score=round(40 if priority == "P2" else 10, 2),
            title=f"PAC {item.year}: convocatoria prevista para el mes {item.planned_month} · {item.process_type}",
            detail=item.item_description[:300] or item.process_description[:300],
            entity_name=item.entity_name,
            department=item.department,
            amount=0.0,
            due_date=due,
            pac_item_id=item.id,
        ))
    return candidates


def evaluate_alerts(db: Session, today: date, *, import_run_id: int | None = None) -> int:
    candidates = _expiring_candidates(db) + _recurring_candidates(db) + _pac_candidates(db, today)
    existing = {(alert.kind, alert.ref_key): alert for alert in db.scalars(select(HistAlert)).all()}
    seen: set[tuple[str, str]] = set()
    now = datetime.utcnow()
    for candidate in candidates:
        key = (candidate.kind, candidate.ref_key)
        seen.add(key)
        alert = existing.get(key)
        if alert is None:
            alert = HistAlert(kind=candidate.kind, ref_key=candidate.ref_key, status="nueva", first_seen_import_id=import_run_id)
            db.add(alert)
        elif alert.status == "descartada" and alert.dismissed_due_date and alert.dismissed_due_date != candidate.due_date:
            alert.status = "nueva"  # the date moved: the dismissal no longer applies
            alert.dismissed_due_date = None
        for field in ("priority", "score", "title", "detail", "entity_name", "department", "amount", "due_date", "expiring_id", "recurring_id", "pac_item_id"):
            setattr(alert, field, getattr(candidate, field))
        alert.title = alert.title[:300]
        alert.is_active = True
        alert.last_evaluated_at = now
    for key, alert in existing.items():
        if key not in seen and alert.is_active:
            alert.is_active = False
            alert.expiring_id = alert.recurring_id = alert.pac_item_id = None
    db.commit()
    return len(candidates)


def refresh_days_and_alerts(db: Session, today: date) -> int:
    """Daily pass: days-to-go change every day even without a new import."""
    from .import_service import refresh_pac
    from .derive import expiring_bucket, recurring_bucket

    for expiring in db.scalars(select(HistExpiring)).all():
        expiring.days_to_end = (expiring.end_date - today).days
        expiring.bucket = expiring_bucket(expiring.days_to_end)
    for item in db.scalars(select(HistRecurring)).all():
        if item.next_purchase_date:
            item.days_to_next = (item.next_purchase_date - today).days
            item.bucket = recurring_bucket(item.days_to_next)
    db.commit()
    refresh_pac(db, today)
    return evaluate_alerts(db, today)
