from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..models import OpportunityViewState, User
from ..schemas import OpportunityViewStateOut, OpportunityViewStateUpdate

router = APIRouter(prefix="/opportunity-view-states", tags=["opportunity view states"])

_SCOPE_PATTERN = re.compile(r"^(?:radar|ocds)\.(?:Peru|Chile)$")
_MAX_STATE_BYTES = 250_000


def _validate_scope(scope: str) -> str:
    if not _SCOPE_PATTERN.fullmatch(scope):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid opportunity view scope")
    return scope


def _to_output(item: OpportunityViewState) -> OpportunityViewStateOut:
    try:
        state_payload = json.loads(item.state_json)
    except (TypeError, json.JSONDecodeError):
        state_payload = {}
    return OpportunityViewStateOut(scope=item.scope, state=state_payload, updated_at=item.updated_at)


@router.get("/{scope}", response_model=OpportunityViewStateOut)
def get_view_state(
    scope: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_scope = _validate_scope(scope)
    item = db.scalar(
        select(OpportunityViewState).where(
            OpportunityViewState.owner_id == current_user.id,
            OpportunityViewState.scope == normalized_scope,
        )
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Opportunity view state not found")
    return _to_output(item)


@router.put("/{scope}", response_model=OpportunityViewStateOut)
def save_view_state(
    scope: str,
    payload: OpportunityViewStateUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    normalized_scope = _validate_scope(scope)
    serialized = json.dumps(payload.state, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > _MAX_STATE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Opportunity view state is too large")

    item = db.scalar(
        select(OpportunityViewState).where(
            OpportunityViewState.owner_id == current_user.id,
            OpportunityViewState.scope == normalized_scope,
        )
    )
    if item is None:
        item = OpportunityViewState(owner_id=current_user.id, scope=normalized_scope, state_json=serialized)
        db.add(item)
    else:
        item.state_json = serialized
    db.commit()
    db.refresh(item)
    return _to_output(item)
