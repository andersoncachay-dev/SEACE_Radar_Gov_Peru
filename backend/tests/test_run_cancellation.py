from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import ScrapeRun
from backend.app.services import run_service


class RunCancellationTests(unittest.TestCase):
    def test_service_restart_closes_orphaned_runs(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, future=True)
        db = session_factory()
        db.add_all([
            ScrapeRun(source="oece_ocds_api", status="running", cancel_requested=True),
            ScrapeRun(source="mercado_publico_lmp_gc", status="running", cancel_requested=False),
            ScrapeRun(source="oece_ocds_api", status="queued", cancel_requested=False),
        ])
        db.commit()
        db.close()

        original_session_factory = run_service.SessionLocal
        run_service.SessionLocal = session_factory
        try:
            reconciled = run_service.reconcile_interrupted_runs()
        finally:
            run_service.SessionLocal = original_session_factory

        verify_db = session_factory()
        runs = list(verify_db.query(ScrapeRun).order_by(ScrapeRun.id).all())
        self.assertEqual(reconciled, 3)
        self.assertEqual([run.status for run in runs], ["cancelled", "failed", "failed"])
        self.assertTrue(all(run.finished_at is not None for run in runs))
        verify_db.close()

    def test_cancelled_queued_run_never_starts_connector(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, future=True)
        db = session_factory()
        run = ScrapeRun(source="oece_ocds_api", status="queued")
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
        db.close()

        original_session_factory = run_service.SessionLocal
        run_service.SessionLocal = session_factory
        try:
            run_service.request_run_cancel(run_id)
            run_service.execute_scrape_run(run_id, {"source": "oece_ocds_api", "keyword": "satelital"})
        finally:
            run_service.SessionLocal = original_session_factory

        verify_db = session_factory()
        cancelled_run = verify_db.get(ScrapeRun, run_id)
        self.assertEqual(cancelled_run.status, "cancelled")
        self.assertEqual(cancelled_run.progress_message, "Búsqueda detenida")
        self.assertIsNotNone(cancelled_run.finished_at)
        verify_db.close()


if __name__ == "__main__":
    unittest.main()
