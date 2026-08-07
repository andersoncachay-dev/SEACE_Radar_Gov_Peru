from __future__ import annotations

import unittest

from backend.app.services.document_service import _argentina_document_candidates


class ArgentinaDocumentDiscoveryTests(unittest.TestCase):
    def test_extracts_general_conditions_and_technical_annex_postbacks(self) -> None:
        html = b"""
        <table>
          <tr><td>DI-2024-79130471-APN-ONC#JGM</td><td>
            <a href="javascript:__doPostBack('ctl00$CPH1$UCVistaPreviaPliego$UCCondicionesGenerales$gv$ctl02$lnkGEDOByC','')">Descargar</a>
          </td></tr>
          <tr><td>Anexo II - Especificaciones Tecnicas.pdf</td><td>Especificaciones_Tecnicas</td><td>
            <a href="javascript:__doPostBack('ctl00$CPH1$UCVistaPreviaPliego$UCAnexos$gv$ctl02$btnVerAnexo','')">Descargar</a>
          </td></tr>
          <tr><td>Autorizacion llamado</td><td>
            <a href="javascript:__doPostBack('ctl00$CPH1$UCVistaPreviaPliego$UC_ActosAdministrativos$gv$ctl02$btnVer','')">Descargar</a>
          </td></tr>
        </table>
        """

        candidates = _argentina_document_candidates(html)

        self.assertEqual(len(candidates), 2)
        self.assertIn("Pliego de Bases", candidates[0]["title"])
        self.assertEqual(candidates[1]["title"], "Anexo II - Especificaciones Tecnicas.pdf")

    def test_extracts_publication_annex_download_routes(self) -> None:
        html = b"""
        <table>
          <tr><td>4. CONV- Pliego de especificaciones tecnicas definitivo.pdf</td><td>Especificaciones_Tecnicas</td><td>
            <a href="/Publicacion/Convocatoria/DescargarArchivo?idAnexo=9299524"><span>Descargar</span></a>
          </td></tr>
          <tr><td>9. CONV-PCP LIC PRIV 6 2026.pdf</td><td>Proyecto_De_Pliego</td><td>
            <a href="/Publicacion/Convocatoria/DescargarArchivo?idAnexo=9299525"><span>Descargar</span></a>
          </td></tr>
        </table>
        """

        candidates = _argentina_document_candidates(html)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0]["title"], "4. CONV- Pliego de especificaciones tecnicas definitivo.pdf")
        self.assertEqual(candidates[0]["href"], "/Publicacion/Convocatoria/DescargarArchivo?idAnexo=9299524")


if __name__ == "__main__":
    unittest.main()
