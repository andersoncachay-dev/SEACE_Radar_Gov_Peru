from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import AppSetting, RadarKeyword, SearchProfile
from backend.app.radar_config import AUTO_PROFILE_PREFIX, DEFAULT_RADAR_KEYWORDS
from backend.app.services.scheduler_service import (
    DEFAULT_INTERVAL_SECONDS,
    claim_external_scheduler_run,
    current_ingestion_period,
    current_ingestion_window,
    get_scheduler_interval,
    scheduler_initial_delay,
    sync_radar_profiles,
)
from backend.app.services import scheduler_service


class RadarProfileSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_session_local = scheduler_service.SessionLocal
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(bind=engine, future=True)
        self.db = self.session_factory()

    def tearDown(self) -> None:
        scheduler_service.SessionLocal = self.original_session_local
        self.db.close()

    def test_country_interval_defaults_to_fifteen_minutes_and_accepts_persisted_value(self) -> None:
        self.assertEqual(get_scheduler_interval(self.db, "peru"), DEFAULT_INTERVAL_SECONDS)
        self.db.add(AppSetting(key="scheduler.peru.interval_seconds", value="93600"))
        self.db.commit()
        self.assertEqual(get_scheduler_interval(self.db, "peru"), 93600)

    def test_country_jobs_keep_distinct_initial_phases(self) -> None:
        self.assertEqual(scheduler_initial_delay("peru", 900), 900)
        self.assertEqual(scheduler_initial_delay("chile", 900), 1200)
        self.assertEqual(scheduler_initial_delay("chile", 60), 90)

    def test_external_jobs_honor_each_country_persisted_interval(self) -> None:
        scheduler_service.SessionLocal = self.session_factory
        self.db.add_all(
            [
                AppSetting(key="scheduler.peru.interval_seconds", value="1800"),
                AppSetting(key="scheduler.chile.interval_seconds", value="3600"),
            ]
        )
        self.db.commit()
        initial = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)

        peru_due, _ = claim_external_scheduler_run("peru", initial)
        chile_due, _ = claim_external_scheduler_run("chile", initial)
        self.assertFalse(peru_due)
        self.assertFalse(chile_due)

        peru_due, peru_next = claim_external_scheduler_run("peru", initial.replace(minute=30))
        chile_due, chile_next = claim_external_scheduler_run("chile", initial.replace(minute=30))
        self.assertTrue(peru_due)
        self.assertFalse(chile_due)
        self.assertEqual(peru_next, datetime(2026, 7, 16, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(chile_next, datetime(2026, 7, 16, 2, 0, tzinfo=timezone.utc))

    def test_creates_country_profiles_and_tracks_custom_keywords(self) -> None:
        # Base keywords are seeded as regular radar_keywords rows (by the
        # 20260721_0030 migration in real deployments) rather than hardcoded,
        # so admins can edit/retire them like any other keyword.
        for country in ("peru", "chile"):
            for keyword in DEFAULT_RADAR_KEYWORDS:
                self.db.add(RadarKeyword(country=country, keyword=keyword, normalized_keyword=keyword.casefold()))
        self.db.commit()

        sync_radar_profiles(self.db)
        profiles = list(
            self.db.scalars(select(SearchProfile).where(SearchProfile.name.startswith(f"{AUTO_PROFILE_PREFIX} ·"))).all()
        )
        self.assertEqual(len(profiles), len(DEFAULT_RADAR_KEYWORDS) * 2)
        self.assertEqual({item.source for item in profiles}, {"oece_ocds_api", "mercado_publico_lmp_gc"})

        custom = RadarKeyword(
            country="peru",
            keyword="fibra óptica",
            normalized_keyword="fibra optica",
        )
        self.db.add(custom)
        self.db.commit()
        sync_radar_profiles(self.db)
        custom_profile = self.db.scalar(
            select(SearchProfile).where(SearchProfile.name == f"{AUTO_PROFILE_PREFIX} · Perú · fibra óptica")
        )
        self.assertIsNotNone(custom_profile)
        self.assertTrue(custom_profile.is_active)

        self.db.delete(custom)
        self.db.commit()
        sync_radar_profiles(self.db)
        self.db.refresh(custom_profile)
        self.assertFalse(custom_profile.is_active)

    def test_automatic_ingestion_uses_only_current_lima_month(self) -> None:
        period = current_ingestion_period(datetime(2026, 8, 1, 2, 30, tzinfo=timezone.utc))

        self.assertEqual(
            period,
            {"year": "2026", "month": "7", "years": ["2026"], "months": ["7"]},
        )

    def test_chile_incremental_window_uses_closing_dates_into_the_future(self) -> None:
        window = current_ingestion_window(
            self.db,
            "chile",
            datetime(2026, 8, 1, 2, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(window["publication_date_from"], "2026-07-29")
        self.assertEqual(window["publication_date_to"], "2026-09-07")
        self.assertEqual(window["years"], ["2026"])
        self.assertEqual(window["months"], ["7", "8", "9"])
        self.assertEqual(window["date_filter_type"], "closing")
        self.assertTrue(window["skip_detail_enrichment"])
        self.assertTrue(window["active_only"])
        self.assertTrue(window["automatic_incremental"])

    def test_peru_incremental_window_remains_anteayer_through_today(self) -> None:
        window = current_ingestion_window(
            self.db,
            "peru",
            datetime(2026, 8, 1, 2, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(window["publication_date_from"], "2026-07-29")
        self.assertEqual(window["publication_date_to"], "2026-07-31")
        self.assertEqual(window["date_filter_type"], "publication")
        self.assertFalse(window["skip_detail_enrichment"])

    def test_radio_enlace_is_not_a_base_keyword(self) -> None:
        self.assertNotIn("radio enlace", {item.casefold() for item in DEFAULT_RADAR_KEYWORDS})


if __name__ == "__main__":
    unittest.main()
