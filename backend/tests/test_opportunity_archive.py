from __future__ import annotations

import unittest

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import Opportunity, User
from backend.app.routers.opportunities import archive_opportunity, archive_opportunities_by_keyword, list_archived_opportunities, list_opportunities, restore_opportunity
from backend.app.schemas import OpportunityKeywordArchiveIn
from backend.app.services.ingestion_service import upsert_opportunities


class OpportunityArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.user = User(
            email="gestor@example.com",
            full_name="Gestor Comercial",
            first_name="Gestor",
            last_name="Comercial",
            access_profile="both",
            password_hash="test",
        )
        self.opportunity = Opportunity(
            source="oece_ocds_api",
            external_id="CP-TEST-2026-1",
            nomenclature="CP-TEST-2026-1",
            entity="Entidad de prueba",
            description="Servicio de conectividad",
        )
        self.db.add_all([self.user, self.opportunity])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_archive_excludes_from_active_and_ingestion_until_restored(self) -> None:
        archive_opportunity(self.opportunity.id, self.user, self.db)

        self.assertEqual(list_opportunities(current_user=self.user, db=self.db), [])
        archived = list_archived_opportunities("peru", self.user, self.db)
        self.assertEqual([item["id"] for item in archived], [self.opportunity.id])

        imported = upsert_opportunities(
            self.db,
            pd.DataFrame([{"nomenclatura": "CP-TEST-2026-1", "descripcion": "Texto actualizado"}]),
            "seace_public_browser",
        )
        self.assertEqual(imported, 0)
        self.assertEqual(self.db.scalar(select(Opportunity).where(Opportunity.source == "seace_public_browser")), None)

        restore_opportunity(self.opportunity.id, self.user, self.db)
        active = list_opportunities(current_user=self.user, db=self.db)
        self.assertEqual([item["id"] for item in active], [self.opportunity.id])

    def test_archive_by_keyword_moves_only_matching_country_processes(self) -> None:
        exclusive = Opportunity(
            source="oece_ocds_api",
            external_id="CP-SAT-2026-2",
            nomenclature="CP-SAT-2026-2",
            entity="Entidad de comunicaciones",
            description="Servicio satelital administrado",
        )
        overlapping = Opportunity(
            source="oece_ocds_api",
            external_id="CP-SAT-2026-3",
            nomenclature="CP-SAT-2026-3",
            entity="Entidad de comunicaciones",
            description="Servicio de internet satelital administrado",
        )
        chile = Opportunity(
            source="mercado_publico_lmp_gc",
            external_id="CL-SAT-2026-1",
            nomenclature="CL-SAT-2026-1",
            entity="Entidad Chile",
            description="Servicio de internet satelital",
        )
        self.db.add_all([exclusive, overlapping, chile])
        self.db.commit()

        result = archive_opportunities_by_keyword(
            OpportunityKeywordArchiveIn(country="peru", keyword="satelital", remaining_keywords=["internet"]),
            self.user,
            self.db,
        )

        self.assertEqual(result["archived"], 1)
        self.assertEqual(result["opportunity_ids"], [exclusive.id])
        self.assertTrue(self.db.get(Opportunity, exclusive.id).is_archived)
        self.assertFalse(self.db.get(Opportunity, overlapping.id).is_archived)
        self.assertFalse(self.db.get(Opportunity, chile.id).is_archived)
        self.assertFalse(self.db.get(Opportunity, self.opportunity.id).is_archived)

    def test_lightweight_refresh_preserves_existing_enrichment(self) -> None:
        self.opportunity.status = "Vigente para Propuesta"
        self.opportunity.region = "Lima"
        self.opportunity.detail_url = "https://example.com/detail"
        self.opportunity.priority = "B"
        self.opportunity.score = 42
        self.db.commit()

        upsert_opportunities(
            self.db,
            pd.DataFrame([{
                "nomenclatura": self.opportunity.nomenclature,
                "descripcion": self.opportunity.description,
            }]),
            self.opportunity.source,
        )

        refreshed = self.db.get(Opportunity, self.opportunity.id)
        self.assertEqual(refreshed.status, "Vigente para Propuesta")
        self.assertEqual(refreshed.region, "Lima")
        self.assertEqual(refreshed.detail_url, "https://example.com/detail")
        self.assertEqual(refreshed.priority, "B")
        self.assertEqual(refreshed.score, 42)


if __name__ == "__main__":
    unittest.main()
