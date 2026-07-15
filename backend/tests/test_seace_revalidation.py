from datetime import datetime, timedelta

import pandas as pd

from backend.app.services.run_service import _recent_consultation_mask
from src.seace_browser_scraper import _looks_like_data_row, _selection_parts


def test_result_row_does_not_require_customer_specific_keywords():
    cells = [
        "1",
        "MUNICIPALIDAD DISTRITAL DE LURIGANCHO",
        "13/07/2026",
        "CP-ABR-5-2026-MDL/DEC-1",
        "Servicio",
        "SERVICIO DE CONECTIVIDAD DE DATOS",
        "0",
        "PEN",
        "3",
    ]

    assert _looks_like_data_row(cells)


def test_recent_consultation_window_excludes_distant_future_rows():
    now = datetime.utcnow()
    rows = pd.DataFrame(
        {"consulta_fin": [now - timedelta(days=29), now + timedelta(days=2), now + timedelta(days=31)]}
    )

    assert _recent_consultation_mask(rows, days=30) == [True, True, False]


def test_nomenclature_is_split_for_seace_fields():
    assert _selection_parts("CP-ABR-5-2026-MDL/DEC-1") == ("5", "1")
