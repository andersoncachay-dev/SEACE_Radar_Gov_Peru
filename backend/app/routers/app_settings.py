from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import AppSetting, User
from ..radar_config import SUPPORTED_COUNTRIES
from ..schemas import (
    AppSettingsOut,
    AppSettingsUpdate,
    SchedulerIntervalOut,
    SchedulerIntervalUpdate,
    TenantBrandIn,
    TenantBrandOut,
    ScoringConfigOut,
    ScoringConfigUpdate,
    TrackingDateRefreshStatusOut,
)
from ..services.scoring_config_service import FACTOR_DEFAULTS, get_scoring_config, save_scoring_config
from ..services.scheduler_service import save_scheduler_interval, scheduler_interval_config, update_tracking_date_refresh_interval

router = APIRouter(prefix="/app-settings", tags=["app settings"])

VERSION_KEY = "version_label"
DEFAULT_VERSION_LABEL = "Versión 1.0 (Beta)"

BRAND_KEY = "tenant_brand"
DEFAULT_BRAND = {"name": "RODAR Consulting", "logoUrl": "/assets/Rodarfondoblanco.png", "primary": "#185bc1"}
# Logos are stored inline as raster data URLs (no SVG: it can carry script) or
# point at a bundled /assets file. ~300 KB of base64 keeps the row small.
_LOGO_DATA_URL = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$")
_LOGO_ASSET = re.compile(r"^/assets/[A-Za-z0-9._-]+\.(png|jpe?g|webp|svg)$")
MAX_LOGO_CHARS = 400_000


def _brand_out(item: AppSetting | None) -> TenantBrandOut:
    brand = dict(DEFAULT_BRAND)
    if item:
        try:
            stored = json.loads(item.value)
            if isinstance(stored, dict):
                brand.update({key: stored[key] for key in DEFAULT_BRAND if isinstance(stored.get(key), str)})
        except ValueError:
            pass
    return TenantBrandOut(**brand, updated_at=item.updated_at if item else None)


def _settings_out(item: AppSetting | None) -> AppSettingsOut:
    return AppSettingsOut(
        version_label=item.value if item else DEFAULT_VERSION_LABEL,
        updated_at=item.updated_at if item else None,
    )


@router.get("", response_model=AppSettingsOut)
def get_app_settings(db: Session = Depends(get_db)):
    item = db.scalar(select(AppSetting).where(AppSetting.key == VERSION_KEY))
    return _settings_out(item)


@router.put("", response_model=AppSettingsOut)
def update_app_settings(
    payload: AppSettingsUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    version_label = payload.version_label.strip()
    if len(version_label) < 3:
        raise HTTPException(status_code=422, detail="La versión debe contener al menos 3 caracteres")
    item = db.scalar(select(AppSetting).where(AppSetting.key == VERSION_KEY))
    if item:
        item.value = version_label
        item.updated_by_id = current_user.id
    else:
        item = AppSetting(key=VERSION_KEY, value=version_label, updated_by_id=current_user.id)
        db.add(item)
    db.commit()
    db.refresh(item)
    return _settings_out(item)


@router.get("/brand", response_model=TenantBrandOut)
def get_tenant_brand(db: Session = Depends(get_db)):
    return _brand_out(db.scalar(select(AppSetting).where(AppSetting.key == BRAND_KEY)))


@router.put("/brand", response_model=TenantBrandOut)
def update_tenant_brand(
    payload: TenantBrandIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    logo = payload.logoUrl.strip()
    if len(logo) > MAX_LOGO_CHARS or not (_LOGO_DATA_URL.match(logo) or _LOGO_ASSET.match(logo)):
        raise HTTPException(status_code=422, detail="El logo debe ser una imagen PNG, JPG o WebP de hasta 300 KB")
    value = json.dumps({"name": payload.name.strip(), "logoUrl": logo, "primary": payload.primary.lower()})
    item = db.scalar(select(AppSetting).where(AppSetting.key == BRAND_KEY))
    if item:
        item.value = value
        item.updated_by_id = current_user.id
    else:
        item = AppSetting(key=BRAND_KEY, value=value, updated_by_id=current_user.id)
        db.add(item)
    db.commit()
    db.refresh(item)
    return _brand_out(item)


@router.get("/scheduler/{country}", response_model=SchedulerIntervalOut)
def scheduler_interval_settings(
    country: str,
    current_user: User = Depends(require_admin),
):
    if country not in SUPPORTED_COUNTRIES:
        raise HTTPException(status_code=404, detail="País no soportado")
    return scheduler_interval_config(country)


@router.put("/scheduler/{country}", response_model=SchedulerIntervalOut)
def update_scheduler_interval_settings(
    country: str,
    payload: SchedulerIntervalUpdate,
    current_user: User = Depends(require_admin),
):
    if country not in SUPPORTED_COUNTRIES:
        raise HTTPException(status_code=404, detail="País no soportado")
    interval_seconds = payload.days * 86_400 + payload.hours * 3_600 + payload.minutes * 60
    return save_scheduler_interval(country, interval_seconds, current_user.id)


@router.put("/tracking-date-refresh/{country}", response_model=TrackingDateRefreshStatusOut)
def update_tracking_date_refresh_settings(
    country: str,
    payload: SchedulerIntervalUpdate,
    current_user: User = Depends(require_admin),
):
    if country not in SUPPORTED_COUNTRIES:
        raise HTTPException(status_code=404, detail="País no soportado")
    interval_seconds = payload.days * 86_400 + payload.hours * 3_600 + payload.minutes * 60
    return update_tracking_date_refresh_interval(country, interval_seconds, current_user.id)


@router.get("/scoring/{country}", response_model=ScoringConfigOut)
def scoring_settings(country: str, current_user: User = Depends(require_admin), db: Session = Depends(get_db)):
    if country not in SUPPORTED_COUNTRIES:
        raise HTTPException(status_code=404, detail="País no soportado")
    return get_scoring_config(db, country)


@router.put("/scoring/{country}", response_model=ScoringConfigOut)
def update_scoring_settings(
    country: str,
    payload: ScoringConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if country not in SUPPORTED_COUNTRIES:
        raise HTTPException(status_code=404, detail="País no soportado")
    if not set(FACTOR_DEFAULTS).issubset(set(payload.factors)) or any(not key.startswith("custom_") and key not in FACTOR_DEFAULTS for key in payload.factors):
        raise HTTPException(status_code=422, detail="La lista de factores de score no es válida")
    return save_scoring_config(db, country, payload.model_dump(), current_user.id)
