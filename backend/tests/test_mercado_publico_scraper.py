from datetime import datetime, timedelta
import unittest

from src.mercado_publico_scraper import (
    _estado_comercial,
    _detail_row_indexes,
    _filter_rows_for_period,
    _is_closed_process,
    _parse_detail,
    _parse_large_purchase_results,
    _to_float,
)


class MercadoPublicoScraperTests(unittest.TestCase):
    def test_parses_large_purchase_with_empty_supplier_without_shifting_columns(self):
        html = """
        <table><tr>
          <td><a href="/gran-compra/54988">54988</a></td>
          <td>PRODUCCION Y TRANSMISION SATELITAL DE HDTV</td>
          <td>SERVICIO NACIONAL DE TURISMO</td>
          <td></td>
          <td>22-09-2020 17:17:00</td>
          <td>08-10-2020 23:59:00</td>
          <td>Cerrada</td>
        </tr></table>
        """

        rows = _parse_large_purchase_results(html, "https://www.mercadopublico.cl/resultados")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Nomenclatura"], "54988")
        self.assertEqual(rows[0]["convocatoria_inicio"], "22/09/2020 17:17:00")
        self.assertEqual(rows[0]["propuesta_fin"], "08/10/2020 23:59:00")
        self.assertEqual(rows[0]["Vigencia"], "Cerrada")

    def test_parses_regular_tender_estimated_amount(self):
        html = "<html><body>7. Montos y duración del contrato Monto Total Estimado: 184120000</body></html>"

        fields = _parse_detail(html)

        self.assertEqual(fields["VR / VE / Cuantia de la contratacion"], 184120000.0)

    def test_parses_official_tender_region(self):
        html = """
        <body>
          Región en que se genera la licitación: Región Metropolitana de Santiago
          <div>Subir</div><h2>3. Etapas y plazos</h2>
        </body>
        """

        self.assertEqual(_parse_detail(html)["region"], "Región Metropolitana de Santiago")

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

    def test_normal_detail_enrichment_visits_only_active_processes(self):
        future = (datetime.now() + timedelta(days=5)).strftime("%d/%m/%Y %H:%M:%S")
        past = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y %H:%M:%S")
        rows = [
            {"Nomenclatura": "ACTIVE-1", "Vigencia": "Publicada", "propuesta_fin": future},
            {"Nomenclatura": "CLOSED", "Vigencia": "Publicada", "propuesta_fin": past},
            {"Nomenclatura": "ACTIVE-2", "Vigencia": "Publicada", "propuesta_fin": future},
        ]

        active, closed = _detail_row_indexes(rows, enrich_details=True, enrich_closed_details=False, max_details=0)

        self.assertEqual(active, {0, 2})
        self.assertEqual(closed, set())

    def test_closed_detail_is_visited_only_for_explicit_revalidation(self):
        past = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y %H:%M:%S")
        rows = [{"Nomenclatura": "CLOSED", "Vigencia": "Publicada", "propuesta_fin": past}]

        active, closed = _detail_row_indexes(rows, enrich_details=True, enrich_closed_details=True, max_details=1)

        self.assertEqual(active, set())
        self.assertEqual(closed, {0})


if __name__ == "__main__":
    unittest.main()
