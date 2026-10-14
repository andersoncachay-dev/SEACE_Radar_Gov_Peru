"""Histórico Chile loaders: ChileCompra licitaciones and órdenes de compra
into the shared hist_* tables (the session is pinned to "chile").

Mapping onto the Peru-shaped tables:

* an awarded line of a licitación (``Oferta seleccionada``) is an
  ``adjudicacion`` row, one per line and supplier; the licitación's declared
  contract term (TiempoDuracionContrato) becomes a HistContract, so
  rebuild_expiring computes its end date exactly as for SEACE contracts;
* a purchase order not derived from a licitación (Compra Ágil, trato
  directo, convenio marco) is an ``orden`` row: they feed the history and
  the recurring-purchase view;
* department = región, government_level = ChileCompra "sector".

Relevance uses the UNSPSC ("código ONU") of each line on top of the keyword
classifier: generic Compra Ágil titles and words like "inalámbrico" or
"fibra óptica" otherwise pull in mice, speakers, drills and medical scopes
(measured on 2026-09: ~60% of keyword-only order matches). See onu_gate().

Files are read in 100k-row pandas chunks (the C parser is ~7x faster than
the csv module on the ~700 MB order files); the code gate and a vectorised
keyword pre-filter leave the full classifier only the few candidate rows.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...models import HistContract, HistContracting, HistImportRun
from . import chilecompra
from .classify import DEFAULT_CATEGORY, EQUIPMENT_CATEGORY, Classifier, Match, normalize
from .conosce import SourceFile
from .derive import DEFAULT_START_OFFSET_DAYS

CHUNK_ROWS = 100_000
# Approximate CLP per unit, only for the ~1% of lines priced in USD or UF.
CURRENCY_TO_CLP = {"CLP": 1.0, "USD": 950.0, "CLF": 39_000.0, "EUR": 1_030.0, "UTM": 68_000.0}

LIC_COLUMNS = [
    "CodigoExterno", "Link", "Nombre", "Tipo de Adquisicion", "Estado", "CodigoOrganismo", "NombreOrganismo", "sector",
    "RutUnidad", "NombreUnidad", "RegionUnidad", "Tipo", "CodigoMoneda", "FechaAdjudicacion", "FechaPublicacion",
    "TiempoDuracionContrato", "UnidadTiempoDuracionContrato", "Correlativo", "Rubro1", "Nombre linea Adquisicion",
    "Descripcion linea Adquisicion", "RutProveedor", "NombreProveedor", "MontoLineaAdjudica", "Oferta seleccionada",
    "CodigoProductoONU",
]
OC_COLUMNS = [
    "Codigo", "Nombre", "Descripcion/Obervaciones", "DescripcionTipoOC", "ProcedenciaOC", "Estado", "FechaCreacion",
    "FechaEnvio", "MontoTotalOC_PesosChilenos", "RutUnidadCompra", "UnidadCompra", "CodigoOrganismoPublico",
    "OrganismoPublico", "sector", "RegionUnidadCompra", "RutSucursal", "NombreProveedor", "CodigoLicitacion",
    "NombreroductoGenerico", "EspecificacionComprador", "RubroN1", "codigoProductoONU",
]

# UNSPSC gate. STRONG products are the rubro by themselves; TELECOM families
# count when a keyword also matches; any other known code is not the rubro.
STRONG_ONU = ("811121", "831217")  # Internet service providers / Internet-related services
TELECOM_ONU = ("8311", "8312", "4322", "4320", "4319", "4323", "2612", "3912")  # telecom services, network gear, cabling
EQUIPMENT_ONU = ("4322", "4320", "4319", "2612", "3912")

# ChileCompra licitación type codes (Ley 19.886) grouped like Peru's "tipo de proceso".
_LIC_GROUPS = {
    "L1": "Licitación pública < 100 UTM (L1)",
    "LE": "Licitación pública 100–1.000 UTM (LE)",
    "LP": "Licitación pública 1.000–2.000 UTM (LP)",
    "LQ": "Licitación pública 2.000–5.000 UTM (LQ)",
    "LR": "Licitación pública ≥ 5.000 UTM (LR)",
    "LS": "Licitación pública servicios personales (LS)",
    "E2": "Licitación privada", "CO": "Licitación privada", "B2": "Licitación privada", "H2": "Licitación privada",
    "I2": "Licitación privada", "A1": "Licitación privada", "B1": "Licitación privada", "J2": "Licitación privada",
}
PROCESS_GROUPS = (
    "Compra Ágil", "Trato directo", "Convenio Marco", "Otras órdenes de compra",
    *dict.fromkeys(_LIC_GROUPS.values()), "Otros procedimientos",
)
_SKIPPED_LIC_STATES = ("revocad", "suspendid", "desiert")
_UNIT_DAYS = {"2": 1, "3": 7}  # días, semanas; 4 = meses, 5 = años (relativedelta below)


def licitacion_group(code: str) -> str:
    return _LIC_GROUPS.get((code or "").strip().upper(), "Otros procedimientos")


def order_group(tipo: str, procedencia: str) -> str:
    kind = normalize(tipo)
    if "compra agil" in kind:
        return "Compra Ágil"
    if "trato directo" in kind or "trato directo" in normalize(procedencia):
        return "Trato directo"
    if "convenio marco" in kind:
        return "Convenio Marco"
    return "Otras órdenes de compra"


# Canonical region names (also the keys of the frontend's Chile map), matched
# on the official long names ChileCompra uses ("Región del Libertador General
# Bernardo O´Higgins", "Región Metropolitana de Santiago", ...).
REGIONS = (
    ("arica", "ARICA Y PARINACOTA"), ("tarapac", "TARAPACÁ"), ("antofagasta", "ANTOFAGASTA"), ("atacama", "ATACAMA"),
    ("coquimbo", "COQUIMBO"), ("valpara", "VALPARAÍSO"), ("metropolitana", "METROPOLITANA DE SANTIAGO"),
    ("santiago", "METROPOLITANA DE SANTIAGO"), ("higgins", "O'HIGGINS"), ("maule", "MAULE"), ("nuble", "ÑUBLE"),
    ("biobio", "BIOBÍO"), ("bio bio", "BIOBÍO"), ("araucan", "LA ARAUCANÍA"), ("los rios", "LOS RÍOS"),
    ("los lagos", "LOS LAGOS"), ("aysen", "AYSÉN"), ("aisen", "AYSÉN"), ("magallanes", "MAGALLANES"),
)


def region(value: str) -> str:
    text = normalize(chilecompra.to_text(value))
    for needle, name in REGIONS:
        if needle in text:
            return name
    cleaned = re.sub(r"^region\s+(de\s+la\s+|del\s+|de\s+)?", "", text)
    return cleaned.upper()[:80]


def onu_gate(code: str) -> str:
    code = (code or "").strip()
    if not code or code in ("0", "NA") or not code.isdigit():
        return "unknown"
    if code.startswith(STRONG_ONU):
        return "strong"
    if code.startswith(TELECOM_ONU):
        return "telecom"
    return "other"


def classify_line(classifier: Classifier, text: str, code: str, *, is_order: bool, object_type: str = "") -> Match:
    """Keyword match (classify.py) refined by the line's UNSPSC code."""
    gate = onu_gate(code)
    match = classifier.classify(text, is_order=is_order, object_type=object_type)
    if gate == "strong":
        excluded = match.relevance == "drop" and any(rule.kind == "exclude" for rule in classifier.hits(normalize(text)))
        if excluded:
            return match
        return Match("ok", match.category if match.relevance != "drop" and match.category else DEFAULT_CATEGORY)
    if gate == "other":
        if match.relevance == "drop" or is_order:
            return Match("drop", "")
        return Match("revisar", match.category)
    if match.relevance == "ok" and gate == "telecom" and code.strip().startswith(EQUIPMENT_ONU) and match.category == DEFAULT_CATEGORY:
        return Match("ok", EQUIPMENT_CATEGORY)
    return match


def _gate_mask(codes: pd.Series, *, keep_other: bool) -> pd.Series:
    codes = codes.fillna("").str.strip()
    unknown = ~codes.str.fullmatch(r"\d+") | codes.isin(("0",))
    known = codes.str.startswith(STRONG_ONU) | codes.str.startswith(TELECOM_ONU)
    return unknown | known | keep_other


def _clean(value) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else chilecompra.to_text(str(value))


def _blank_code(value: str) -> bool:
    return value in ("", "NA", "0")


def _prefilter(classifier: Classifier) -> re.Pattern | None:
    """Accent-insensitive stems of the active keywords, run vectorised on raw
    text before the (normalising, slower) classifier."""
    stems = set()
    for rule in classifier.rules:
        if rule.kind == "exclude":
            continue
        words = [word for word in rule.keyword.split() if len(word) >= 3]
        if words:
            stems.add(max(words, key=len))
    if not stems:
        return None
    accent = {"a": "[aá]", "e": "[eé]", "i": "[ií]", "o": "[oó]", "u": "[uúü]", "n": "[nñ]"}
    return re.compile("|".join("".join(accent.get(ch, re.escape(ch)) for ch in stem) for stem in sorted(stems)), re.I)


def _frames(path: Path, columns: list[str]):
    header = next(chilecompra._raw_rows(path), [])
    usecols = [column for column in columns if column in header]
    return pd.read_csv(
        path, sep=";", encoding="latin-1", dtype=str, usecols=usecols, chunksize=CHUNK_ROWS,
        on_bad_lines="skip", engine="c", keep_default_na=False,
    )


def _candidates(chunk: pd.DataFrame, text_columns: list[str], pattern: re.Pattern | None, code_column: str) -> pd.DataFrame:
    present = [column for column in text_columns if column in chunk.columns]
    if not present:
        return chunk.iloc[0:0]
    text = chunk[present[0]].str.cat([chunk[column] for column in present[1:]], sep=" ") if len(present) > 1 else chunk[present[0]]
    chunk = chunk.assign(_text=text)
    strong = chunk[code_column].fillna("").str.strip().str.startswith(STRONG_ONU) if code_column in chunk.columns else False
    if pattern is None:
        return chunk
    return chunk[strong | text.str.contains(pattern.pattern, flags=re.I, regex=True)]


def _term_end(start, amount: str, unit: str):
    from dateutil.relativedelta import relativedelta

    try:
        value = int(float((amount or "0").replace(",", ".")))
    except ValueError:
        return None
    unit = (unit or "").strip()
    if value <= 0:
        return None
    if unit == "4":
        return start + relativedelta(months=value)
    if unit == "5":
        return start + relativedelta(years=value)
    if unit in _UNIT_DAYS:
        return start + timedelta(days=value * _UNIT_DAYS[unit])
    return None


def load_licitaciones(db: Session, run: HistImportRun, classifier: Classifier, source: SourceFile, path: Path, flush) -> int:
    period = f"{source.year:04d}-{source.month:02d}"
    db.execute(delete(HistContracting).where(HistContracting.dataset == "adjudicacion", HistContracting.source_period == period))
    db.commit()
    pattern = _prefilter(classifier)
    pending: list[dict] = []
    contracts: dict[str, dict] = {}
    seen: set[str] = set()
    for chunk in _frames(path, LIC_COLUMNS):
        if "Oferta seleccionada" not in chunk.columns:
            continue
        chunk = chunk[chunk["Oferta seleccionada"].str.strip().eq("Seleccionada")]
        if chunk.empty:
            continue
        for row in _candidates(chunk, ["Nombre", "Nombre linea Adquisicion", "Descripcion linea Adquisicion"], pattern, "CodigoProductoONU").to_dict("records"):
            state = normalize(row.get("Estado"))
            if any(term in state for term in _SKIPPED_LIC_STATES):
                continue
            match = classify_line(classifier, row["_text"], _clean(row.get("CodigoProductoONU")), is_order=False, object_type=_clean(row.get("Rubro1")))
            if match.relevance == "drop":
                continue
            award_date = chilecompra.to_date(row.get("FechaAdjudicacion")) or chilecompra.to_date(row.get("FechaPublicacion"))
            if award_date is None:
                continue
            code = _clean(row.get("CodigoExterno"))
            key = f"{code}|{_clean(row.get('Correlativo'))}|{_clean(row.get('RutProveedor'))}"[:120]
            if key in seen:
                continue
            seen.add(key)
            currency = _clean(row.get("CodigoMoneda")).upper() or "CLP"
            amount = chilecompra.to_float(row.get("MontoLineaAdjudica")) * CURRENCY_TO_CLP.get(currency, 1.0)
            line = " ".join(filter(None, (_clean(row.get("Nombre linea Adquisicion")), _clean(row.get("Descripcion linea Adquisicion")))))
            entity_code = _clean(row.get("CodigoOrganismo"))[:20]
            pending.append({
                "dataset": "adjudicacion",
                "source_key": key,
                "source_period": period,
                "year": award_date.year,
                "month": f"{award_date.year:04d}-{award_date.month:02d}",
                "event_date": award_date,
                "process_group": licitacion_group(_clean(row.get("Tipo"))),
                "procedure": _clean(row.get("Tipo de Adquisicion"))[:160],
                "nomenclature": code[:200],
                "convocatoria_code": code[:30],
                "item_number": _clean(row.get("Correlativo"))[:20],
                "entity_code": entity_code,
                "entity_ruc": _clean(row.get("RutUnidad"))[:20],
                "entity_name": _clean(row.get("NombreOrganismo"))[:300],
                "department": region(_clean(row.get("RegionUnidad"))),
                "description": f"{_clean(row.get('Nombre'))} — {line}" if line else _clean(row.get("Nombre")),
                "category": match.category[:80],
                "amount": round(amount, 2),
                "reference_amount": 0.0,
                "supplier_ruc": _clean(row.get("RutProveedor"))[:20],
                "supplier_name": _clean(row.get("NombreProveedor"))[:300],
                "status": _clean(row.get("Estado"))[:60],
                "direct_cause": "",
                "object_type": _clean(row.get("Rubro1"))[:40],
                "government_level": _clean(row.get("sector"))[:40],
                "relevance": match.relevance,
                "import_run_id": run.id,
            })
            start = award_date + timedelta(days=DEFAULT_START_OFFSET_DAYS)
            end = _term_end(start, _clean(row.get("TiempoDuracionContrato")), _clean(row.get("UnidadTiempoDuracionContrato")))
            if end is not None and code not in contracts:
                contracts[code] = {
                    "contract_code": code[:40], "entity_code": entity_code, "convocatoria_code": code[:30], "item_number": "",
                    "contract_number": f"{_clean(row.get('TiempoDuracionContrato'))} " + {"2": "días", "3": "semanas", "4": "meses", "5": "años"}.get(_clean(row.get("UnidadTiempoDuracionContrato")), ""),
                    "amount_item": 0.0, "amount_additional": 0.0, "amount_reduction": 0.0, "amount_extension": 0.0, "amount_complementary": 0.0,
                    "contractor_ruc": "", "url": _clean(row.get("Link")), "signed_at": None, "start_date": start, "end_date": end, "end_date_updated": None,
                }
            if len(pending) >= 2000:
                flush(db, HistContracting, pending)
    flush(db, HistContracting, pending)
    if contracts:
        codes = list(contracts)
        for index in range(0, len(codes), 500):
            db.execute(delete(HistContract).where(HistContract.contract_code.in_(codes[index:index + 500])))
        flush(db, HistContract, list(contracts.values()))
    db.commit()
    return len(seen)


def load_ordenes(db: Session, run: HistImportRun, classifier: Classifier, source: SourceFile, path: Path, flush) -> int:
    period = f"{source.year:04d}-{source.month:02d}"
    db.execute(delete(HistContracting).where(HistContracting.dataset == "orden", HistContracting.source_period == period))
    db.commit()
    pattern = _prefilter(classifier)
    orders: dict[str, dict] = {}
    for chunk in _frames(path, OC_COLUMNS):
        if "CodigoLicitacion" in chunk.columns:
            # Orders issued from a licitación are already its awarded lines.
            chunk = chunk[chunk["CodigoLicitacion"].str.strip().isin(("", "NA", "0"))]
        if "ProcedenciaOC" in chunk.columns:
            # Installments of a contract awarded by licitación ("Proveniente de
            # licitación pública/privada") are that award, not a new purchase.
            chunk = chunk[~chunk["ProcedenciaOC"].str.contains("licitaci", case=False, regex=False)]
        if "codigoProductoONU" in chunk.columns:
            # Cheap vectorised gate first: most order lines are other products.
            chunk = chunk[_gate_mask(chunk["codigoProductoONU"], keep_other=False)]
        if chunk.empty:
            continue
        for row in _candidates(chunk, ["Nombre", "NombreroductoGenerico", "EspecificacionComprador"], pattern, "codigoProductoONU").to_dict("records"):
            code = _clean(row.get("Codigo"))
            if not code or code in orders:
                continue
            match = classify_line(classifier, row["_text"], _clean(row.get("codigoProductoONU")), is_order=True, object_type=_clean(row.get("RubroN1")))
            if match.relevance != "ok":
                continue
            issued = chilecompra.to_date(row.get("FechaEnvio")) or chilecompra.to_date(row.get("FechaCreacion"))
            if issued is None:
                issued = datetime(source.year, source.month, 1).date()
            group = order_group(_clean(row.get("DescripcionTipoOC")), _clean(row.get("ProcedenciaOC")))
            orders[code] = {
                "dataset": "orden",
                "source_key": code[:120],
                "source_period": period,
                "year": issued.year,
                "month": f"{issued.year:04d}-{issued.month:02d}",
                "event_date": issued,
                "process_group": group,
                "procedure": (_clean(row.get("ProcedenciaOC")) if group == "Trato directo" else _clean(row.get("DescripcionTipoOC")))[:160],
                "nomenclature": code[:200],
                "convocatoria_code": "",
                "item_number": "",
                "entity_code": _clean(row.get("CodigoOrganismoPublico"))[:20],
                "entity_ruc": _clean(row.get("RutUnidadCompra"))[:20],
                "entity_name": _clean(row.get("OrganismoPublico"))[:300],
                "department": region(_clean(row.get("RegionUnidadCompra"))),
                "description": " ".join(filter(None, (_clean(row.get("Nombre")), _clean(row.get("Descripcion/Obervaciones")))))[:4000],
                "category": match.category[:80],
                "amount": round(chilecompra.to_float(row.get("MontoTotalOC_PesosChilenos")), 2),
                "reference_amount": 0.0,
                "supplier_ruc": _clean(row.get("RutSucursal"))[:20],
                "supplier_name": _clean(row.get("NombreProveedor"))[:300],
                "status": _clean(row.get("Estado"))[:60],
                "direct_cause": _clean(row.get("ProcedenciaOC"))[:200] if group == "Trato directo" else "",
                "object_type": _clean(row.get("RubroN1"))[:40],
                "government_level": _clean(row.get("sector"))[:40],
                "relevance": "ok",
                "import_run_id": run.id,
            }
    rows = list(orders.values())
    for index in range(0, len(rows), 2000):
        flush(db, HistContracting, rows[index:index + 2000])
    db.commit()
    return len(orders)


def loaded_periods(db: Session) -> set[tuple[str, str]]:
    return set(db.execute(select(HistContracting.dataset, HistContracting.source_period).distinct()).all())
