from __future__ import annotations

import unittest

import pandas as pd

from backend.app.services.run_service import _filter_dataframe_entity, _filter_dataframe_nomenclature, _filter_dataframe_period


class AdditionalSearchPeriodTests(unittest.TestCase):
    def test_filters_exact_publication_date_range(self) -> None:
        rows = pd.DataFrame(
            {
                "fecha_publicacion": pd.to_datetime(["2026-06-10", "2026-06-20", "2026-07-05", "2026-07-12"]),
                "nomenclatura": ["BEFORE", "IN-JUNE", "IN-JULY", "AFTER"],
            }
        )

        filtered = _filter_dataframe_period(
            rows,
            {
                "years": ["2026"],
                "months": ["6", "7"],
                "publication_date_from": "2026-06-15",
                "publication_date_to": "2026-07-10",
            },
        )

        self.assertEqual(filtered["nomenclatura"].tolist(), ["IN-JUNE", "IN-JULY"])

    def test_restricts_keyword_results_to_selected_entity(self) -> None:
        rows = pd.DataFrame(
            {
                "entidad": ["Gobierno Regional de Lima", "Gobierno Regional de Lima Metropolitana", "Municipalidad de Lima"],
                "nomenclatura": ["TARGET", "PARTIAL", "OTHER"],
            }
        )

        filtered = _filter_dataframe_entity(rows, "Gobierno Regional de Lima")

        self.assertEqual(filtered["nomenclatura"].tolist(), ["TARGET"])

    def test_requires_exact_nomenclature(self) -> None:
        rows = pd.DataFrame(
            {
                "nomenclatura": ["CP-ABR-5-2026-MDL/DEC-1", "CP-ABR-5-2026-MDL/DEC-10"],
            }
        )

        filtered = _filter_dataframe_nomenclature(rows, " cp-abr-5-2026-mdl/dec-1 ")

        self.assertEqual(filtered["nomenclatura"].tolist(), ["CP-ABR-5-2026-MDL/DEC-1"])


if __name__ == "__main__":
    unittest.main()
