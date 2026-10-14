"""Prioritised Histórico alerts (Perú and Chile, per session country):
expiring contracts, due recurring purchases and PAC items about to be called.
Amount thresholds are in soles and scaled by HistCountry.amount_scale.

Alerts are keyed by (kind, ref_key) so a monthly re-import updates the same
row: its workflow status survives, a dismissal holds until the due date
changes, and rows that no longer qualify are deactivated rather than deleted.

Each user can narrow what they see (and what their weekly digest contains)
with a HistAlertPreference: categories such as "Satelital - Starlink",
departments, government levels, process types, minimum amount and priority.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...hist_scope import current_country
from ...models import HistAlert, HistAlertPreference, HistContracting, HistExpiring, HistPacItem, HistRecurring
from .classify import normalize
from .countries import get_country
from .derive import PATTERN_MONTHLY, PATTERN_SINGLE

HIGH_AMOUNT = 500_000.0  # soles; lifts 91–180 day expirations to P2
RECENTLY_OVERDUE_DAYS = 60  # an overdue recurring purchase stays actionable this long
RECURRING_MIN_AMOUNT = 10_000.0  # soles bought from the same supplier in 12 months
PRIORITY_LABELS = {"P1": "Crítica", "P2": "Alta", "P3": "Media", "P4": "Baja"}
PRIORITY_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
ALERT_KINDS = ("vencimiento", "recurrente", "pac")


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
    category: str = ""
    process_group: str = ""
    government_level: str = ""
    expiring_id: int | None = None
    recurring_id: int | None = None
    pac_item_id: int | None = None


def _amount_weight(amount: float) -> float:
    return math.log10(max(amount, 0) + 1) * 5


def expiring_priority(days: int, amount: float, scale: float = 1.0) -> str | None:
    if days < 0 or days > 365:
        return None
    if days <= 30:
        return "P1"
    if days <= 90:
        return "P2"
    if days <= 180:
        return "P2" if amount >= HIGH_AMOUNT * scale else "P3"
    return "P4"


def recurring_priority(days: int, pattern: str, amount_12m: float = RECURRING_MIN_AMOUNT, scale: float = 1.0) -> str | None:
    """Only genuinely recurring buyers worth a call, and only while actionable.

    Calibrated on the 2026-10 data: without the amount floor and the
    monthly-only rule for overdue purchases, ~870 low-value pairs flooded
    the "Media" tray. Long-overdue pairs (the entity changed supplier or
    modality) are not alerted at all."""
    if pattern == PATTERN_SINGLE or amount_12m < RECURRING_MIN_AMOUNT * scale:
        return None
    if 0 <= days <= 30:
        return "P2"
    if -RECENTLY_OVERDUE_DAYS <= days < 0:
        return "P3" if pattern == PATTERN_MONTHLY else None
    if 30 < days <= 90:
        return "P4"
    return None


def pac_priority(item: HistPacItem, today: date) -> str | None:
    """PAC items planned for this month or the next one."""
    if not item.situation.startswith("Por convocar"):
        return None
    months_ahead = (item.year - today.year) * 12 + item.planned_month - today.month
    if not 0 <= months_ahead <= 1:
        return None
    return "P3" if item.already_awarded else "P2"


def _expiring_candidates(db: Session) -> list[Candidate]:
    country = get_country(current_country(db))
    rows = db.execute(select(HistExpiring, HistContracting).join(HistContracting, HistContracting.id == HistExpiring.contracting_id)).all()
    candidates = []
    for expiring, award in rows:
        priority = expiring_priority(expiring.days_to_end, award.amount, country.amount_scale)
        if not priority:
            continue
        score = (365 - expiring.days_to_end) / 365 * 60 + _amount_weight(award.amount / country.amount_scale) + (10 if expiring.is_real_date else 0) - (15 if expiring.possibly_renewed else 0)
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
            category=award.category,
            process_group=award.process_group,
            government_level=award.government_level,
            expiring_id=expiring.id,
        ))
    return candidates


def _recurring_candidates(db: Session) -> list[Candidate]:
    country = get_country(current_country(db))
    candidates = []
    for item in db.scalars(select(HistRecurring)).all():
        priority = recurring_priority(item.days_to_next, item.pattern, item.amount_12m_supplier, country.amount_scale)
        if not priority:
            continue
        overdue = item.days_to_next < 0
        urgency = 50 if overdue else (90 - item.days_to_next) / 90 * 50
        candidates.append(Candidate(
            kind="recurrente",
            ref_key=f"{item.entity_ruc}|{item.supplier_ruc}",
            priority=priority,
            score=round(urgency + _amount_weight(item.amount_12m_supplier / country.amount_scale), 2),
            title=(f"Compra atrasada {-item.days_to_next} días" if overdue else f"Próxima compra en {item.days_to_next} días") + f" · {item.supplier_name}",
            detail=f"{item.pattern}: {item.orders_12m} órdenes en 12 meses ({country.money(item.amount_12m_supplier)}). Última: {item.last_order_description[:200]}",
            entity_name=item.entity_name,
            department=item.department,
            amount=item.amount_12m_supplier,
            due_date=item.next_purchase_date,
            category=item.category,
            process_group=country.small_purchase_group,
            government_level=item.government_level,
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
            score=round(40 if priority == "P2" else 20, 2),
            title=f"PAC {item.year}: convocatoria prevista para el mes {item.planned_month} · {item.process_type}",
            detail=item.item_description[:300] or item.process_description[:300],
            entity_name=item.entity_name,
            department=item.department,
            amount=0.0,
            due_date=due,
            category=item.category,
            process_group=item.process_group,
            government_level=item.government_level,
            pac_item_id=item.id,
        ))
    return candidates


_COPIED_FIELDS = (
    "priority", "score", "title", "detail", "entity_name", "department", "amount", "due_date",
    "category", "process_group", "government_level", "expiring_id", "recurring_id", "pac_item_id",
)


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
        for field in _COPIED_FIELDS:
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
    from .derive import expiring_bucket, recurring_bucket
    from .import_service import refresh_pac

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


# --- per-user alert preferences ---------------------------------------------------


def split_csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split("|") if item.strip()]


def join_csv(values: list[str] | None) -> str:
    # "|" rather than "," because category names contain commas.
    return "|".join(dict.fromkeys(item.strip() for item in (values or []) if item.strip()))


def get_preference(db: Session, user_id: int) -> HistAlertPreference | None:
    return db.scalar(select(HistAlertPreference).where(HistAlertPreference.user_id == user_id))


def matches_preference(alert: HistAlert, preference: HistAlertPreference | None) -> bool:
    """An empty preference (or an empty field) means "everything"."""
    if preference is None:
        return True
    kinds, categories = split_csv(preference.kinds), split_csv(preference.categories)
    departments, levels, groups = split_csv(preference.departments), split_csv(preference.government_levels), split_csv(preference.process_groups)
    if kinds and alert.kind not in kinds:
        return False
    if categories and alert.category not in categories:
        return False
    if departments and alert.department not in departments:
        return False
    if levels and alert.government_level not in levels:
        return False
    if groups and alert.process_group not in groups:
        return False
    if PRIORITY_ORDER.get(alert.priority, 4) > PRIORITY_ORDER.get(preference.min_priority or "P4", 4):
        return False
    if preference.min_amount and alert.kind != "pac" and alert.amount < preference.min_amount:
        return False
    terms = [normalize(term) for term in split_csv(preference.keywords)]
    if terms:
        haystack = normalize(f"{alert.title} {alert.detail} {alert.entity_name}")
        if not any(term in haystack for term in terms):
            return False
    return True


def preference_conditions(preference: HistAlertPreference | None) -> list:
    """SQL version of matches_preference, so "Mis alertas" paginates in the
    database. Free-text terms use ILIKE (accent-sensitive, unlike the Python
    check used by the digest)."""
    if preference is None:
        return []
    conditions = []
    for column, value in (
        (HistAlert.kind, preference.kinds), (HistAlert.category, preference.categories), (HistAlert.department, preference.departments),
        (HistAlert.government_level, preference.government_levels), (HistAlert.process_group, preference.process_groups),
    ):
        values = split_csv(value)
        if values:
            conditions.append(column.in_(values))
    allowed = [p for p, order in PRIORITY_ORDER.items() if order <= PRIORITY_ORDER.get(preference.min_priority or "P4", 4)]
    conditions.append(HistAlert.priority.in_(allowed))
    if preference.min_amount:
        conditions.append((HistAlert.kind == "pac") | (HistAlert.amount >= preference.min_amount))
    terms = split_csv(preference.keywords)
    if terms:
        conditions.append(or_(*(
            HistAlert.title.ilike(f"%{term}%") | HistAlert.detail.ilike(f"%{term}%") | HistAlert.entity_name.ilike(f"%{term}%")
            for term in terms
        )))
    return conditions
