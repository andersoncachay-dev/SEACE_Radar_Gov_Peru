from __future__ import annotations

import json
import logging
import queue
import shutil
import tempfile
import threading
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..dependencies import get_current_user, require_admin, user_has_module
from ..hist_scope import current_country, use_country
from ..models import HistAlert, HistAlertPreference, HistImportRun, HistKeyword, User
from ..services.favorite_service import favorite_keys
from ..services.historico import import_service, notify, orchestration, query_service
from ..services.historico.countries import CHILE, COUNTRIES, get_country
from ..services.historico.alerts_service import (
    ALERT_KINDS,
    PRIORITY_LABELS,
    get_preference,
    join_csv,
    preference_conditions,
    split_csv,
)

# Mounted twice by main.py: at /historico (Perú) and /historico-chile (Chile),
# each with scope_dependency(country), which pins the request's DB session to
# that country (hist_scope) before any endpoint runs.
router = APIRouter(tags=["historico"])
logger = logging.getLogger(__name__)
UPLOAD_ROOT = Path(tempfile.gettempdir()) / "historico_uploads"


def _path_country(request: Request) -> str:
    path = request.url.path
    return CHILE.code if path == CHILE.api_prefix or path.startswith(f"{CHILE.api_prefix}/") else "peru"


def scope_dependency(country: str):
    def dependency(db: Session = Depends(get_db)) -> str:
        use_country(db, country)
        return country

    return dependency


def module_user(request: Request, current_user: User = Depends(get_current_user)) -> User:
    if not user_has_module(current_user, get_country(_path_country(request)).module):
        raise HTTPException(status_code=403, detail="Este modulo no esta habilitado para tu perfil")
    return current_user
LIST_KINDS = ("contrataciones", "vencimientos", "recurrentes", "pac")


def _today(db: Session | None = None) -> date:
    return orchestration.local_now(db).date() if db is not None else orchestration.lima_now().date()


def _filters(
    years: list[int] = Query(default=[]),
    months: list[int] = Query(default=[]),
    departments: list[str] = Query(default=[]),
    categories: list[str] = Query(default=[]),
    process_groups: list[str] = Query(default=[]),
    government_levels: list[str] = Query(default=[]),
    buckets: list[str] = Query(default=[]),
    patterns: list[str] = Query(default=[]),
    situations: list[str] = Query(default=[]),
    datasets: list[str] = Query(default=[]),
    q: str = "",
    relevance: str = "ok",
    real_date_only: bool = False,
    hide_renewed: bool = False,
    min_amount: float = 0,
    favorites_only: bool = False,
    user: User = Depends(module_user),
    db: Session = Depends(get_db),
) -> query_service.Filters:
    return query_service.Filters(
        years=years, months=months, departments=departments, categories=categories, process_groups=process_groups,
        government_levels=government_levels, buckets=buckets, patterns=patterns, situations=situations, datasets=datasets,
        q=q, relevance=relevance, real_date_only=real_date_only, hide_renewed=hide_renewed, min_amount=min_amount,
        favorite_keys=favorite_keys(db, user.id) if favorites_only else None,
    )


def _check_kind(kind: str) -> None:
    if kind not in LIST_KINDS:
        raise HTTPException(status_code=404, detail="Vista no encontrada")


# --- read ----------------------------------------------------------------------------


@router.get("/status")
def get_status(_: User = Depends(module_user), db: Session = Depends(get_db)):
    return orchestration.status(db)


@router.get("/filters")
def get_filters(_: User = Depends(module_user), db: Session = Depends(get_db)):
    return query_service.filter_options(db)


@router.get("/vencimientos-runway")
def get_runway(filters: query_service.Filters = Depends(_filters), _: User = Depends(module_user), db: Session = Depends(get_db)):
    """Contracts ending in the next 12 months under the page's filters."""
    return query_service.expiring_runway(db, filters, _today(db))


@router.get("/pac-summary")
def get_pac_summary(filters: query_service.Filters = Depends(_filters), _: User = Depends(module_user), db: Session = Depends(get_db)):
    return query_service.pac_summary(db, filters)


@router.get("/summary")
def get_summary(filters: query_service.Filters = Depends(_filters), _: User = Depends(module_user), db: Session = Depends(get_db)):
    return query_service.summary(db, filters, _today(db))


# --- alerts --------------------------------------------------------------------------


class AlertUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(nueva|vista|en_gestion|descartada)$")
    assignee_id: int | None = None


def _alert_dict(alert: HistAlert) -> dict:
    return {
        "id": alert.id, "kind": alert.kind, "priority": alert.priority, "priority_label": PRIORITY_LABELS.get(alert.priority, alert.priority),
        "score": alert.score, "title": alert.title, "detail": alert.detail, "entity_name": alert.entity_name, "department": alert.department,
        "amount": alert.amount, "due_date": alert.due_date.isoformat() if alert.due_date else None, "status": alert.status,
        "category": alert.category, "process_group": alert.process_group, "government_level": alert.government_level,
        "assignee_id": alert.assignee_id, "expiring_id": alert.expiring_id, "recurring_id": alert.recurring_id, "pac_item_id": alert.pac_item_id,
        "created_at": alert.created_at.isoformat(), "is_active": alert.is_active,
    }


class AlertPreferenceIn(BaseModel):
    kinds: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    government_levels: list[str] = Field(default_factory=list)
    process_groups: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    min_amount: float = Field(default=0, ge=0)
    min_priority: str = Field(default="P4", pattern="^P[1-4]$")
    historico_digest: bool | None = None


def _preference_dict(preference: HistAlertPreference | None, user: User) -> dict:
    return {
        "configured": preference is not None,
        "kinds": split_csv(preference.kinds) if preference else [],
        "categories": split_csv(preference.categories) if preference else [],
        "departments": split_csv(preference.departments) if preference else [],
        "government_levels": split_csv(preference.government_levels) if preference else [],
        "process_groups": split_csv(preference.process_groups) if preference else [],
        "keywords": split_csv(preference.keywords) if preference else [],
        "min_amount": preference.min_amount if preference else 0,
        "min_priority": preference.min_priority if preference else "P4",
        "historico_digest": user.historico_digest,
    }


@router.get("/alerts/preferences")
def get_alert_preferences(user: User = Depends(module_user), db: Session = Depends(get_db)):
    return _preference_dict(get_preference(db, user.id), user)


@router.put("/alerts/preferences")
def save_alert_preferences(payload: AlertPreferenceIn, user: User = Depends(module_user), db: Session = Depends(get_db)):
    preference = get_preference(db, user.id) or HistAlertPreference(user_id=user.id)
    draft = _draft_preference(payload, user.id)
    for field in ("kinds", "categories", "departments", "government_levels", "process_groups", "keywords", "min_amount", "min_priority"):
        setattr(preference, field, getattr(draft, field))
    if preference.id is None:
        db.add(preference)
    if payload.historico_digest is not None:
        user.historico_digest = payload.historico_digest  # same request session as get_current_user
    db.commit()
    return _preference_dict(preference, user)


def _draft_preference(payload: AlertPreferenceIn, user_id: int) -> HistAlertPreference:
    return HistAlertPreference(
        user_id=user_id,
        kinds=join_csv([kind for kind in payload.kinds if kind in ALERT_KINDS]),
        categories=join_csv(payload.categories),
        departments=join_csv(payload.departments),
        government_levels=join_csv(payload.government_levels),
        process_groups=join_csv(payload.process_groups),
        keywords=join_csv([term[:60] for term in payload.keywords]),
        min_amount=payload.min_amount,
        min_priority=payload.min_priority,
    )


@router.post("/alerts/preview")
def preview_alert_preferences(payload: AlertPreferenceIn, user: User = Depends(module_user), db: Session = Depends(get_db)):
    """Live count for the "Configurar mis alertas" panel, before saving."""
    conditions = [HistAlert.is_active.is_(True), HistAlert.status != "descartada", *preference_conditions(_draft_preference(payload, user.id))]
    counts = dict(db.execute(select(HistAlert.priority, func.count()).where(*conditions).group_by(HistAlert.priority)).all())
    return {"total": sum(counts.values()), "counts": {p: counts.get(p, 0) for p in PRIORITY_LABELS}}


@router.get("/alerts/list")
def list_alerts(
    kinds: list[str] = Query(default=[]),
    priorities: list[str] = Query(default=[]),
    statuses: list[str] = Query(default=[]),
    departments: list[str] = Query(default=[]),
    categories: list[str] = Query(default=[]),
    q: str = "",
    mine: bool = False,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(module_user),
    db: Session = Depends(get_db),
):
    """mine=true narrows to the user's saved alert preferences ("Mis alertas")."""
    scope = [HistAlert.is_active.is_(True), *(preference_conditions(get_preference(db, user.id)) if mine else [])]
    where = list(scope)
    if categories:
        where.append(HistAlert.category.in_(categories))
    if kinds:
        where.append(HistAlert.kind.in_(kinds))
    if priorities:
        where.append(HistAlert.priority.in_(priorities))
    where.append(HistAlert.status.in_(statuses) if statuses else HistAlert.status != "descartada")
    if departments:
        where.append(HistAlert.department.in_(departments))
    if q.strip():
        where.append(HistAlert.title.ilike(f"%{q.strip()}%") | HistAlert.entity_name.ilike(f"%{q.strip()}%"))
    size = min(max(page_size, 1), query_service.MAX_PAGE_SIZE)
    total = db.scalar(select(func.count()).select_from(HistAlert).where(*where))
    rows = db.scalars(select(HistAlert).where(*where).order_by(HistAlert.priority, HistAlert.score.desc()).offset((max(page, 1) - 1) * size).limit(size)).all()
    counts = dict(db.execute(
        select(HistAlert.priority, func.count()).where(*scope, HistAlert.status != "descartada").group_by(HistAlert.priority)
    ).all())
    return {"items": [_alert_dict(row) for row in rows], "total": total, "page": max(page, 1), "page_size": size,
            "counts": {p: counts.get(p, 0) for p in PRIORITY_LABELS}}


@router.patch("/alerts/{alert_id}")
def update_alert(alert_id: int, payload: AlertUpdate, _: User = Depends(module_user), db: Session = Depends(get_db)):
    alert = db.get(HistAlert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    if payload.status:
        alert.status = payload.status
        alert.dismissed_due_date = alert.due_date if payload.status == "descartada" else None
    if "assignee_id" in payload.model_fields_set:
        alert.assignee_id = payload.assignee_id
    db.commit()
    return _alert_dict(alert)


# --- administration ---------------------------------------------------------------


class KeywordIn(BaseModel):
    keyword: str = Field(min_length=2, max_length=120)
    category: str = Field(default="Internet (sin especificar)", max_length=80)
    kind: str = Field(default="include", pattern="^(include|review|exclude)$")
    priority: int = Field(default=90, ge=1, le=999)
    is_active: bool = True


def _keyword_dict(item: HistKeyword) -> dict:
    return {"id": item.id, "keyword": item.keyword, "category": item.category, "kind": item.kind, "priority": item.priority, "is_active": item.is_active}


@router.get("/admin/keywords")
def list_keywords(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    import_service.ensure_default_keywords(db)
    return [_keyword_dict(item) for item in db.scalars(select(HistKeyword).order_by(HistKeyword.priority, HistKeyword.keyword)).all()]


@router.post("/admin/keywords", status_code=201)
def create_keyword(payload: KeywordIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    keyword = payload.keyword.strip().lower()
    if db.scalar(select(HistKeyword).where(func.lower(HistKeyword.keyword) == keyword)):
        raise HTTPException(status_code=409, detail="La palabra clave ya existe")
    item = HistKeyword(keyword=keyword, category=payload.category.strip(), kind=payload.kind, priority=payload.priority, is_active=payload.is_active)
    db.add(item)
    db.commit()
    return _keyword_dict(item)


@router.put("/admin/keywords/{keyword_id}")
def update_keyword(keyword_id: int, payload: KeywordIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(HistKeyword, keyword_id)
    if not item:
        raise HTTPException(status_code=404, detail="Palabra clave no encontrada")
    item.keyword, item.category, item.kind = payload.keyword.strip().lower(), payload.category.strip(), payload.kind
    item.priority, item.is_active = payload.priority, payload.is_active
    db.commit()
    return _keyword_dict(item)


@router.delete("/admin/keywords/{keyword_id}", status_code=204)
def delete_keyword(keyword_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(HistKeyword, keyword_id)
    if item:
        db.delete(item)
        db.commit()
    return Response(status_code=204)


def _run_dict(run: HistImportRun) -> dict:
    return {
        "id": run.id, "origin": run.origin, "status": run.status, "progress": run.progress, "message": run.message, "error": run.error,
        "files": json.loads(run.files_json or "[]"), "counts": json.loads(run.counts_json or "{}"),
        "data_cut_date": run.data_cut_date.isoformat() if run.data_cut_date else None,
        "created_at": run.created_at.isoformat(), "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


class SettingsIn(BaseModel):
    refresh_day: int = Field(ge=1, le=28)


@router.get("/admin/imports")
def list_imports(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    runs = db.scalars(select(HistImportRun).order_by(HistImportRun.created_at.desc()).limit(30)).all()
    return {"status": orchestration.status(db), "runs": [_run_dict(run) for run in runs]}


@router.put("/admin/settings")
def update_settings(payload: SettingsIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    orchestration.set_setting(db, orchestration.KEY_REFRESH_DAY, str(payload.refresh_day), user.id)
    return orchestration.status(db)


@router.post("/admin/refresh")
def request_refresh(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Ask the hourly govradar-historico-<country> job to run a full refresh."""
    orchestration.request_refresh(db, user.id)
    return orchestration.status(db)


@router.post("/admin/imports", status_code=201)
def create_upload_run(origin: str = "manual_upload", user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if origin not in ("manual_upload", "pc_script"):
        raise HTTPException(status_code=400, detail="Origen no válido")
    if orchestration.running_import(db):
        raise HTTPException(status_code=409, detail="Ya hay una actualización en curso")
    run = import_service.create_run(db, origin, user.id)
    run.status, run.message = "receiving", "Esperando archivos"
    db.commit()
    (UPLOAD_ROOT / str(run.id)).mkdir(parents=True, exist_ok=True)
    return _run_dict(run)


@router.post("/admin/imports/{run_id}/files")
def upload_file(run_id: int, file: UploadFile = File(...), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = db.get(HistImportRun, run_id)
    if not run or run.status != "receiving":
        raise HTTPException(status_code=409, detail="La carga no admite más archivos")
    module = import_service.source_module(db)
    folder = UPLOAD_ROOT / str(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    incoming = folder / f"incoming-{Path(file.filename or 'archivo').name}"
    with incoming.open("wb") as handle:
        shutil.copyfileobj(file.file, handle, length=1 << 20)
    source = module.identify_file(file.filename or "", incoming)
    if source is None:
        incoming.unlink(missing_ok=True)
        label = get_country(current_country(db)).source_label
        raise HTTPException(status_code=400, detail=f"No se reconoce el archivo {file.filename}: usa los nombres originales de {label}")
    target = folder / source.filename
    incoming.replace(target)
    files = json.loads(run.files_json or "[]")
    if source.filename not in files:
        files.append(source.filename)
    run.files_json = json.dumps(files)
    db.commit()
    if run.origin == "pc_script":
        # The PC script sends the whole ~3 GB catalogue, in load order; load
        # each file as it lands so only one sits on the API's ephemeral disk.
        _enqueue(_load_uploaded, current_country(db), run_id, target)
    return {"filename": source.filename, "dataset": source.dataset, "year": source.year, "month": source.month}


# One worker drains a FIFO queue: uploads must load in arrival order (awards
# before contracts) and never run concurrently with each other.
_work_queue: "queue.Queue[tuple]" = queue.Queue()
_worker_started = threading.Lock()
_worker: threading.Thread | None = None


def _enqueue(func, *args) -> None:
    global _worker
    with _worker_started:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_drain_queue, daemon=True, name="historico-imports")
            _worker.start()
    _work_queue.put((func, args))


def _drain_queue() -> None:
    while True:
        func, args = _work_queue.get()
        try:
            func(*args)
        except Exception:  # tasks record their own failure on the run; keep the worker alive
            logger.exception("Histórico background task %s failed", getattr(func, "__name__", func))
        finally:
            _work_queue.task_done()


def _load_uploaded(country: str, run_id: int, path: Path) -> None:
    db = use_country(SessionLocal(), country)
    try:
        run = db.get(HistImportRun, run_id)
        if run is None or run.status not in ("receiving", "running"):
            return
        source = import_service.source_module(db).identify_file(path.name)
        run.message = f"Procesando {path.name}"
        db.commit()
        try:
            import_service.load_file(db, run, source, path)
        except Exception as exc:
            import_service.fail_run(db, run, exc)
    finally:
        path.unlink(missing_ok=True)
        db.close()


def _finish_uploaded(country: str, run_id: int) -> None:
    db = use_country(SessionLocal(), country)
    try:
        run = db.get(HistImportRun, run_id)
        if run is None or run.status == "failed":
            return
        folder = UPLOAD_ROOT / str(run_id)
        module = import_service.source_module(db)
        if run.origin == "pc_script":
            import_service.finish_import(db, run, _today(db))  # files already loaded one by one
        else:
            files = [(module.identify_file(path.name), path) for path in sorted(folder.glob("*"))]
            import_service.import_files(db, run, [(source, path) for source, path in files if source], today=_today(db))
        if run.status == "completed" and run.origin == "pc_script":
            orchestration.record_job_result(db, run)
    except Exception as exc:
        import_service.fail_run(db, run, exc)
    finally:
        shutil.rmtree(UPLOAD_ROOT / str(run_id), ignore_errors=True)
        db.close()


@router.post("/admin/imports/{run_id}/process")
def process_upload(run_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = db.get(HistImportRun, run_id)
    if not run or run.status != "receiving":
        raise HTTPException(status_code=409, detail="La carga ya fue procesada")
    if not json.loads(run.files_json or "[]"):
        raise HTTPException(status_code=400, detail="Sube al menos un archivo")
    run.status, run.message = "queued", "En cola"
    db.commit()
    _enqueue(_finish_uploaded, current_country(db), run_id)
    return _run_dict(run)


@router.get("/admin/imports/{run_id}")
def get_import(run_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    run = db.get(HistImportRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Carga no encontrada")
    return _run_dict(run)


class FallbackFailure(BaseModel):
    reason: str = Field(default="el script de la PC no pudo completar la carga", max_length=500)


@router.post("/admin/fallback-failed")
def report_fallback_failure(payload: FallbackFailure, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Called by the PC script when it also fails: ask admins for a manual upload."""
    sent = 0
    if orchestration.manual_notice_due(db, pc_failed=True):
        sent = notify.send_manual_upload_notice(db, payload.reason)
        orchestration.mark_manual_notice_sent(db)
    return {"notified": sent}


# --- generic list routes: registered last so /{kind}/{id} never shadows
# the static /alerts/... and /admin/... paths above ---------------------------


@router.get("/{kind}/export.xlsx")
def export(kind: str, sort: str | None = None, filters: query_service.Filters = Depends(_filters), _: User = Depends(module_user), db: Session = Depends(get_db)):
    _check_kind(kind)
    content = query_service.export_xlsx(db, kind, filters, sort)
    filename = f"Historico Peru - {kind} {_today():%Y-%m-%d}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{kind}/buckets")
def get_buckets(kind: str, filters: query_service.Filters = Depends(_filters), _: User = Depends(module_user), db: Session = Depends(get_db)):
    if kind not in ("vencimientos", "recurrentes"):
        raise HTTPException(status_code=404, detail="Vista no encontrada")
    return query_service.bucket_counts(db, kind, filters)


@router.get("/{kind}/{record_id}")
def get_detail(kind: str, record_id: int, _: User = Depends(module_user), db: Session = Depends(get_db)):
    _check_kind(kind)
    found = query_service.detail(db, kind, record_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Registro no encontrado")
    return found


@router.get("/{kind}")
def get_list(
    kind: str,
    page: int = 1,
    page_size: int = 50,
    sort: str | None = None,
    filters: query_service.Filters = Depends(_filters),
    _: User = Depends(module_user),
    db: Session = Depends(get_db),
):
    _check_kind(kind)
    lister = {
        "contrataciones": query_service.list_contractings,
        "vencimientos": query_service.list_expiring,
        "recurrentes": query_service.list_recurring,
        "pac": query_service.list_pac,
    }[kind]
    kwargs = {"page": page, "page_size": page_size}
    if sort:
        kwargs["sort"] = sort
    return lister(db, filters, **kwargs)
