from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


SOURCES = (
    "mercado_publico_browser",
    "mercado_publico_lmp_gc",
    "oece_ocds_api",
    "seace_public_browser",
    "seace_public_excel",
)


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _local_rows(container: str, database: str, user: str) -> list[dict[str, Any]]:
    source_list = ",".join(f"'{source}'" for source in SOURCES)
    query = f"""
    SELECT json_build_object(
        'source', source,
        'nomenclatura', external_id,
        'entidad', entity,
        'objeto', object_type,
        'descripcion', description,
        'region', region,
        'ruc', buyer_ruc,
        'ocid', ocid,
        'tender_id', tender_id,
        'source_id', ocds_source_id,
        'release_id', release_id,
        'monto', amount,
        'moneda', currency,
        'estado_operativo', status,
        'prioridad', priority,
        'score', score,
        'motivos_score', reasons,
        'url_detalle', detail_url,
        'requerimiento_pdf', requirement_pdf_url,
        'requerimiento_pdf_local', requirement_pdf_local,
        'fecha_publicacion', publication_date,
        'consulta_fin', consultation_deadline,
        'cotizacion_fin', quote_deadline,
        'propuesta_fin', proposal_deadline
    )::text
    FROM opportunities
    WHERE source IN ({source_list}) AND is_archived IS FALSE
    ORDER BY source, external_id
    """
    result = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "psql",
            "-U",
            user,
            "-d",
            database,
            "-At",
            "-c",
            query,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _login(session: requests.Session, api_url: str, email: str, password: str) -> None:
    response = session.post(
        f"{api_url}/auth/login",
        data={"username": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    session.headers["Authorization"] = f"Bearer {response.json()['access_token']}"


def _get_json(session: requests.Session, url: str) -> Any:
    response = session.get(url, timeout=120)
    response.raise_for_status()
    return response.json()


def _backup(session: requests.Session, api_url: str, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"opportunities-production-before-{stamp}.json"
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "active": _get_json(session, f"{api_url}/opportunities"),
        "archived_peru": _get_json(session, f"{api_url}/opportunities/archived?country=peru"),
        "archived_chile": _get_json(session, f"{api_url}/opportunities/archived?country=chile"),
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def _duplicate_summary(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    exact = Counter((row.get("source"), row.get("external_id")) for row in rows)
    nomenclature = Counter(
        (row.get("source"), _normalized(row.get("nomenclature")))
        for row in rows
        if _normalized(row.get("nomenclature"))
    )
    return {
        "source_external_id": [
            {"source": key[0], "external_id": key[1], "count": count}
            for key, count in exact.items()
            if count > 1
        ],
        "source_nomenclature": [
            {"source": key[0], "nomenclature": key[1], "count": count}
            for key, count in nomenclature.items()
            if count > 1
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate active opportunity rows through the protected GovRadar API.")
    parser.add_argument("--api-url", default="https://api.crmprocesosgobierno.rodarlab.com")
    parser.add_argument("--email", default=os.getenv("GOVRADAR_ADMIN_EMAIL", "admin@rodarlab.com"))
    parser.add_argument("--container", default="seace_radar_db")
    parser.add_argument("--database", default="seace_radar")
    parser.add_argument("--db-user", default="seace")
    parser.add_argument("--batch-size", type=int, default=75)
    parser.add_argument("--backup-dir", type=Path, default=Path("exports/migrations"))
    args = parser.parse_args()

    password = os.getenv("GOVRADAR_ADMIN_PASSWORD", "")
    if not password:
        print("GOVRADAR_ADMIN_PASSWORD is required", file=sys.stderr)
        return 2

    api_url = args.api_url.rstrip("/")
    session = requests.Session()
    _login(session, api_url, args.email, password)
    backup_path = _backup(session, api_url, args.backup_dir)
    rows = _local_rows(args.container, args.database, args.db_user)
    # OCDS is the canonical Peru feed. Keep legacy SEACE rows only when their
    # nomenclature does not exist in OCDS, otherwise a maintenance rerun would
    # recreate cross-source duplicates already consolidated in production.
    ocds_keys = {
        _normalized(row.get("nomenclatura"))
        for row in rows
        if row["source"] == "oece_ocds_api" and _normalized(row.get("nomenclatura"))
    }
    rows = [
        row
        for row in rows
        if row["source"] not in {"seace_public_browser", "seace_public_excel"}
        or _normalized(row.get("nomenclatura")) not in ocds_keys
    ]
    by_source = Counter(row["source"] for row in rows)

    migrated: Counter[str] = Counter()
    for source in SOURCES:
        source_rows = [
            {key: value for key, value in row.items() if key != "source"}
            for row in rows
            if row["source"] == source and row.get("nomenclatura")
        ]
        for offset in range(0, len(source_rows), args.batch_size):
            batch = source_rows[offset : offset + args.batch_size]
            response = session.post(
                f"{api_url}/opportunities/import",
                json={"source": source, "rows": batch},
                timeout=180,
            )
            response.raise_for_status()
            migrated[source] += int(response.json().get("imported", 0))

    active = _get_json(session, f"{api_url}/opportunities")
    stats = _get_json(session, f"{api_url}/opportunities/stats")
    report = {
        "backup": str(backup_path),
        "local_active_by_source": dict(by_source),
        "processed_by_source": dict(migrated),
        "production_active_by_source": stats.get("by_source", {}),
        "production_active_total": stats.get("total", 0),
        "duplicates": _duplicate_summary(active),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
