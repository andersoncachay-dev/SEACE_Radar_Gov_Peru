from __future__ import annotations

import unittest

from backend.app.services.run_service import _merge_mercado_publico_chile_details


class ChileDetailUrlMergeTests(unittest.TestCase):
    def test_ficha_url_is_merged_into_bulk_row(self) -> None:
        bulk_rows = [
            {"Nomenclatura": "3621-46-LE26", "url_detalle": "", "Vigencia": "Publicada"},
        ]
        detail_rows = [
            {
                "Nomenclatura": "3621-46-LE26",
                "url_detalle": "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?qs=abc123",
                "contract_duration": "12 Meses",
            },
        ]

        merged = _merge_mercado_publico_chile_details(bulk_rows, detail_rows, [])

        self.assertEqual(
            merged[0]["url_detalle"],
            "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?qs=abc123",
        )

    def test_bulk_row_without_matching_detail_keeps_empty_url(self) -> None:
        bulk_rows = [{"Nomenclatura": "NOT-ENRICHED", "url_detalle": "", "Vigencia": "Cerrada"}]

        merged = _merge_mercado_publico_chile_details(bulk_rows, [], [])

        self.assertEqual(merged[0]["url_detalle"], "")


if __name__ == "__main__":
    unittest.main()
