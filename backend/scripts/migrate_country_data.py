from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


COUNTRY_SOURCES = {
    "chile": ("mercado_publico_browser", "mercado_publico_lmp_gc"),
    "peru": ("oece_ocds_api", "seace_public_browser", "seace_public_excel"),
}


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def rows(connection: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def one(connection: psycopg.Connection, query: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    result = rows(connection, query, params)
    return result[0] if result else None


def insert_row(
    connection: psycopg.Connection,
    table: str,
    record: dict[str, Any],
    *,
    returning: str = "id",
) -> int:
    columns = list(record)
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING {}").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        sql.Identifier(returning),
    )
    with connection.cursor() as cursor:
        cursor.execute(statement, [record[column] for column in columns])
        return int(cursor.fetchone()[0])


def insert_rows(connection: psycopg.Connection, table: str, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    columns = list(records[0])
    statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() for _ in columns),
    )
    with connection.cursor() as cursor:
        cursor.executemany(statement, [[record[column] for column in columns] for record in records])


def update_row(connection: psycopg.Connection, table: str, row_id: int, record: dict[str, Any]) -> None:
    columns = list(record)
    statement = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
        sql.Identifier(table),
        sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder()) for column in columns
        ),
    )
    with connection.cursor() as cursor:
        cursor.execute(statement, [record[column] for column in columns] + [row_id])


def without_id(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "id"}


def backup_target(connection: psycopg.Connection, country: str, source_names: tuple[str, ...], backup_dir: Path) -> Path:
    opportunity_ids = rows(
        connection,
        "SELECT id FROM opportunities WHERE source = ANY(%s) ORDER BY id",
        (list(source_names),),
    )
    ids = [item["id"] for item in opportunity_ids]
    backup = {
        "country": country,
        "created_at": datetime.now(UTC).isoformat(),
        "radar_keywords": rows(connection, "SELECT * FROM radar_keywords WHERE country = %s ORDER BY id", (country,)),
        "search_profiles": rows(
            connection, "SELECT * FROM search_profiles WHERE source = ANY(%s) ORDER BY id", (list(source_names),)
        ),
        "scrape_runs": rows(connection, "SELECT * FROM scrape_runs WHERE source = ANY(%s) ORDER BY id", (list(source_names),)),
        "opportunities": rows(connection, "SELECT * FROM opportunities WHERE source = ANY(%s) ORDER BY id", (list(source_names),)),
        "opportunity_snapshots": rows(
            connection,
            "SELECT * FROM opportunity_snapshots WHERE opportunity_id = ANY(%s) ORDER BY id",
            (ids,),
        ) if ids else [],
        "documents": rows(
            connection,
            "SELECT * FROM documents WHERE opportunity_id = ANY(%s) ORDER BY id",
            (ids,),
        ) if ids else [],
        "alerts": rows(
            connection,
            "SELECT * FROM alerts WHERE opportunity_id = ANY(%s) ORDER BY id",
            (ids,),
        ) if ids else [],
        "app_settings": rows(
            connection, "SELECT * FROM app_settings WHERE key LIKE %s ORDER BY id", (f"scheduler.{country}.%",)
        ),
    }
    rule_ids = sorted({item["rule_id"] for item in backup["alerts"]})
    backup["alert_rules"] = rows(
        connection, "SELECT * FROM alert_rules WHERE id = ANY(%s) ORDER BY id", (rule_ids,)
    ) if rule_ids else []
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"{country}-production-before-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    path.write_text(json.dumps(backup, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    return path


def migrate(source: psycopg.Connection, target: psycopg.Connection, country: str) -> dict[str, int]:
    source_names = COUNTRY_SOURCES[country]
    summary = {
        "keywords_inserted": 0,
        "keywords_updated": 0,
        "profiles_inserted": 0,
        "profiles_updated": 0,
        "runs_inserted": 0,
        "runs_existing": 0,
        "opportunities_inserted": 0,
        "opportunities_updated": 0,
        "opportunities_preserved_newer": 0,
        "snapshots_inserted": 0,
        "snapshots_existing": 0,
        "documents_inserted": 0,
        "documents_updated": 0,
        "alert_rules_inserted": 0,
        "alert_rules_updated": 0,
        "alerts_inserted": 0,
        "alerts_updated": 0,
        "settings_inserted": 0,
        "settings_updated": 0,
    }
    admin = one(target, "SELECT id FROM users WHERE role = 'admin' ORDER BY id LIMIT 1")
    admin_id = int(admin["id"]) if admin else None

    for item in rows(source, "SELECT * FROM radar_keywords WHERE country = %s ORDER BY id", (country,)):
        existing = one(
            target,
            "SELECT id FROM radar_keywords WHERE country = %s AND normalized_keyword = %s",
            (item["country"], item["normalized_keyword"]),
        )
        record = without_id(item)
        record["created_by_id"] = admin_id if item["created_by_id"] is not None else None
        if existing:
            update_row(target, "radar_keywords", int(existing["id"]), record)
            summary["keywords_updated"] += 1
        else:
            insert_row(target, "radar_keywords", record)
            summary["keywords_inserted"] += 1

    profile_map: dict[int, int] = {}
    for item in rows(source, "SELECT * FROM search_profiles WHERE source = ANY(%s) ORDER BY id", (list(source_names),)):
        existing = one(
            target,
            "SELECT id FROM search_profiles WHERE name = %s AND source = %s ORDER BY id LIMIT 1",
            (item["name"], item["source"]),
        )
        record = without_id(item)
        record["owner_id"] = admin_id if item["owner_id"] is not None else None
        if existing:
            target_id = int(existing["id"])
            update_row(target, "search_profiles", target_id, record)
            summary["profiles_updated"] += 1
        else:
            target_id = insert_row(target, "search_profiles", record)
            summary["profiles_inserted"] += 1
        profile_map[int(item["id"])] = target_id

    run_map: dict[int, int] = {}
    for item in rows(source, "SELECT * FROM scrape_runs WHERE source = ANY(%s) ORDER BY id", (list(source_names),)):
        mapped_profile = profile_map.get(int(item["search_profile_id"])) if item["search_profile_id"] is not None else None
        existing = one(
            target,
            """SELECT id FROM scrape_runs
               WHERE source = %s AND search_profile_id IS NOT DISTINCT FROM %s AND created_at = %s
               ORDER BY id LIMIT 1""",
            (item["source"], mapped_profile, item["created_at"]),
        )
        if existing:
            target_id = int(existing["id"])
            summary["runs_existing"] += 1
        else:
            record = without_id(item)
            record["search_profile_id"] = mapped_profile
            target_id = insert_row(target, "scrape_runs", record)
            summary["runs_inserted"] += 1
        run_map[int(item["id"])] = target_id

    opportunity_map: dict[int, int] = {}
    for item in rows(source, "SELECT * FROM opportunities WHERE source = ANY(%s) ORDER BY id", (list(source_names),)):
        existing = one(
            target,
            "SELECT id, updated_at, is_archived FROM opportunities WHERE source = %s AND external_id = %s",
            (item["source"], item["external_id"]),
        )
        record = without_id(item)
        record["archived_by_id"] = admin_id if item["archived_by_id"] is not None else None
        if not existing:
            target_id = insert_row(target, "opportunities", record)
            summary["opportunities_inserted"] += 1
        else:
            target_id = int(existing["id"])
            target_updated_at = existing["updated_at"]
            if target_updated_at is None or item["updated_at"] >= target_updated_at:
                update_row(target, "opportunities", target_id, record)
                summary["opportunities_updated"] += 1
            else:
                if item["is_archived"] and not existing["is_archived"]:
                    archive_record = {
                        key: record[key]
                        for key in ("is_archived", "archived_at", "archived_by_id", "archive_country", "archive_key")
                    }
                    update_row(target, "opportunities", target_id, archive_record)
                summary["opportunities_preserved_newer"] += 1
        opportunity_map[int(item["id"])] = target_id

    snapshots = rows(
        source,
        """SELECT s.* FROM opportunity_snapshots s
           JOIN opportunities o ON o.id = s.opportunity_id
           WHERE o.source = ANY(%s) ORDER BY s.id""",
        (list(source_names),),
    )
    target_opportunity_ids = list(opportunity_map.values())
    existing_snapshot_keys = {
        (item["opportunity_id"], item["run_id"], item["content_hash"], item["change_type"], item["created_at"])
        for item in rows(
            target,
            """SELECT opportunity_id, run_id, content_hash, change_type, created_at
               FROM opportunity_snapshots WHERE opportunity_id = ANY(%s)""",
            (target_opportunity_ids,),
        )
    }
    new_snapshots: list[dict[str, Any]] = []
    for item in snapshots:
        mapped_opportunity = opportunity_map[int(item["opportunity_id"])]
        mapped_run = run_map.get(int(item["run_id"])) if item["run_id"] is not None else None
        key = (
            mapped_opportunity,
            mapped_run,
            item["content_hash"],
            item["change_type"],
            item["created_at"],
        )
        if key in existing_snapshot_keys:
            summary["snapshots_existing"] += 1
            continue
        record = without_id(item)
        record["opportunity_id"] = mapped_opportunity
        record["run_id"] = mapped_run
        new_snapshots.append(record)
        existing_snapshot_keys.add(key)
        summary["snapshots_inserted"] += 1
    insert_rows(target, "opportunity_snapshots", new_snapshots)

    documents = rows(
        source,
        """SELECT d.* FROM documents d
           JOIN opportunities o ON o.id = d.opportunity_id
           WHERE o.source = ANY(%s) ORDER BY d.id""",
        (list(source_names),),
    )
    for item in documents:
        mapped_opportunity = opportunity_map[int(item["opportunity_id"])]
        existing = one(
            target,
            """SELECT id FROM documents
               WHERE opportunity_id = %s AND source_url = %s AND filename = %s
               ORDER BY id LIMIT 1""",
            (mapped_opportunity, item["source_url"], item["filename"]),
        )
        record = without_id(item)
        record["opportunity_id"] = mapped_opportunity
        # Local filesystem paths are not valid inside Azure; preserve the remote source metadata.
        record["local_path"] = ""
        if existing:
            update_row(target, "documents", int(existing["id"]), record)
            summary["documents_updated"] += 1
        else:
            insert_row(target, "documents", record)
            summary["documents_inserted"] += 1

    source_alerts = rows(
        source,
        """SELECT a.* FROM alerts a
           JOIN opportunities o ON o.id = a.opportunity_id
           WHERE o.source = ANY(%s) ORDER BY a.id""",
        (list(source_names),),
    )
    source_rule_ids = sorted({item["rule_id"] for item in source_alerts})
    rule_map: dict[int, int] = {}
    if source_rule_ids:
        for item in rows(source, "SELECT * FROM alert_rules WHERE id = ANY(%s) ORDER BY id", (source_rule_ids,)):
            existing = one(
                target,
                """SELECT id FROM alert_rules
                   WHERE name = %s AND channel = %s AND destination = %s
                   ORDER BY id LIMIT 1""",
                (item["name"], item["channel"], item["destination"]),
            )
            record = without_id(item)
            if existing:
                target_id = int(existing["id"])
                update_row(target, "alert_rules", target_id, record)
                summary["alert_rules_updated"] += 1
            else:
                target_id = insert_row(target, "alert_rules", record)
                summary["alert_rules_inserted"] += 1
            rule_map[int(item["id"])] = target_id

    for item in source_alerts:
        mapped_opportunity = opportunity_map[int(item["opportunity_id"])]
        mapped_rule = rule_map[int(item["rule_id"])]
        existing = one(
            target,
            """SELECT id FROM alerts
               WHERE opportunity_id = %s AND rule_id = %s AND alert_type = %s""",
            (mapped_opportunity, mapped_rule, item["alert_type"]),
        )
        record = without_id(item)
        record["opportunity_id"] = mapped_opportunity
        record["rule_id"] = mapped_rule
        if existing:
            update_row(target, "alerts", int(existing["id"]), record)
            summary["alerts_updated"] += 1
        else:
            insert_row(target, "alerts", record)
            summary["alerts_inserted"] += 1

    for item in rows(source, "SELECT * FROM app_settings WHERE key LIKE %s ORDER BY id", (f"scheduler.{country}.%",)):
        existing = one(target, "SELECT id FROM app_settings WHERE key = %s", (item["key"],))
        record = without_id(item)
        record["updated_by_id"] = admin_id if item["updated_by_id"] is not None else None
        if existing:
            update_row(target, "app_settings", int(existing["id"]), record)
            summary["settings_updated"] += 1
        else:
            insert_row(target, "app_settings", record)
            summary["settings_inserted"] += 1

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate country-scoped GovRadar data between PostgreSQL databases.")
    parser.add_argument("--country", choices=sorted(COUNTRY_SOURCES), required=True)
    parser.add_argument("--backup-dir", default="exports/migrations")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source_url = os.environ["SOURCE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    target_url = os.environ["TARGET_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)

    with psycopg.connect(source_url) as source, psycopg.connect(target_url) as target:
        backup_path = backup_target(target, args.country, COUNTRY_SOURCES[args.country], Path(args.backup_dir))
        summary = migrate(source, target, args.country)
        if args.dry_run:
            target.rollback()
        else:
            target.commit()
        print(
            json.dumps(
                {"country": args.country, "dry_run": args.dry_run, "backup": str(backup_path), "summary": summary},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
