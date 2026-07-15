from datetime import datetime, timedelta
import unittest

import pandas as pd

from backend.app.services.run_service import _filter_incremental_rows


class IncrementalIngestionTests(unittest.TestCase):
    def test_keeps_recent_active_and_revalidates_existing_active_only(self) -> None:
        now = datetime.now()
        rows = pd.DataFrame(
            [
                {
                    "nomenclatura": "NEW",
                    "fecha_publicacion": now,
                    "propuesta_fin": now + timedelta(days=2),
                    "estado_comercial": "Vigente",
                },
                {
                    "nomenclatura": "OLD-ACTIVE",
                    "fecha_publicacion": now - timedelta(days=30),
                    "propuesta_fin": now + timedelta(days=2),
                    "estado_comercial": "Vigente",
                },
                {
                    "nomenclatura": "EXPIRED",
                    "fecha_publicacion": now,
                    "propuesta_fin": now - timedelta(seconds=1),
                    "estado_comercial": "Vigente",
                },
                {
                    "nomenclatura": "CLOSED",
                    "fecha_publicacion": now,
                    "propuesta_fin": now + timedelta(days=2),
                    "estado_comercial": "Proceso Culminado",
                },
            ]
        )
        diagnostics: list[str] = []
        filtered = _filter_incremental_rows(
            rows,
            {
                "automatic_incremental": True,
                "publication_date_from": now.strftime("%Y-%m-%d"),
                "publication_date_to": now.strftime("%Y-%m-%d"),
            },
            {"old-active"},
            diagnostics,
        )

        self.assertEqual(set(filtered["nomenclatura"]), {"NEW", "OLD-ACTIVE"})
        self.assertIn("1 nuevos/vigentes", diagnostics[0])
        self.assertIn("1 vigentes existentes", diagnostics[0])

    def test_chile_discovery_tag_uses_server_publication_filter(self) -> None:
        now = datetime.now()
        rows = pd.DataFrame(
            [
                {
                    "nomenclatura": "DISCOVERED-TODAY",
                    "fecha_publicacion": pd.NaT,
                    "propuesta_fin": now + timedelta(days=20),
                    "estado_comercial": "Vigente",
                    "automatic_discovery": True,
                },
                {
                    "nomenclatura": "REVALIDATED",
                    "fecha_publicacion": pd.NaT,
                    "propuesta_fin": now + timedelta(days=20),
                    "estado_comercial": "Vigente",
                    "automatic_discovery": False,
                },
            ]
        )

        filtered = _filter_incremental_rows(
            rows,
            {"automatic_incremental": True},
            {"revalidated"},
            [],
        )

        self.assertEqual(set(filtered["nomenclatura"]), {"DISCOVERED-TODAY", "REVALIDATED"})


if __name__ == "__main__":
    unittest.main()
