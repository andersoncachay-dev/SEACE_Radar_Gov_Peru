from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from backend.app.services.document_service import _probe_document_extension


class DocumentTypeProbeTests(unittest.TestCase):
    def test_reads_extension_from_content_disposition(self) -> None:
        response = Mock(status_code=200, headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="Bases Administrativas.docx"',
        })
        with patch("backend.app.services.document_service.requests.head", return_value=response):
            extension = _probe_document_extension("https://prod1.seace.gob.pe/SdescargarArchivoAlfresco?fileCode=abc")

        self.assertEqual(extension, "docx")

    def test_falls_back_to_content_type_when_no_disposition(self) -> None:
        response = Mock(status_code=200, headers={"Content-Type": "application/pdf"})
        with patch("backend.app.services.document_service.requests.head", return_value=response):
            extension = _probe_document_extension("https://prod1.seace.gob.pe/SdescargarArchivoAlfresco?fileCode=abc")

        self.assertEqual(extension, "pdf")

    def test_falls_back_to_get_when_head_has_no_content_type(self) -> None:
        head_response = Mock(status_code=200, headers={})
        get_response = Mock(status_code=200, headers={"Content-Type": "application/vnd.ms-excel"})
        with patch("backend.app.services.document_service.requests.head", return_value=head_response), \
                patch("backend.app.services.document_service.requests.get", return_value=get_response):
            extension = _probe_document_extension("https://prod1.seace.gob.pe/SdescargarArchivoAlfresco?fileCode=abc")

        self.assertEqual(extension, "xls")

    def test_returns_empty_string_when_request_fails(self) -> None:
        with patch("backend.app.services.document_service.requests.head", side_effect=Exception("timeout")):
            extension = _probe_document_extension("https://prod1.seace.gob.pe/SdescargarArchivoAlfresco?fileCode=abc")

        self.assertEqual(extension, "")


if __name__ == "__main__":
    unittest.main()
