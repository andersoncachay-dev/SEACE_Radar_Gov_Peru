from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AppSetting
from src.keywords import CORE_KEYWORDS, ENTERPRISE_REQUIREMENTS, TARGET_ENTITIES, TARGET_REGIONS

CHILE_REGIONS = [
    "arica y parinacota", "tarapacá", "antofagasta", "atacama", "coquimbo",
    "valparaíso", "metropolitana de santiago", "libertador general bernardo o'higgins",
    "maule", "ñuble", "biobío", "la araucanía", "los ríos", "los lagos",
    "aysén del general carlos ibáñez del campo", "magallanes y de la antártica chilena",
]

FACTOR_DEFAULTS = {
    "keyword": {"label": "Keyword de negocio", "points": 20, "enabled": True, "value": ", ".join(CORE_KEYWORDS), "value_type": "list", "field": "description"},
    "target_entity": {"label": "Entidad objetivo", "points": 15, "enabled": True, "value": ", ".join([*TARGET_ENTITIES, "provias", "mtc"]), "value_type": "list", "field": "entity"},
    "priority_region": {"label": "Región priorizada", "points": 10, "enabled": True, "value": ", ".join(TARGET_REGIONS), "value_type": "list", "field": "region"},
    "attractive_amount": {"label": "Monto atractivo", "points": 10, "enabled": True, "value": "100000", "value_type": "number", "field": "amount"},
    "quick_purchase": {"label": "Compra rápida", "points": 5, "enabled": True, "value": "menor_8", "value_type": "text", "field": "origin"},
    "queries_and_proposal": {"label": "Consultas y propuesta/cotización", "points": 30, "enabled": True, "value": "consultas y propuesta, consulta y cotiz", "value_type": "list", "field": "status"},
    "proposal_only": {"label": "Solo propuesta/cotización", "points": 20, "enabled": True, "value": "vigente para propuesta, solo para propuesta, sólo para propuesta, solo para cotiz, sólo para cotiz", "value_type": "list", "field": "status"},
    "evaluation": {"label": "En evaluación", "points": 5, "enabled": True, "value": "en evalu", "value_type": "list", "field": "status"},
    "closed": {"label": "Proceso cerrado", "points": -35, "enabled": True, "value": "cerrado", "value_type": "list", "field": "status"},
    "enterprise": {"label": "Requisitos enterprise", "points": 10, "enabled": True, "value": ", ".join(ENTERPRISE_REQUIREMENTS), "value_type": "list", "field": "description"},
}


def default_scoring_config(country: str) -> dict:
    normalized = "chile" if str(country).lower() == "chile" else "peru"
    factors = deepcopy(FACTOR_DEFAULTS)
    if normalized == "chile":
        factors["target_entity"]["enabled"] = False
        factors["quick_purchase"]["enabled"] = False
        factors["keyword"]["points"] = 25
        factors["priority_region"]["points"] = 15
        factors["priority_region"]["value"] = ", ".join(CHILE_REGIONS)
        factors["attractive_amount"]["points"] = 15
        factors["queries_and_proposal"]["points"] = 35
        factors["closed"]["value"] = "cerrado, culminado"
    return {
        "country": normalized,
        "priority_a_min": 60 if normalized == "chile" else 70,
        "priority_b_min": 40 if normalized == "chile" else 45,
        "attractive_amount_min": 100000,
        "score_target": 100,
        "factors": factors,
    }


def _key(country: str, field: str) -> str:
    return f"scoring.{country}.{field}"


def get_scoring_config(db: Session, country: str) -> dict:
    config = default_scoring_config(country)
    prefix = f"scoring.{config['country']}."
    items = db.scalars(select(AppSetting).where(AppSetting.key.like(f"{prefix}%"))).all()
    values = {item.key.removeprefix(prefix): item.value for item in items}
    for custom_key in [key for key in values.get("factor_keys", "").split(",") if key.startswith("custom_")]:
        config["factors"][custom_key] = {"label": "Factor adicional", "points": 0, "enabled": True, "value": "", "value_type": "list", "field": "description"}
    for field in ("priority_a_min", "priority_b_min", "attractive_amount_min"):
        if field in values:
            config[field] = int(values[field])
    for factor_key, factor in config["factors"].items():
        if f"{factor_key}.points" in values:
            factor["points"] = int(values[f"{factor_key}.points"])
        if f"{factor_key}.enabled" in values:
            factor["enabled"] = values[f"{factor_key}.enabled"].lower() == "true"
        if f"{factor_key}.value" in values:
            factor["value"] = values[f"{factor_key}.value"]
        for metadata in ("label", "value_type", "field"):
            if f"{factor_key}.{metadata}" in values:
                factor[metadata] = values[f"{factor_key}.{metadata}"]
    config["attractive_amount_min"] = int(config["factors"]["attractive_amount"]["value"])
    return config


def save_scoring_config(db: Session, country: str, payload: dict, user_id: int | None) -> dict:
    normalized = "chile" if str(country).lower() == "chile" else "peru"
    values = {
        "priority_a_min": payload["priority_a_min"],
        "priority_b_min": payload["priority_b_min"],
        "attractive_amount_min": payload["attractive_amount_min"],
        "factor_keys": ",".join(payload["factors"]),
    }
    for factor_key, factor in payload["factors"].items():
        values[f"{factor_key}.points"] = factor["points"]
        values[f"{factor_key}.enabled"] = str(factor["enabled"]).lower()
        values[f"{factor_key}.value"] = factor["value"].strip()
        values[f"{factor_key}.label"] = factor.get("label", "Factor adicional").strip()
        values[f"{factor_key}.value_type"] = factor.get("value_type", "list")
        values[f"{factor_key}.field"] = factor.get("field", "description")
    existing = {
        item.key: item
        for item in db.scalars(select(AppSetting).where(AppSetting.key.like(f"scoring.{normalized}.%"))).all()
    }
    for field, value in values.items():
        key = _key(normalized, field)
        item = existing.get(key)
        if item:
            item.value = str(value)
            item.updated_by_id = user_id
        else:
            db.add(AppSetting(key=key, value=str(value), updated_by_id=user_id))
    db.commit()
    return get_scoring_config(db, normalized)
