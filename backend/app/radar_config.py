from __future__ import annotations

DEFAULT_RADAR_KEYWORDS = ("satelital", "internet", "conectividad", "LEO", "GEO", "órbita")
AUTO_PROFILE_PREFIX = "Radar automático"

RADAR_COUNTRY_CONFIG = {
    "peru": {"label": "Perú", "source": "oece_ocds_api", "version": "OCDS", "max_results": 100},
    "chile": {"label": "Chile", "source": "mercado_publico_lmp_gc", "version": "Mercado Público", "max_results": 50},
    "argentina": {
        "label": "Argentina",
        "source": "comprar_argentina_procesos",
        "sources": (
            {"source": "comprar_argentina_procesos", "label": "Procesos"},
            {"source": "comprar_argentina_publicaciones", "label": "Publicaciones"},
        ),
        "version": "COMPR.AR",
        "max_results": 250,
    },
}


SUPPORTED_COUNTRIES = tuple(RADAR_COUNTRY_CONFIG)


def country_for_source(source: str) -> str:
    normalized = str(source or "").strip().lower()
    if normalized.startswith("mercado_publico"):
        return "chile"
    if normalized.startswith("comprar_argentina"):
        return "argentina"
    return "peru"


def source_for_country(country: str) -> str:
    normalized = str(country or "").strip().lower()
    config = RADAR_COUNTRY_CONFIG.get(normalized)
    if config is None:
        raise ValueError(f"País no soportado: {country}")
    return str(config["source"])
