from __future__ import annotations

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import RadarKeyword, SearchProfile
from backend.app.radar_config import AUTO_PROFILE_PREFIX, DEFAULT_RADAR_KEYWORDS
from backend.app.services.scheduler_service import sync_radar_profiles


class RadarProfileSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()

    def tearDown(self) -> None:
        self.db.close()

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


if __name__ == "__main__":
    unittest.main()
