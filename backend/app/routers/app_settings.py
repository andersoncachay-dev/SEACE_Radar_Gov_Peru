from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin
from ..models import AppSetting, User
from ..schemas import AppSettingsOut, AppSettingsUpdate

router = APIRouter(prefix="/app-settings", tags=["app settings"])

VERSION_KEY = "version_label"
DEFAULT_VERSION_LABEL = "Versión 1.0 (Beta)"


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
