"""Load CONOSCE files into the hist_* tables and rebuild derived views.

Every dataset/period in a run *replaces* what was stored for that same
dataset/period: OECE re-publishes past months with corrections, so merging
would keep stale rows. A run may cover any subset of files (manual uploads),
and only the periods it read are replaced.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ...models import (
    HistContract,
    HistContracting,
    HistEntity,
    HistExpiring,
    HistImportRun,
    HistKeyword,
    HistPacItem,
    HistRecurring,
)
from . import conosce
from .classify import DEFAULT_KEYWORDS, Classifier, build_rules, government_level, normalize, process_group
from .derive import (
    ContractDates,
    OrderPoint,
    end_of_term,
    expiring_bucket,
    next_purchase,
    pac_situation,
    recurring_bucket,
)

logger = logging.getLogger(__name__)
BATCH = 2000
DATASET_ORDER = {"entidades": 0, "adjudicaciones": 1, "directa": 2, "contratos": 3, "pac": 4, "ordenes": 5}
ProgressFn = Callable[[int, str], None]


def lima_today() -> date:
    return (datetime.utcnow() - timedelta(hours=5)).date()


# --- keywords ------------------------------------------------------------------


def ensure_default_keywords(db: Session) -> None:
    if db.scalar(select(HistKeyword.id).limit(1)) is not None:
        return
    for keyword, category, kind, priority in DEFAULT_KEYWORDS:
        db.add(HistKeyword(keyword=keyword, category=category, kind=kind, priority=priority))
    db.commit()


def load_classifier(db: Session) -> Classifier:
    ensure_default_keywords(db)
    rows = db.execute(
        select(HistKeyword.keyword, HistKeyword.category, HistKeyword.kind, HistKeyword.priority).where(HistKeyword.is_active.is_(True))
    ).all()
    return Classifier(build_rules(rows))


# --- run bookkeeping -------------------------------------------------------------


def create_run(db: Session, origin: str, triggered_by_id: int | None = None) -> HistImportRun:
    run = HistImportRun(origin=origin, status="queued", triggered_by_id=triggered_by_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _update_run(db: Session, run: HistImportRun, **fields) -> None:
    for key, value in fields.items():
        setattr(run, key, value)
    db.commit()


# --- entry points ------------------------------------------------------------------


def import_files(
    db: Session,
    run: HistImportRun,
    files: Iterable[tuple[conosce.SourceFile, Path]],
    *,
    today: date | None = None,
    progress: ProgressFn | None = None,
) -> HistImportRun:
    """Load already-downloaded files (manual upload / PC script / job)."""
    today = today or lima_today()
    ordered = sorted(files, key=lambda item: (DATASET_ORDER[item[0].dataset], item[0].year or 0, item[0].month or 0))
    _update_run(db, run, status="running", started_at=datetime.utcnow(), progress=1, message="Procesando archivos",
                files_json=json.dumps([source.filename for source, _ in ordered]))
    try:
        classifier = load_classifier(db)
        for index, (source, path) in enumerate(ordered, start=1):
            message = f"Procesando {source.filename} ({index}/{len(ordered)})"
            _update_run(db, run, progress=int(5 + 80 * (index - 1) / max(1, len(ordered))), message=message)
            if progress:
                progress(run.progress, message)
            load_file(db, run, source, path, classifier)
        finish_import(db, run, today)
    except Exception as exc:  # recorded on the run; callers decide on fallback
        fail_run(db, run, exc)
    return run


def load_file(db: Session, run: HistImportRun, source: conosce.SourceFile, path: Path, classifier: Classifier | None = None) -> int:
    """Load one file into the base tables and add its row count to the run.
    Derived views are left for finish_import, so a run can stream files in
    (PC script uploads) while keeping a single file on disk at a time."""
    loaded = _load_file(db, run, classifier or load_classifier(db), source, path)
    counts = json.loads(run.counts_json or "{}")
    counts[source.dataset] = counts.get(source.dataset, 0) + loaded
    _update_run(db, run, counts_json=json.dumps(counts))
    return loaded


def finish_import(db: Session, run: HistImportRun, today: date) -> HistImportRun:
    from .alerts_service import evaluate_alerts

    _update_run(db, run, status="running", progress=88, message="Calculando vencimientos, recurrentes y PAC")
    counts = json.loads(run.counts_json or "{}")
    counts.update(rebuild_derived(db, today))
    counts["alertas"] = evaluate_alerts(db, today, import_run_id=run.id)
    _update_run(
        db, run, status="completed", finished_at=datetime.utcnow(), progress=100,
        data_cut_date=date(today.year, today.month, 1) - timedelta(days=1),
        counts_json=json.dumps(counts), message="Actualización completada",
    )
    return run


def fail_run(db: Session, run: HistImportRun, exc: Exception) -> None:
    db.rollback()
    logger.exception("Histórico Perú import %s failed", run.id)
    _update_run(db, run, status="failed", finished_at=datetime.utcnow(), error=f"{type(exc).__name__}: {exc}", message="La actualización falló")


def download_and_import(
    db: Session,
    run: HistImportRun,
    work_dir: Path,
    *,
    today: date | None = None,
    proxies: dict | None = None,
    progress: ProgressFn | None = None,
) -> HistImportRun:
    """Full refresh straight from CONOSCE. Each file is downloaded, loaded and
    deleted before the next one (catalogue() is already in load order), so
    disk use stays at one ~70 MB file instead of the ~3 GB catalogue."""
    today = today or lima_today()
    sources = conosce.catalogue(today)
    _update_run(db, run, status="running", started_at=datetime.utcnow(), progress=1, message="Descargando desde CONOSCE",
                files_json=json.dumps([source.filename for source in sources]))
    missing: list[str] = []
    try:
        classifier = load_classifier(db)
        for index, source in enumerate(sources, start=1):
            message = f"Descargando y procesando {source.filename} ({index}/{len(sources)})"
            _update_run(db, run, progress=int(1 + 86 * (index - 1) / len(sources)), message=message)
            if progress:
                progress(run.progress, message)
            try:
                path = conosce.download(source, work_dir, proxies=proxies)
            except FileNotFoundError:
                missing.append(source.filename)  # e.g. a month OECE has not published yet
                continue
            try:
                load_file(db, run, source, path, classifier)
            finally:
                path.unlink(missing_ok=True)
        if missing:
            counts = json.loads(run.counts_json or "{}")
            counts["archivos_no_publicados"] = missing
            _update_run(db, run, counts_json=json.dumps(counts))
        finish_import(db, run, today)
    except Exception as exc:
        fail_run(db, run, exc)
    return run


# --- per-file loaders ------------------------------------------------------------------


def _load_file(db: Session, run: HistImportRun, classifier: Classifier, source: conosce.SourceFile, path: Path) -> int:
    loader = {
        "entidades": _load_entities,
        "adjudicaciones": _load_awards,
        "directa": _load_awards,
        "contratos": _load_contracts,
        "pac": _load_pac,
        "ordenes": _load_orders,
    }[source.dataset]
    return loader(db, run, classifier, source, path)


def _flush(db: Session, model, rows: list[dict]) -> None:
    if rows:
        if model is HistContracting:
            # The same order/item can show up in two CONOSCE files (e.g. an
            # order registered one month and issued the next): the file read
            # last wins instead of tripping the (dataset, source_key) key.
            for dataset in {row["dataset"] for row in rows}:
                keys = [row["source_key"] for row in rows if row["dataset"] == dataset]
                db.execute(delete(HistContracting).where(HistContracting.dataset == dataset, HistContracting.source_key.in_(keys)))
        now = datetime.utcnow()
        for row in rows:
            row.setdefault("created_at", now)
            row.setdefault("updated_at", now)
        db.execute(insert(model), rows)
        rows.clear()


def _load_entities(db: Session, run, classifier, source, path) -> int:
    existing = {entity.ruc: entity for entity in db.scalars(select(HistEntity)).all()}
    count = 0
    for row in conosce.iter_rows(path):
        ruc = conosce.to_text(row.get("ruc"))
        if not ruc:
            continue
        entity = existing.get(ruc) or HistEntity(ruc=ruc)
        entity.name = conosce.to_text(row.get("nombre_de_entidad"))[:300]
        entity.code = conosce.to_text(row.get("codconsucode"))[:20]
        entity.department = conosce.to_text(row.get("departamento")).upper()[:80]
        entity.province = conosce.to_text(row.get("provincia"))[:80]
        entity.district = conosce.to_text(row.get("distrito"))[:80]
        if not entity.government_level:
            entity.government_level = government_level("", entity.name)
        if ruc not in existing:
            db.add(entity)
            existing[ruc] = entity
        count += 1
    db.commit()
    return count


def _load_awards(db: Session, run, classifier: Classifier, source, path) -> int:
    """adjudicaciones (all selection procedures) and directa (adds causal)."""
    is_direct = source.dataset == "directa"
    if not is_direct:
        db.execute(delete(HistContracting).where(HistContracting.dataset == "adjudicacion", HistContracting.source_period == str(source.year)))
        db.commit()
    existing_direct = set()
    if is_direct:
        existing_direct = set(db.scalars(select(HistContracting.source_key).where(HistContracting.dataset == "adjudicacion", HistContracting.source_period == str(source.year))).all())
    levels: dict[str, str] = {}
    pending: list[dict] = []
    count = 0
    for row in conosce.iter_rows(path):
        description = " ".join(filter(None, (conosce.to_text(row.get("descripcion_proceso")), conosce.to_text(row.get("descripcion_item")))))
        object_type = conosce.to_text(row.get("objetocontractual"))
        match = classifier.classify(description, is_order=False, object_type=object_type)
        if match.relevance == "drop":
            continue
        award_date = conosce.to_date(row.get("fecha_buenapro")) or conosce.to_date(row.get("fecha_convocatoria"))
        if award_date is None:
            continue
        key = f"{conosce.to_text(row.get('codigoconvocatoria'))}-{conosce.to_text(row.get('n_item'))}"
        entity_ruc = conosce.to_text(row.get("entidad_ruc"))
        level = government_level(conosce.to_text(row.get("tipoentidad")), conosce.to_text(row.get("entidad")))
        levels[entity_ruc] = level
        cause = conosce.to_text(row.get("causal"))[:200]
        if is_direct and key in existing_direct:
            db.query(HistContracting).filter(HistContracting.dataset == "adjudicacion", HistContracting.source_key == key).update({"direct_cause": cause})
            count += 1
            continue
        procedure = conosce.to_text(row.get("tipoprocesoseleccion"))
        pending.append({
            "dataset": "adjudicacion",
            "source_key": key[:120],
            "source_period": str(source.year),
            "year": award_date.year,
            "month": f"{award_date.year:04d}-{award_date.month:02d}",
            "event_date": award_date,
            "process_group": process_group(procedure),
            "procedure": procedure[:160],
            "nomenclature": conosce.to_text(row.get("proceso"))[:200],
            "convocatoria_code": conosce.to_text(row.get("codigoconvocatoria"))[:30],
            "item_number": conosce.to_text(row.get("n_item"))[:20],
            "entity_code": conosce.to_text(row.get("codigoentidad"))[:20],
            "entity_ruc": entity_ruc[:20],
            "entity_name": conosce.to_text(row.get("entidad"))[:300],
            "department": conosce.to_text(row.get("entidad_departamento")).upper()[:80],
            "description": description,
            "category": match.category[:80],
            "amount": conosce.to_float(row.get("monto_adjudicado_item_soles")),
            "reference_amount": conosce.to_float(row.get("monto_referencial_item_soles")),
            "supplier_ruc": conosce.to_text(row.get("ruc_proveedor"))[:20],
            "supplier_name": conosce.to_text(row.get("proveedor"))[:300],
            "status": conosce.to_text(row.get("estado_item"))[:60],
            "direct_cause": cause,
            "object_type": object_type[:40],
            "government_level": level,
            "relevance": match.relevance,
            "import_run_id": run.id,
        })
        count += 1
        if len(pending) >= BATCH:
            _flush(db, HistContracting, pending)
    _flush(db, HistContracting, pending)
    # SEACE's TIPOENTIDAD is the authoritative government level; carry it to
    # the entity catalogue so <= 8 UIT orders (which lack it) inherit it.
    if levels:
        for entity in db.scalars(select(HistEntity).where(HistEntity.ruc.in_(list(levels)))).all():
            entity.government_level = levels[entity.ruc]
    db.commit()
    return count


def _load_contracts(db: Session, run, classifier, source, path) -> int:
    wanted = {
        (code, conv)
        for code, conv in db.execute(
            select(HistContracting.entity_code, HistContracting.convocatoria_code).where(HistContracting.dataset == "adjudicacion")
        ).all()
    }
    count = 0
    seen: set[str] = set()
    for row in conosce.iter_rows(path):
        entity_code = conosce.to_text(row.get("codigoentidad"))
        conv = conosce.to_text(row.get("codigoconvocatoria"))
        if (entity_code, conv) not in wanted:
            continue
        code = conosce.to_text(row.get("codigo_contrato") or row.get("n_cod_contrato"))[:40]
        if not code or code in seen:
            continue
        seen.add(code)
        contract = db.scalar(select(HistContract).where(HistContract.contract_code == code)) or HistContract(contract_code=code)
        contract.entity_code = entity_code[:20]
        contract.convocatoria_code = conv[:30]
        contract.item_number = conosce.to_text(row.get("num_item"))[:20]
        contract.contract_number = conosce.to_text(row.get("num_contrato"))[:200]
        contract.amount_item = conosce.to_float(row.get("monto_contratado_item"))
        contract.amount_additional = conosce.to_float(row.get("monto_adicional"))
        contract.amount_reduction = conosce.to_float(row.get("monto_reduccion"))
        contract.amount_extension = conosce.to_float(row.get("monto_prorroga"))
        contract.amount_complementary = conosce.to_float(row.get("monto_complementario"))
        contract.contractor_ruc = conosce.to_text(row.get("ruc_contratista"))[:20]
        contract.url = conosce.to_text(row.get("urlcontrato"))
        contract.signed_at = conosce.to_date(row.get("fecha_suscripcion_contrato"))
        contract.start_date = conosce.to_date(row.get("fecha_vigencia_inicial"))
        contract.end_date = conosce.to_date(row.get("fecha_vigencia_final"))
        contract.end_date_updated = conosce.to_date(row.get("fecha_vigencia_fin_actualizada"))
        if contract.id is None:
            db.add(contract)
        count += 1
    db.commit()
    return count


def _load_pac(db: Session, run, classifier: Classifier, source, path) -> int:
    db.execute(delete(HistPacItem).where(HistPacItem.year == source.year))
    db.commit()
    levels = dict(db.execute(select(HistEntity.ruc, HistEntity.government_level)).all())
    pending: list[dict] = []
    seen: set[tuple] = set()
    for row in conosce.iter_rows(path):
        description = " ".join(filter(None, (conosce.to_text(row.get("descripcion_proceso")), conosce.to_text(row.get("descripcion_item")))))
        match = classifier.classify(description, is_order=False, object_type=conosce.to_text(row.get("objetocontractual")))
        if match.relevance != "ok":
            continue
        key = (source.year, conosce.to_text(row.get("codigoentidad")), conosce.to_text(row.get("n_referencia")), conosce.to_text(row.get("n_item")))
        if key in seen:
            continue
        seen.add(key)
        ruc = conosce.to_text(row.get("ruc_entidad"))
        name = conosce.to_text(row.get("entidad"))
        procedure = conosce.to_text(row.get("tipoprocesoseleccion"))
        pending.append({
            "year": source.year,
            "entity_code": key[1][:20],
            "entity_ruc": ruc[:20],
            "entity_name": name[:300],
            "department": conosce.to_text(row.get("departamento_ent")).upper()[:80],
            "government_level": levels.get(ruc) or government_level("", name),
            "version": conosce.to_text(row.get("version"))[:20],
            "reference_number": key[2][:30],
            "process_description": conosce.to_text(row.get("descripcion_proceso")),
            "process_type": procedure[:160],
            "process_group": process_group(procedure),
            "object_type": conosce.to_text(row.get("objetocontractual"))[:40],
            "item_number": key[3][:20],
            "item_description": conosce.to_text(row.get("descripcion_item")),
            "category": match.category[:80],
            "quantity": conosce.to_float(row.get("cantidad")),
            "unit": conosce.to_text(row.get("unidad_medida"))[:80],
            "item_department": conosce.to_text(row.get("departamento")).upper()[:80],
            "province": conosce.to_text(row.get("provincia"))[:80],
            "district": conosce.to_text(row.get("distrito"))[:120],
            "planned_month": int(conosce.to_float(row.get("mes_previsto"))),
            "published_at": conosce.to_date(row.get("fecha_publicacion")),
            "relevance": match.relevance,
        })
        if len(pending) >= BATCH:
            _flush(db, HistPacItem, pending)
    _flush(db, HistPacItem, pending)
    db.commit()
    return len(seen)


def _load_orders(db: Session, run, classifier: Classifier, source, path) -> int:
    month_key = f"{source.year:04d}-{source.month:02d}"
    db.execute(delete(HistContracting).where(HistContracting.dataset == "orden", HistContracting.source_period == month_key))
    db.commit()
    levels = dict(db.execute(select(HistEntity.ruc, HistEntity.government_level)).all())
    pending: list[dict] = []
    seen: set[str] = set()
    for row in conosce.iter_rows(path):
        # Only direct purchases up to 8 UIT; orders derived from a selection
        # procedure are already counted through adjudicaciones.
        if "8 uit" not in normalize(conosce.to_text(row.get("tipodecontratacion"))):
            continue
        description = conosce.to_text(row.get("descripcion_orden"))
        object_type = conosce.to_text(row.get("objetocontractual"))
        match = classifier.classify(description, is_order=True, object_type=object_type)
        if match.relevance != "ok":
            continue
        entity_ruc = conosce.to_text(row.get("ruc_entidad"))
        order_id = conosce.to_text(row.get("orden")) or conosce.to_text(row.get("nro_de_orden"))
        key = f"{entity_ruc}|{order_id}"[:120]
        if key in seen:
            continue
        seen.add(key)
        issued = conosce.to_date(row.get("fecha_de_emision")) or conosce.to_date(row.get("fecha_registro")) or date(source.year, source.month, 1)
        entity_name = conosce.to_text(row.get("entidad"))
        pending.append({
            "dataset": "orden",
            "source_key": key,
            "source_period": month_key,
            "year": issued.year,
            "month": f"{issued.year:04d}-{issued.month:02d}",
            "event_date": issued,
            "process_group": "Menores a 8 UIT",
            "procedure": f"{conosce.to_text(row.get('tipoorden')) or 'Orden'} (≤ 8 UIT)"[:160],
            "nomenclature": order_id[:200],
            "convocatoria_code": "",
            "item_number": "",
            "entity_code": "",
            "entity_ruc": entity_ruc[:20],
            "entity_name": entity_name[:300],
            "department": conosce.to_text(row.get("departamento_entidad")).upper()[:80],
            "description": description,
            "category": match.category[:80],
            "amount": conosce.to_float(row.get("monto_total_orden_original")),
            "reference_amount": 0.0,
            "supplier_ruc": conosce.to_text(row.get("ruc_contratista"))[:20],
            "supplier_name": conosce.to_text(row.get("nombre_razon_contratista"))[:300],
            "status": conosce.to_text(row.get("estadocontratacion"))[:60],
            "direct_cause": "",
            "object_type": object_type[:40],
            "government_level": levels.get(entity_ruc) or government_level("", entity_name),
            "relevance": "ok",
            "import_run_id": run.id,
        })
        if len(pending) >= BATCH:
            _flush(db, HistContracting, pending)
    _flush(db, HistContracting, pending)
    db.commit()
    return len(seen)


# --- derived views ---------------------------------------------------------------------


def rebuild_derived(db: Session, today: date) -> dict[str, int]:
    return {
        "vencimientos": rebuild_expiring(db, today),
        "recurrentes": rebuild_recurring(db, today),
        "pac": refresh_pac(db, today),
    }


def rebuild_expiring(db: Session, today: date) -> int:
    db.execute(delete(HistExpiring))
    awards = db.scalars(
        select(HistContracting).where(HistContracting.dataset == "adjudicacion", HistContracting.relevance == "ok")
    ).all()
    contracts: dict[tuple[str, str, str], HistContract] = {}
    for contract in db.scalars(select(HistContract)).all():
        contracts[(contract.entity_code, contract.convocatoria_code, contract.item_number)] = contract
        contracts.setdefault((contract.entity_code, contract.convocatoria_code, ""), contract)
    # "Posible renovado": the entity awarded a later process in the same category.
    latest_by_entity_category: dict[tuple[str, str], list[tuple[date, str]]] = defaultdict(list)
    for award in awards:
        if award.event_date:
            latest_by_entity_category[(award.entity_ruc, award.category)].append((award.event_date, award.convocatoria_code))
    pending: list[dict] = []
    for award in awards:
        if not award.event_date:
            continue
        contract = contracts.get((award.entity_code, award.convocatoria_code, award.item_number)) or contracts.get(
            (award.entity_code, award.convocatoria_code, "")
        )
        dates = ContractDates(contract.start_date, contract.end_date, contract.end_date_updated) if contract else None
        term = end_of_term(award.event_date, award.description, dates)
        days = (term.end - today).days
        renewed = any(
            when > award.event_date and conv != award.convocatoria_code
            for when, conv in latest_by_entity_category[(award.entity_ruc, award.category)]
        )
        extras = (contract.amount_additional + contract.amount_extension + contract.amount_complementary) if contract else 0.0
        pending.append({
            "contracting_id": award.id,
            "contract_id": contract.id if contract else None,
            "start_date": term.start,
            "end_date": term.end,
            "date_source": term.source[:80],
            "is_real_date": term.is_real,
            "days_to_end": days,
            "bucket": expiring_bucket(days),
            "monthly_amount": round(award.amount / max(1.0, round(term.approx_months)), 2),
            "extras_amount": extras,
            "possibly_renewed": renewed,
        })
        if len(pending) >= BATCH:
            _flush(db, HistExpiring, pending)
    _flush(db, HistExpiring, pending)
    db.commit()
    return db.query(HistExpiring).count()


def rebuild_recurring(db: Session, today: date) -> int:
    db.execute(delete(HistRecurring))
    window_start = today - timedelta(days=365)
    orders = db.execute(
        select(HistContracting).where(
            HistContracting.dataset == "orden",
            HistContracting.event_date >= window_start,
            HistContracting.event_date <= today,
        )
    ).scalars().all()
    orders = [order for order in orders if "anulad" not in normalize(order.status)]
    by_pair: dict[tuple[str, str], list[HistContracting]] = defaultdict(list)
    entity_total: dict[str, float] = defaultdict(float)
    entity_suppliers: dict[str, set[str]] = defaultdict(set)
    for order in orders:
        by_pair[(order.entity_ruc, order.supplier_ruc)].append(order)
        entity_total[order.entity_ruc] += order.amount
        entity_suppliers[order.entity_ruc].add(order.supplier_ruc)
    pending: list[dict] = []
    for (entity_ruc, supplier_ruc), items in by_pair.items():
        items.sort(key=lambda item: item.event_date)
        last = items[-1]
        forecast = next_purchase([OrderPoint(item.event_date, item.description) for item in items])
        days = (forecast.next_date - today).days
        pending.append({
            "entity_ruc": entity_ruc,
            "entity_name": last.entity_name,
            "department": last.department,
            "government_level": last.government_level,
            "supplier_ruc": supplier_ruc,
            "supplier_name": last.supplier_name,
            "category": last.category,
            "orders_12m": len(items),
            "months_12m": len({item.month for item in items}),
            "amount_12m_supplier": round(sum(item.amount for item in items), 2),
            "amount_12m_entity": round(entity_total[entity_ruc], 2),
            "suppliers_12m": len(entity_suppliers[entity_ruc]),
            "last_order_date": last.event_date,
            "last_order_amount": last.amount,
            "last_order_description": last.description,
            "last_order_id": last.id,
            "pattern": forecast.pattern,
            "next_purchase_date": forecast.next_date,
            "days_to_next": days,
            "bucket": recurring_bucket(days),
        })
        if len(pending) >= BATCH:
            _flush(db, HistRecurring, pending)
    _flush(db, HistRecurring, pending)
    db.commit()
    return len(by_pair)


def refresh_pac(db: Session, today: date) -> int:
    awarded_by_year: dict[int, set[str]] = defaultdict(set)
    for year, ruc in db.execute(
        select(HistContracting.year, HistContracting.entity_ruc).where(HistContracting.dataset == "adjudicacion", HistContracting.relevance == "ok")
    ).all():
        awarded_by_year[year].add(ruc)
    items = db.scalars(select(HistPacItem)).all()
    for item in items:
        item.situation = pac_situation(item.planned_month, item.year, today)
        item.already_awarded = item.entity_ruc in awarded_by_year[item.year]
    db.commit()
    return len(items)


def latest_completed_run(db: Session) -> HistImportRun | None:
    return db.scalar(select(HistImportRun).where(HistImportRun.status == "completed").order_by(HistImportRun.finished_at.desc()).limit(1))
