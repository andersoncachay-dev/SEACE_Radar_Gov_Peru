from __future__ import annotations

from datetime import datetime, timedelta
import unittest

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import Opportunity
from backend.app.services.ingestion_service import _as_datetime
from backend.app.services.run_service import (
    _finalize_stale_peru_consultations,
    _peru_pending_schedule_rows,
    _peru_schedule_targets,
    _seace_has_proposal_schedule,
)
from src.normalizer import normalize_columns
from src.oece_ocds_connector import _parse_csv_row, _parse_date


class PeruSchedulePipelineTests(unittest.TestCase):
    def test_seace_result_requires_requested_process_with_proposal_deadline(self) -> None:
        unrelated = pd.DataFrame({
            "Nomenclatura": ["CP-ABR-99-2026-OTRA-1"],
            "propuesta_fin": ["30/07/2026 23:59"],
        })
        requested_without_schedule = pd.DataFrame({
            "Nomenclatura": ["CP-ABR-5-2026-MDL/DEC-1", "CP-ABR-5-2026-MDL/DEC-1"],
            "propuesta_fin": ["", float("nan")],
        })
        requested_with_schedule = pd.DataFrame({
            "Nomenclatura": ["CP-ABR-5-2026-MDL/DEC-1"],
            "propuesta_fin": ["30/07/2026 23:59"],
        })

        self.assertFalse(_seace_has_proposal_schedule(unrelated, "CP-ABR-5-2026-MDL/DEC-1"))
        self.assertFalse(_seace_has_proposal_schedule(requested_without_schedule, "CP-ABR-5-2026-MDL/DEC-1"))
        self.assertTrue(_seace_has_proposal_schedule(requested_with_schedule, "CP-ABR-5-2026-MDL/DEC-1"))

    def test_iso_dates_are_not_reinterpreted_as_day_first(self) -> None:
        self.assertEqual(_as_datetime("2026-07-11 04:59:00"), datetime(2026, 7, 11, 4, 59))
        normalized = normalize_columns(
            pd.DataFrame({"consulta_fin": ["2026-07-11 04:59:00", "11/07/2026 04:59:00"]})
        )
        self.assertEqual(normalized.iloc[0]["consulta_fin"].to_pydatetime(), datetime(2026, 7, 11, 4, 59))
        self.assertEqual(normalized.iloc[1]["consulta_fin"].to_pydatetime(), datetime(2026, 7, 11, 4, 59))
        self.assertEqual(_parse_date("2026/07/08"), datetime(2026, 7, 8))

    def test_ocds_supplies_publication_and_consultation_dates(self) -> None:
        row = pd.Series(
            {
                "Entrega compilada:Licitación:Título de la licitación": "CP SER-SM-10-2026-RENIEC-1",
                "compiledRelease/tender/datePublished": "2026-06-26T15:48:00-05:00",
                "Entrega compilada:Licitación:Periodo de consulta:Fecha de fin": "2026-07-10T23:59:00-05:00",
                "Entrega compilada:Licitación:Periodo de licitación:Fecha de fin": "2026-07-20T23:59:00-05:00",
            }
        )

        parsed = _parse_csv_row(row, "seace_v3")

        self.assertEqual(parsed["Fecha y Hora de Publicacion"], datetime(2026, 6, 26, 20, 48))
        self.assertEqual(parsed["consulta_fin"], datetime(2026, 7, 11, 4, 59))
        self.assertEqual(parsed["propuesta_fin"], datetime(2026, 7, 21, 4, 59))

    def test_progressive_queue_skips_schedules_already_validated_by_seace(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, future=True)()
        db.add_all(
            [
                Opportunity(source="oece_ocds_api", external_id="PENDING", nomenclature="PENDING"),
                Opportunity(
                    source="oece_ocds_api",
                    external_id="VALIDATED",
                    nomenclature="VALIDATED",
                    proposal_deadline=datetime(2026, 7, 20, 18),
                    schedule_source="seace",
                    schedule_validated_at=datetime(2026, 7, 15, 18),
                ),
            ]
        )
        db.commit()
        rows = pd.DataFrame({
            "Nomenclatura": ["PENDING", "VALIDATED", "NEW"],
            "Fecha y Hora de Publicacion": [datetime.utcnow(), datetime.utcnow(), datetime.utcnow()],
            "consulta_fin": [datetime.utcnow(), datetime.utcnow(), datetime.utcnow()],
        })

        targets = _peru_schedule_targets(db, "oece_ocds_api", rows)

        self.assertEqual(targets, ["PENDING", "NEW"])
        self.assertEqual(rows["replace_schedule"].tolist(), [True, False, True])
        db.close()

    def test_only_new_excludes_already_saved_but_still_pending_rows(self) -> None:
        """Automatic runs must not re-search SEACE for rows already saved.

        ``only_new=True`` (used by scheduled/automatic runs) should skip
        "PENDING" - already in the opportunities table, just not yet SEACE-
        validated - and only target "NEW", a nomenclature not saved at all.
        Manual revalidation keeps the default (only_new=False) behavior, which
        still retries "PENDING".
        """
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, future=True)()
        db.add_all(
            [
                Opportunity(source="oece_ocds_api", external_id="PENDING", nomenclature="PENDING"),
                Opportunity(
                    source="oece_ocds_api",
                    external_id="VALIDATED",
                    nomenclature="VALIDATED",
                    proposal_deadline=datetime(2026, 7, 20, 18),
                    schedule_source="seace",
                    schedule_validated_at=datetime(2026, 7, 15, 18),
                ),
            ]
        )
        db.commit()
        rows = pd.DataFrame({
            "Nomenclatura": ["PENDING", "VALIDATED", "NEW"],
            "Fecha y Hora de Publicacion": [datetime.utcnow(), datetime.utcnow(), datetime.utcnow()],
            "consulta_fin": [datetime.utcnow(), datetime.utcnow(), datetime.utcnow()],
        })

        targets = _peru_schedule_targets(db, "oece_ocds_api", rows, only_new=True)

        self.assertEqual(targets, ["NEW"])
        db.close()

    def test_unproven_legacy_deadline_is_revalidated(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, future=True)()
        db.add(
            Opportunity(
                source="oece_ocds_api",
                external_id="LEGACY",
                nomenclature="LEGACY",
                proposal_deadline=datetime(2026, 10, 7, 23, 59),
            )
        )
        db.commit()
        rows = pd.DataFrame({
            "Nomenclatura": ["LEGACY"],
            "Fecha y Hora de Publicacion": [datetime.utcnow()],
            "consulta_fin": [datetime.utcnow()],
        })

        self.assertEqual(_peru_schedule_targets(db, "oece_ocds_api", rows), ["LEGACY"])
        self.assertTrue(bool(rows.iloc[0]["replace_schedule"]))
        db.close()

    def test_older_than_30_days_requires_manual_validation(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, future=True)()
        rows = pd.DataFrame({
            "Nomenclatura": ["OLD"],
            "Fecha y Hora de Publicacion": [datetime(2026, 1, 1)],
            "consulta_fin": [datetime.utcnow() - timedelta(days=31)],
        })

        self.assertEqual(_peru_schedule_targets(db, "oece_ocds_api", rows), [])
        self.assertEqual(
            _peru_schedule_targets(db, "oece_ocds_api", rows, allow_older=True),
            ["OLD"],
        )
        db.close()

    def test_saved_pending_queue_does_not_depend_on_ocds_results(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, future=True)()
        db.add_all(
            [
                Opportunity(
                    source="oece_ocds_api",
                    external_id="PENDING-SAT",
                    nomenclature="PENDING-SAT",
                    description="Servicio de internet satelital",
                    publication_date=datetime.utcnow(),
                    consultation_deadline=datetime.utcnow(),
                ),
                Opportunity(
                    source="oece_ocds_api",
                    external_id="VALIDATED-SAT",
                    nomenclature="VALIDATED-SAT",
                    description="Servicio satelital",
                    schedule_source="seace",
                    schedule_validated_at=datetime(2026, 7, 15),
                ),
            ]
        )
        db.commit()

        queued = _peru_pending_schedule_rows(db, "oece_ocds_api", "satelital", 15)

        self.assertEqual([row["Nomenclatura"] for row in queued], ["PENDING-SAT"])
        self.assertTrue(queued[0]["replace_schedule"])
        db.close()

    def test_consultation_older_than_30_days_is_closed_but_future_seace_proposal_wins(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, future=True)()
        db.add_all(
            [
                Opportunity(
                    source="oece_ocds_api",
                    external_id="STALE",
                    nomenclature="STALE",
                    status="Vigente para Propuesta",
                    consultation_deadline=datetime.utcnow() - timedelta(days=31),
                ),
                Opportunity(
                    source="oece_ocds_api",
                    external_id="SEACE-FUTURE",
                    nomenclature="SEACE-FUTURE",
                    status="Vigente para Propuesta",
                    consultation_deadline=datetime.utcnow() - timedelta(days=31),
                    proposal_deadline=datetime.utcnow() + timedelta(days=5),
                    schedule_source="seace",
                ),
            ]
        )
        db.commit()

        self.assertEqual(_finalize_stale_peru_consultations(db, "oece_ocds_api"), 1)
        stale = db.scalar(select(Opportunity).where(Opportunity.external_id == "STALE"))
        seace_future = db.scalar(select(Opportunity).where(Opportunity.external_id == "SEACE-FUTURE"))
        self.assertEqual(stale.status, "Proceso Culminado")
        self.assertEqual(seace_future.status, "Vigente para Propuesta")
        db.close()


if __name__ == "__main__":
    unittest.main()
