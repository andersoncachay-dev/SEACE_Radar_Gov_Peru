"""What differs between Histórico Perú and Histórico Chile.

Both modules share tables (scoped by country, see hist_scope.py), import
pipeline, derived views, alerts, API and screens; only the open-data source,
the classification of procedures/organisations, the currency and a few
labels and thresholds change.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class HistCountry:
    code: str
    module: str  # User.module_access value
    label: str  # "Histórico Perú"
    source_label: str  # shown as "Datos <source_label> al ..."
    timezone: str
    currency: str
    # Local currency per Peruvian sol: alert amount thresholds were calibrated
    # in soles for Peru and are scaled with this for other countries.
    amount_scale: float
    default_refresh_day: int
    # Label of an end date that comes from the official record (Peru: the
    # SEACE contract; Chile: the term declared in the licitación).
    real_date_label: str
    small_purchase_group: str  # process group of the recurring-purchase orders
    api_prefix: str
    job_name: str

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)

    def today(self) -> date:
        return self.now().date()

    def money(self, value: float) -> str:
        return f"{self.currency} {value:,.0f}".replace(",", " " if self.code == "peru" else ".")


PERU = HistCountry(
    code="peru", module="historico_peru", label="Histórico Perú", source_label="CONOSCE", timezone="America/Lima",
    currency="S/", amount_scale=1.0, default_refresh_day=9, real_date_label="Contrato SEACE",
    small_purchase_group="Menores a 8 UIT", api_prefix="/historico", job_name="govradar-historico-peru",
)
CHILE = HistCountry(
    code="chile", module="historico_chile", label="Histórico Chile", source_label="ChileCompra", timezone="America/Santiago",
    currency="CLP", amount_scale=250.0, default_refresh_day=3, real_date_label="Plazo declarado en la licitación",
    small_purchase_group="Compra Ágil y trato directo", api_prefix="/historico-chile", job_name="govradar-historico-chile",
)
COUNTRIES: dict[str, HistCountry] = {PERU.code: PERU, CHILE.code: CHILE}


def get_country(code: str) -> HistCountry:
    return COUNTRIES[code]
