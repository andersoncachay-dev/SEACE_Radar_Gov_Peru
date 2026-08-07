from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from src.comprar_argentina_scraper import (
    _commercial_status,
    _next_publication_page,
    _process_schedule_from_detail,
    _province,
    _publication_row,
    _publication_schedule_from_detail,
)


class _DetailSession:
    def get(self, *_args, **_kwargs):
        class Response:
            content = b"""
                <span id='x_Cronograma_lblFechaPublicacion'>03/07/2026 12:00 Hrs.</span>
                <span id='x_Cronograma_lblFechaInicioConsultas'>06/07/2026 08:00 Hrs.</span>
                <span id='x_Cronograma_lblFechaFinalConsultas'>16/07/2026 08:00 Hrs.</span>
                <span id='x_Cronograma_lblFechaActoApertura'>21/07/2026 09:00 Hrs.</span>
            """

            @staticmethod
            def raise_for_status() -> None:
                return None

        return Response()


class _PublicationDetailSession:
    def get(self, *_args, **_kwargs):
        class Response:
            content = b"""
                <section class='panel'>
                  <div class='panel-heading'><h3 class='panel-title'>Cronograma</h3></div>
                  <label for='FechaPublicacion'>Fecha de publicacion:</label>
                  <div class='form-control'>22/07/2026</div>
                  <label for='FechaInicioConsultas'>Inicio de consultas:</label>
                  <div class='form-control'>22/07/2026</div>
                  <label for='FechaFinConsultas'>Fin de consultas:</label>
                  <div class='form-control'>31/07/2026</div>
                  <label for='FechaApertura'>Fecha de apertura:</label>
                  <div class='form-control'>06/8/2026 11:00</div>
                  <label for='FechaFinRecepcionDocumentacion'>Fin de recepcion de documentacion:</label>
                  <div class='form-control'>05/8/2026 18:30</div>
                </section>
            """

            @staticmethod
            def raise_for_status() -> None:
                return None

        return Response()


class ComprarArgentinaScraperTests(unittest.TestCase):
    def test_comprar_terminal_states_are_commercially_closed(self) -> None:
        for status in ("Adjudicado", "Dejado Sin Efecto", "Fracasado", "Desierto"):
            self.assertEqual(_commercial_status(status), "Proceso Culminado")

    def test_comprar_active_states_remain_in_evaluation(self) -> None:
        for status in ("En Apertura", "En Evaluación", "Pendiente Adjudicación", "Pendiente Análisis"):
            self.assertEqual(_commercial_status(status), "En Evaluación")

    def test_published_process_uses_opening_date(self) -> None:
        future = datetime.now() + timedelta(days=2)
        past = datetime.now() - timedelta(days=2)
        self.assertEqual(_commercial_status("Publicado", future), "Vigente para Propuesta")
        self.assertEqual(_commercial_status("Publicado", past), "En Evaluación")

    def test_argentina_province_aliases_and_long_names(self) -> None:
        self.assertEqual(_province("Organismo de Capital Federal"), "Ciudad de Buenos Aires")
        self.assertEqual(_province("Delegación Río Negro"), "Río Negro")
        self.assertEqual(_province("Servicio nacional"), "Argentina")

    def test_publication_grid_row_is_normalized(self) -> None:
        normalized = _publication_row(
            {
                "Número publicación": "128-0016-CDI23",
                "Tipo": "Convocatoria",
                "Fecha de apertura": "10/02/2023",
                "Objeto": "Equipamiento satelital",
                "Estado": "Publicado",
                "Servicio Administrativo Financiero": "814-UNSAM",
                "Unidad Operativa de Contrataciones": "128/0 - UNSAM",
            }
        )
        self.assertEqual(normalized["nomenclatura"], "128-0016-CDI23")
        self.assertEqual(normalized["record_type"], "publicacion")
        self.assertEqual(normalized["objeto"], "Convocatoria")
        self.assertEqual(normalized["source_status"], "Publicado")

    def test_process_detail_schedule_is_normalized(self) -> None:
        schedule = _process_schedule_from_detail(_DetailSession(), "https://comprar.gob.ar/ficha")
        self.assertEqual(schedule["fecha_publicacion"], datetime(2026, 7, 3, 12, 0))
        self.assertEqual(schedule["consulta_fin"], datetime(2026, 7, 16, 8, 0))
        self.assertEqual(schedule["propuesta_fin"], datetime(2026, 7, 21, 9, 0))
        self.assertEqual(schedule["schedule_source"], "comprar")
        self.assertTrue(schedule["replace_schedule"])

    def test_publication_detail_schedule_is_normalized(self) -> None:
        schedule = _publication_schedule_from_detail(_PublicationDetailSession(), "https://comprar.gob.ar/ficha")
        self.assertEqual(schedule["fecha_publicacion"], datetime(2026, 7, 22))
        self.assertEqual(schedule["consulta_fin"], datetime(2026, 7, 31))
        self.assertEqual(schedule["fecha_apertura"], datetime(2026, 8, 6, 11, 0))
        self.assertEqual(schedule["propuesta_fin"], datetime(2026, 8, 5, 18, 30))
        self.assertEqual(schedule["schedule_source"], "comprar")
        self.assertTrue(schedule["replace_schedule"])

    def test_publication_pager_discovers_pages_exposed_later(self) -> None:
        class Response:
            text = "javascript:__doPostBack('grid','Page$11') javascript:__doPostBack('grid','Page$12')"

        self.assertEqual(_next_publication_page(Response(), 11), 12)
        self.assertIsNone(_next_publication_page(Response(), 12))


if __name__ == "__main__":
    unittest.main()
