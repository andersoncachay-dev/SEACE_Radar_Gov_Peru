"""Derived commercial views for Histórico Perú (pure functions, no DB).

Labels mirror the v9 workbook so users moving off the Excel recognise them.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .classify import normalize

DEFAULT_START_OFFSET_DAYS = 15  # buena pro -> estimated contract start
DEFAULT_TERM_MONTHS = 12

_NUMBER_WORDS = {
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciocho": 18, "veinte": 20, "veinticuatro": 24,
    "treinta": 30, "treinta y seis": 36, "cuarenta y cinco": 45, "sesenta": 60,
    "noventa": 90, "ciento veinte": 120, "ciento ochenta": 180, "trescientos sesenta y cinco": 365,
}
_NUMBER = r"(\d{1,4}|" + "|".join(sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True)) + r")"
_TERM = re.compile(_NUMBER + r"\s*(?:\(\s*\d{1,4}\s*\)\s*)?(meses|mes|dias|dia|anos|ano)\b")
_PERIOD = re.compile(r"\b(?:periodo|ejercicio|ano fiscal|ano)\s+(20\d\d)\b")
_MONTHLY = re.compile(r"\b(mensual|mensuales|mes de (?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|setiembre|septiembre|octubre|noviembre|diciembre))\b")


@dataclass(frozen=True)
class Term:
    """A contract duration found in a description."""

    months: int = 0
    days: int = 0
    period_year: int = 0

    @property
    def label(self) -> str:
        if self.period_year:
            return f"periodo {self.period_year}"
        if self.months:
            return f"{self.months} meses"
        return f"{self.days} días"

    def end_from(self, start: date) -> date:
        if self.period_year:
            return date(self.period_year, 12, 31)
        if self.months:
            return start + relativedelta(months=self.months)
        return start + timedelta(days=self.days)

    def approx_months(self, start: date) -> float:
        return max(1.0, (self.end_from(start) - start).days / 30.4)


def _to_int(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS.get(token, 0)


def parse_term(description: str) -> Term | None:
    """Duration written in a description: "12 meses", "365 días calendario",
    "doce (12) meses", "dos años", "periodo 2026"."""
    text = normalize(description)
    if not text:
        return None
    period = _PERIOD.search(text)
    term_match = _TERM.search(text)
    if term_match:
        value = _to_int(term_match.group(1))
        unit = term_match.group(2)
        if value > 0:
            if unit.startswith("mes") and value <= 60:
                return Term(months=value)
            if unit.startswith("ano") and value <= 5:
                return Term(months=12 * value)
            if unit.startswith("dia") and 15 <= value <= 1825:
                return Term(days=value)
    if period:
        return Term(period_year=int(period.group(1)))
    return None


def is_monthly_text(description: str) -> bool:
    return bool(_MONTHLY.search(normalize(description)))


# --- contracts > 8 UIT ------------------------------------------------------

EXPIRING_BUCKETS = ("Vence ≤ 90 días", "Vence 91–180 días", "Vence 181–365 días", "Vence > 1 año", "Vencido")


def expiring_bucket(days: int) -> str:
    if days < 0:
        return "Vencido"
    if days <= 90:
        return "Vence ≤ 90 días"
    if days <= 180:
        return "Vence 91–180 días"
    if days <= 365:
        return "Vence 181–365 días"
    return "Vence > 1 año"


@dataclass(frozen=True)
class ContractDates:
    start: date | None
    end: date | None
    end_updated: date | None


@dataclass(frozen=True)
class EndOfTerm:
    start: date
    end: date
    source: str
    is_real: bool
    approx_months: float


def end_of_term(award_date: date, description: str, contract: ContractDates | None = None) -> EndOfTerm:
    """Real end date when SEACE has the contract; otherwise estimated from the
    term written in the description, or 12 months after the buena pro."""
    if contract and (contract.end_updated or contract.end):
        end = contract.end_updated or contract.end
        start = contract.start or award_date + timedelta(days=DEFAULT_START_OFFSET_DAYS)
        source = "Contrato SEACE (vigencia actualizada)" if contract.end_updated else "Contrato SEACE"
        return EndOfTerm(start, end, source, True, max(1.0, (end - start).days / 30.4))
    start = award_date + timedelta(days=DEFAULT_START_OFFSET_DAYS)
    term = parse_term(description)
    if term:
        return EndOfTerm(start, term.end_from(start), f"Estimada: {term.label} (descripción)", False, term.approx_months(start))
    end = start + relativedelta(months=DEFAULT_TERM_MONTHS)
    return EndOfTerm(start, end, "Estimada: 12 meses desde buena pro", False, 12.0)


# --- recurring orders <= 8 UIT ------------------------------------------------

RECURRING_BUCKETS = ("≤ 30 días", "31–90 días", "91–180 días", "181–365 días", "> 1 año", "Atrasada (sin compra reciente)")
PATTERN_MONTHLY = "Mensual / recurrente"
PATTERN_PERIOD = "Por periodo (plazo en descripción)"
PATTERN_REPEATED = "Compras repetidas"
PATTERN_SINGLE = "Compra única"


def recurring_bucket(days: int) -> str:
    if days < 0:
        return "Atrasada (sin compra reciente)"
    if days <= 30:
        return "≤ 30 días"
    if days <= 90:
        return "31–90 días"
    if days <= 180:
        return "91–180 días"
    if days <= 365:
        return "181–365 días"
    return "> 1 año"


@dataclass(frozen=True)
class OrderPoint:
    order_date: date
    description: str


@dataclass(frozen=True)
class NextPurchase:
    pattern: str
    next_date: date


def next_purchase(orders: list[OrderPoint]) -> NextPurchase:
    """Pattern and next expected purchase for one entity + supplier pair."""
    ordered = sorted(orders, key=lambda point: point.order_date)
    last = ordered[-1]
    months = {(point.order_date.year, point.order_date.month) for point in ordered}
    gaps = [(b.order_date - a.order_date).days for a, b in zip(ordered, ordered[1:]) if (b.order_date - a.order_date).days > 0]
    typical_gap = int(statistics.median(gaps)) if gaps else 0
    if len(months) >= 4 or is_monthly_text(last.description):
        gap = typical_gap if 0 < typical_gap <= 45 else 30
        return NextPurchase(PATTERN_MONTHLY, last.order_date + timedelta(days=gap))
    term = parse_term(last.description)
    if term and not term.period_year:
        return NextPurchase(PATTERN_PERIOD, term.end_from(last.order_date))
    if term and term.period_year:
        return NextPurchase(PATTERN_PERIOD, date(term.period_year + 1, 1, 1))
    if len(ordered) >= 2 and typical_gap:
        return NextPurchase(PATTERN_REPEATED, last.order_date + timedelta(days=typical_gap))
    return NextPurchase(PATTERN_SINGLE, last.order_date + relativedelta(months=12))


# --- PAC ----------------------------------------------------------------------

_MONTH_ABBR = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")


def pac_situation(planned_month: int, plan_year: int, cut: date) -> str:
    if plan_year > cut.year or (plan_year == cut.year and planned_month >= cut.month):
        return f"Por convocar (mes previsto ≥ {_MONTH_ABBR[cut.month - 1]})"
    return "Mes previsto ya pasó"
