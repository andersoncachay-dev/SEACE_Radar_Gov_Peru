from datetime import datetime, timedelta
import unittest

from src.mercado_publico_scraper import (
    _estado_comercial,
    _filter_rows_for_period,
    _is_closed_process,
    _parse_detail,
    _to_float,
)


class MercadoPublicoScraperTests(unittest.TestCase):
    def test_parses_regular_tender_estimated_amount(self):
        html = "<html><body>7. Montos y duración del contrato Monto Total Estimado: 184120000</body></html>"

        fields = _parse_detail(html)

        self.assertEqual(fields["VR / VE / Cuantia de la contratacion"], 184120000.0)

    def test_parses_chilean_thousands_separators(self):
        self.assertEqual(_to_float("$ 184.120.000"), 184120000.0)
        self.assertEqual(_to_float("CLP 1.234,56"), 1234.56)

    def test_adjudicated_process_is_closed(self):
        self.assertEqual(_estado_comercial("Adjudicada", "", ""), "Proceso Culminado")
        self.assertTrue(_is_closed_process({"Vigencia": "Adjudicada", "propuesta_fin": ""}))

    def test_past_proposal_deadline_is_closed(self):
        closing = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y %H:%M:%S")

        self.assertTrue(_is_closed_process({"Vigencia": "Publicada", "propuesta_fin": closing}))

    def test_filters_period_before_opening_details(self):
        rows = [
            {"Nomenclatura": "JUN", "propuesta_fin": "30/06/2026 15:00:00"},
            {"Nomenclatura": "JUL", "propuesta_fin": "15/07/2026 15:00:00"},
            {"Nomenclatura": "OLD", "propuesta_fin": "15/07/2025 15:00:00"},
        ]

        filtered = _filter_rows_for_period(rows, years=[2026], months=[6, 7])

        self.assertEqual([row["Nomenclatura"] for row in filtered], ["JUN", "JUL"])


if __name__ == "__main__":
    unittest.main()
