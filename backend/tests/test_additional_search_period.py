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

    def test_argentina_opening_window_keeps_tenders_published_earlier(self) -> None:
        # COMPR.AR announces a tender (fecha_publicacion) well before it opens
        # (fecha_apertura). The automatic incremental window targets the
        # opening date, so a process published outside the window must still
        # be kept when its opening date falls inside it.
        rows = pd.DataFrame(
            {
                "nomenclatura": ["PUBLISHED-EARLY", "PUBLISHED-IN-WINDOW", "OPENS-LATE"],
                "fecha_publicacion": pd.to_datetime(["2026-06-10", "2026-08-30", "2026-05-01"]),
                "fecha_apertura": pd.to_datetime(["2026-09-05", "2026-09-10", "2026-11-01"]),
            }
        )

        filtered = _filter_dataframe_period(
            rows,
            {
                "years": ["2026"],
                "months": ["8", "9", "10"],
                "publication_date_from": "2026-08-28",
                "publication_date_to": "2026-10-07",
                "date_filter_type": "opening",
                "source": "comprar_argentina_procesos",
            },
        )

        self.assertEqual(filtered["nomenclatura"].tolist(), ["PUBLISHED-EARLY", "PUBLISHED-IN-WINDOW"])

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
