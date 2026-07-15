from __future__ import annotations

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "entidades_contratantes.csv"

DEPARTMENTS = [
    "AMAZONAS",
    "ANCASH",
    "APURIMAC",
    "AREQUIPA",
    "AYACUCHO",
    "CAJAMARCA",
    "CALLAO",
    "CUSCO",
    "HUANCAVELICA",
    "HUANUCO",
    "ICA",
    "JUNIN",
    "LA LIBERTAD",
    "LAMBAYEQUE",
    "LIMA",
    "LORETO",
    "MADRE DE DIOS",
    "MOQUEGUA",
    "PASCO",
    "PIURA",
    "PUNO",
    "SAN MARTIN",
    "TACNA",
    "TUMBES",
    "UCAYALI",
]

DEPARTMENT_ALIASES = {
    "ANCASH": "ANCASH",
    "APURIMAC": "APURIMAC",
    "HUANUCO": "HUANUCO",
    "JUNIN": "JUNIN",
    "SAN MARTIN": "SAN MARTIN",
    "LIMA METROPOLITANA": "LIMA",
    "PROVINCIA CONSTITUCIONAL DEL CALLAO": "CALLAO",
}

STOPWORDS = {
    "DE",
    "DEL",
    "LA",
    "LAS",
    "LOS",
    "EL",
    "Y",
    "EN",
    "PARA",
    "POR",
    "CON",
    "UNIDAD",
    "GESTION",
    "GOBIERNO",
    "REGIONAL",
}


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()
    return re.sub(r"\s+", " ", text)


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) > 2 and token not in STOPWORDS}


def _detect_department(value: str) -> str:
    key = _normalize(value)
    if not key:
        return ""
    for alias, department in DEPARTMENT_ALIASES.items():
        if f" {alias} " in f" {key} ":
            return department
    for department in DEPARTMENTS:
        if f" {department} " in f" {key} ":
            return department
    return ""


@lru_cache(maxsize=1)
def _load_entities() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    rows: list[dict[str, str]] = []
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with CATALOG_PATH.open("r", encoding=encoding, newline="") as handle:
                rows = list(csv.DictReader(handle, delimiter="|"))
            break
        except UnicodeDecodeError:
            continue
    entities: list[dict[str, Any]] = []
    for row in rows:
        name = (row.get("NOMBRE_DE_ENTIDAD") or "").strip()
        if not name:
            continue
        entities.append(
            {
                "name": name,
                "key": _normalize(name),
                "tokens": _tokens(name),
                "ruc": (row.get("RUC") or "").strip(),
                "region": (row.get("DEPARTAMENTO") or "").strip(),
                "province": (row.get("PROVINCIA") or "").strip(),
                "district": (row.get("DISTRITO") or "").strip(),
                "status": (row.get("ESTADO") or "").strip(),
            }
        )
    return entities


@lru_cache(maxsize=1)
def _entity_index() -> dict[str, dict[str, Any]]:
    return {entity["key"]: entity for entity in _load_entities()}


def find_entity(entity_name: str) -> dict[str, Any] | None:
    key = _normalize(entity_name)
    if not key:
        return None
    digits = re.sub(r"\D+", "", entity_name or "")
    if len(digits) == 11:
        for entity in _load_entities():
            if entity.get("ruc") == digits:
                return entity
    indexed = _entity_index().get(key)
    if indexed:
        return indexed
    if len(key) < 12:
        return None
    best: dict[str, Any] | None = None
    best_score = 0.0
    key_tokens = _tokens(key)
    for entity in _load_entities():
        candidate = entity["key"]
        if len(candidate) >= 12 and (candidate in key or key in candidate):
            return entity
        candidate_tokens = entity.get("tokens") or set()
        if len(key_tokens) >= 3 and len(candidate_tokens) >= 3:
            overlap = len(key_tokens & candidate_tokens)
            denominator = max(1, min(len(key_tokens), len(candidate_tokens)))
            score = overlap / denominator
            if score > best_score:
                best = entity
                best_score = score
    if best and best_score >= 0.75:
        return best
    detected_region = _detect_department(entity_name)
    if detected_region:
        return {
            "name": entity_name,
            "key": key,
            "tokens": key_tokens,
            "ruc": "",
            "region": detected_region,
            "province": "",
            "district": "",
            "status": "",
        }
    return None
