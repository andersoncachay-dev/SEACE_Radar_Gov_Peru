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
    current_ingestion_period,
    current_ingestion_window,
    get_scheduler_interval,
    scheduler_initial_delay,
    sync_radar_profiles,
)


class RadarProfileSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()

    def tearDown(self) -> None:
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

    def test_creates_country_profiles_and_tracks_custom_keywords(self) -> None:
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

    def test_incremental_window_is_anteayer_through_today_in_lima(self) -> None:
        window = current_ingestion_window(
            self.db,
            "chile",
            datetime(2026, 8, 1, 2, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(window["publication_date_from"], "2026-07-29")
        self.assertEqual(window["publication_date_to"], "2026-07-31")
        self.assertEqual(window["years"], ["2026"])
        self.assertEqual(window["months"], ["7"])
        self.assertTrue(window["active_only"])
        self.assertTrue(window["automatic_incremental"])

    def test_radio_enlace_is_not_a_base_keyword(self) -> None:
        self.assertNotIn("radio enlace", {item.casefold() for item in DEFAULT_RADAR_KEYWORDS})


if __name__ == "__main__":
    unittest.main()
