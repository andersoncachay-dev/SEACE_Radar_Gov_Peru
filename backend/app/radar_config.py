from __future__ import annotations

DEFAULT_RADAR_KEYWORDS = ("satelital", "internet", "conectividad", "radio enlace", "LEO", "GEO", "órbita")
AUTO_PROFILE_PREFIX = "Radar automático"

RADAR_COUNTRY_CONFIG = {
    "peru": {"label": "Perú", "source": "oece_ocds_api", "version": "OCDS", "max_results": 100},
    "chile": {"label": "Chile", "source": "mercado_publico_lmp_gc", "version": "Mercado Público", "max_results": 50},
}
