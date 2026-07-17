from __future__ import annotations

import argparse
import json
from datetime import datetime

from backend.app.radar_config import DEFAULT_RADAR_KEYWORDS
from src.keyword_matching import contains_any_complete_phrase
from src.oece_ocds_connector import _csv_col, _csv_date, _read_monthly_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    current = datetime.utcnow()
    mapping: dict[str, dict[str, str | None]] = {}
    downloaded: list[int] = []
    skipped: list[int] = []
    for month in range(1, current.month + 1):
        try:
            frame, _ = _read_monthly_csv("seace_v3", current.year, month)
        except Exception:
            skipped.append(month)
            continue
        downloaded.append(month)
        nomenclature_column = next(
            (
                column
                for column in frame.columns
                if "título de la licitación" in str(column).casefold()
            ),
            "",
        )
        for _, row in frame.iterrows():
            searchable = " ".join(str(value or "") for value in row.values)
            if not contains_any_complete_phrase(searchable, DEFAULT_RADAR_KEYWORDS):
                continue
            nomenclature = str(row.get(nomenclature_column) or "").strip() if nomenclature_column else ""
            publication = _csv_date(
                row,
                "compiledRelease/tender/datePublished",
                "Entrega compilada:Fecha de entrega",
            )
            consultation = _csv_date(
                row,
                "Entrega compilada:Licitación:Periodo de consulta:Fecha de fin",
            )
            if nomenclature and publication is not None:
                mapping[nomenclature] = {
                    "publication_date": publication.isoformat(),
                    "consultation_deadline": consultation.isoformat() if consultation is not None else None,
                }
    with open(args.output, "w", encoding="utf-8") as file:
        json.dump(mapping, file, ensure_ascii=False, sort_keys=True)
    print(json.dumps({"records": len(mapping), "downloaded_months": downloaded, "skipped_months": skipped}))


if __name__ == "__main__":
    main()
