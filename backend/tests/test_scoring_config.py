from __future__ import annotations

import unittest

import pandas as pd

from backend.app.services.scoring_config_service import CHILE_REGIONS, default_scoring_config
from src.scoring import calcular_score


class ScoringConfigTests(unittest.TestCase):
    def test_chile_uses_chilean_regions_and_reachable_priority_a(self):
        config = default_scoring_config("chile")
        self.assertEqual(config["priority_a_min"], 60)
        self.assertIn("metropolitana de santiago", config["factors"]["priority_region"]["value"])
        self.assertNotIn("loreto", config["factors"]["priority_region"]["value"])
        self.assertEqual(len(CHILE_REGIONS), 16)

    def test_chile_closed_factor_recognizes_culminated_processes(self):
        config = default_scoring_config("chile")
        row = pd.Series({"descripcion": "internet satelital", "objeto": "", "nomenclatura": "", "area_usuaria": "", "entidad": "", "region": "Chile", "monto": 0, "estado_comercial": "Proceso Culminado", "origen": ""})
        score, _, reasons = calcular_score(row, config)
        self.assertEqual(score, 0)
        self.assertIn("Proceso cerrado", reasons)

    def test_chile_does_not_score_peru_only_factors(self):
        row = pd.Series({
            "descripcion": "servicio sin keywords", "objeto": "", "nomenclatura": "", "area_usuaria": "",
            "entidad": "MTC PROVIAS", "region": "", "monto": 0, "estado_comercial": "",
            "origen": "menor_8_browser",
        })
        peru_score, _, peru_reasons = calcular_score(row, default_scoring_config("peru"))
        chile_score, _, chile_reasons = calcular_score(row, default_scoring_config("chile"))
        self.assertEqual(peru_score, 20)
        self.assertEqual(chile_score, 0)
        self.assertIn("Entidad objetivo", peru_reasons)
        self.assertNotIn("Entidad objetivo", chile_reasons)

    def test_custom_considered_value_changes_the_score(self):
        config = default_scoring_config("chile")
        config["factors"]["keyword"]["value"] = "fibra submarina"
        row = pd.Series({
            "descripcion": "servicio de fibra submarina", "objeto": "", "nomenclatura": "", "area_usuaria": "",
            "entidad": "", "region": "", "monto": 0, "estado_comercial": "", "origen": "",
        })
        score, _, reasons = calcular_score(row, config)
        self.assertEqual(score, 25)
        self.assertIn("Keyword conectividad/satelital", reasons)

    def test_custom_factor_participates_in_score(self):
        config = default_scoring_config("chile")
        config["factors"]["custom_cloud"] = {
            "label": "Cloud", "points": 8, "enabled": True, "value": "nube privada", "field": "description", "value_type": "list",
        }
        row = pd.Series({"descripcion": "servicio de nube privada", "objeto": "", "nomenclatura": "", "area_usuaria": "", "entidad": "", "region": "", "monto": 0, "estado_comercial": "", "origen": ""})
        score, _, reasons = calcular_score(row, config)
        self.assertEqual(score, 8)
        self.assertIn("Cloud", reasons)


if __name__ == "__main__":
    unittest.main()
