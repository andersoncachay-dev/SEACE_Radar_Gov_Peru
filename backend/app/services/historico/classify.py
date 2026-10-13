"""Rubro filter and categorisation for Histórico Perú.

Ports the rules in the "Notas" sheet of SEACE_Internet_Procesos_2023_2026_v9.xlsx:
keyword match on the process/item/order description, a keyword-driven
category, the grouped "tipo de proceso" and the "nivel de gobierno".
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from src.keyword_matching import contains_complete_phrase

DEFAULT_CATEGORY = "Internet (sin especificar)"

# (keyword, category, kind, priority). Lower priority wins when several
# category keywords match the same description. "include" makes a row part of
# the rubro; "review" alone only queues > 8 UIT rows for manual review;
# "exclude" marks known false positives.
DEFAULT_KEYWORDS: tuple[tuple[str, str, str, int], ...] = (
    ("starlink", "Satelital - Starlink", "include", 10),
    ("fibra optica", "Fibra óptica", "include", 20),
    ("vsat", "Satelital (otros)", "include", 30),
    ("satelital", "Satelital (otros)", "include", 30),
    ("radioenlace", "Inalámbrico / radioenlace", "include", 40),
    ("radio enlace", "Inalámbrico / radioenlace", "include", 40),
    ("wifi", "Inalámbrico / radioenlace", "include", 40),
    ("wi-fi", "Inalámbrico / radioenlace", "include", 40),
    ("inalambrico", "Inalámbrico / radioenlace", "include", 45),
    ("plan de datos", "Móvil / datos", "include", 50),
    ("datos moviles", "Móvil / datos", "include", 50),
    ("internet movil", "Móvil / datos", "include", 50),
    ("enlace dedicado", "Enlace dedicado / datos", "include", 60),
    ("mpls", "Enlace dedicado / datos", "include", 60),
    ("enlace de datos", "Enlace dedicado / datos", "include", 60),
    ("transmision de datos", "Enlace dedicado / datos", "include", 60),
    ("internet", DEFAULT_CATEGORY, "include", 90),
    ("conectividad", DEFAULT_CATEGORY, "include", 90),
    ("banda ancha", DEFAULT_CATEGORY, "include", 90),
    ("mbps", DEFAULT_CATEGORY, "include", 90),
    ("telecomunicaciones", "Telecom relacionado", "review", 95),
    ("satelite", "Satelital (otros)", "review", 95),
    ("internet de las cosas", DEFAULT_CATEGORY, "exclude", 100),
    ("seguros", DEFAULT_CATEGORY, "exclude", 100),
    ("poliza", DEFAULT_CATEGORY, "exclude", 100),
)

EQUIPMENT_TERMS = ("router", "antena", "modem", "switch", "access point", "equipo", "equipos", "transductor")
EQUIPMENT_CATEGORY = "Equipamiento"

PROCESS_GROUPS = (
    "Menores a 8 UIT",
    "Adjudicación Simplificada",
    "Comparación de Precios",
    "Concurso Público",
    "Concurso Público Abreviado",
    "Licitación Pública",
    "Licitación Pública Abreviada",
    "Subasta Inversa Electrónica",
    "Contratación Directa",
    "Otros procedimientos",
)

GOVERNMENT_LEVELS = ("Gobierno Nacional", "Gobierno Regional", "Gobierno Local", "Empresas públicas")


def normalize(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().lower()


@dataclass(frozen=True)
class KeywordRule:
    keyword: str
    category: str
    kind: str
    priority: int


@dataclass(frozen=True)
class Match:
    relevance: str  # ok | revisar | drop
    category: str


def build_rules(rows: Iterable[tuple[str, str, str, int]]) -> list[KeywordRule]:
    rules = [KeywordRule(normalize(k), c, kind, int(p)) for k, c, kind, p in rows if normalize(k)]
    return sorted(rules, key=lambda rule: (rule.priority, -len(rule.keyword)))


DEFAULT_RULES = build_rules(DEFAULT_KEYWORDS)


class Classifier:
    """All keyword rules compiled into one alternation, so the ~18M monthly
    order rows cost one regex scan each instead of one per keyword."""

    def __init__(self, rules: list[KeywordRule]):
        self.rules = rules
        self._by_keyword = {}
        for rule in rules:
            self._by_keyword.setdefault(rule.keyword, rule)
        alternation = "|".join(
            r"\s+".join(re.escape(word) for word in keyword.split())
            for keyword in sorted(self._by_keyword, key=len, reverse=True)
        )
        self._pattern = re.compile(rf"(?<!\w)(?:{alternation})(?!\w)") if alternation else None

    def hits(self, haystack: str) -> list[KeywordRule]:
        if not self._pattern or not haystack:
            return []
        found = {" ".join(match.group(0).split()) for match in self._pattern.finditer(haystack)}
        # Overlapping phrases ("internet" inside "internet movil") are only
        # reported once by finditer; recheck the shorter ones explicitly.
        for keyword in self._by_keyword:
            if keyword not in found and any(keyword in hit for hit in found) and contains_complete_phrase(haystack, keyword):
                found.add(keyword)
        return sorted((self._by_keyword[k] for k in found if k in self._by_keyword), key=lambda rule: (rule.priority, -len(rule.keyword)))

    def classify(self, text: str, *, is_order: bool, object_type: str = "") -> Match:
        return classify_text(text, self, is_order=is_order, object_type=object_type)


def classify_text(text: str, rules: "list[KeywordRule] | Classifier", *, is_order: bool, object_type: str = "") -> Match:
    """Decide whether a description belongs to the rubro and which category.

    Orders (<= 8 UIT) are either kept or dropped; awarded items (> 8 UIT)
    with only weak or contradictory evidence go to "revisar" instead.
    """
    haystack = normalize(text)
    if not haystack:
        return Match("drop", "")
    classifier = rules if isinstance(rules, Classifier) else Classifier(rules)
    hits = classifier.hits(haystack)
    included = [rule for rule in hits if rule.kind == "include"]
    excluded = any(rule.kind == "exclude" for rule in hits)
    reviewed = [rule for rule in hits if rule.kind == "review"]
    if included and not excluded:
        category = included[0].category
        if category == DEFAULT_CATEGORY and _is_goods(object_type) and any(term in haystack for term in EQUIPMENT_TERMS):
            category = EQUIPMENT_CATEGORY
        return Match("ok", category)
    if is_order:
        return Match("drop", "")
    if included or reviewed:
        return Match("revisar", (included or reviewed)[0].category)
    return Match("drop", "")


def _is_goods(object_type: str) -> bool:
    return normalize(object_type) in {"bien", "bienes"}


def process_group(procedure: str, *, is_order: bool = False) -> str:
    if is_order:
        return "Menores a 8 UIT"
    value = normalize(procedure)
    if value.startswith("adjudicacion simplificada"):
        return "Adjudicación Simplificada"
    if value.startswith("concurso publico abreviado"):
        return "Concurso Público Abreviado"
    if value.startswith("concurso publico"):
        return "Concurso Público"
    if value.startswith("licitacion publica abreviada"):
        return "Licitación Pública Abreviada"
    if value.startswith("licitacion publica"):
        return "Licitación Pública"
    if value.startswith("contratacion directa"):
        return "Contratación Directa"
    if value.startswith("comparacion de precios"):
        return "Comparación de Precios"
    if value.startswith("subasta inversa"):
        return "Subasta Inversa Electrónica"
    return "Otros procedimientos"


_REGIONAL_NAME = re.compile(r"\b(gobierno regional|ugel|diresa|direccion regional|red de salud|hospital regional|proyecto especial)\b")
_LOCAL_NAME = re.compile(r"\b(municipalidad|mancomunidad|instituto vial provincial)\b")
_COMPANY_NAME = re.compile(r"\b(fonafe|petroperu|sedapal|s\.?a\.?|electro|eps|empresa)\b")


def government_level(entity_type: str = "", entity_name: str = "") -> str:
    """SEACE's TIPOENTIDAD when available, else a name heuristic."""
    kind = normalize(entity_type)
    if "regional" in kind:
        return "Gobierno Regional"
    if "local" in kind:
        return "Gobierno Local"
    if "empresa" in kind or "fonafe" in kind:
        return "Empresas públicas"
    if "nacional" in kind:
        return "Gobierno Nacional"
    name = normalize(entity_name)
    if _REGIONAL_NAME.search(name):
        return "Gobierno Regional"
    if _LOCAL_NAME.search(name):
        return "Gobierno Local"
    if _COMPANY_NAME.search(name):
        return "Empresas públicas"
    return "Gobierno Nacional"
