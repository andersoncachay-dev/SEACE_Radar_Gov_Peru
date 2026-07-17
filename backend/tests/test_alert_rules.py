from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import Alert, AlertRule, Opportunity, OpportunitySnapshot, ScrapeRun
from backend.app.routers.alerts import delete_rule, list_alerts, update_rule
from backend.app.schemas import AlertRuleUpdate
from backend.app.services.notification_service import _matches_rule_keywords, evaluate_alerts, evaluate_new_opportunity_alerts, send_pending_alerts


class AlertRuleManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.rule = AlertRule(
            name="Radar prioridad A",
            channel="email",
            destination="ventas@example.com",
            min_priority="A",
            is_active=True,
        )
        self.db.add(self.rule)
        self.db.commit()
        self.db.refresh(self.rule)

    def tearDown(self) -> None:
        self.db.close()

    def test_updates_rule_with_validated_destination(self) -> None:
        updated = update_rule(
            self.rule.id,
            AlertRuleUpdate(
                name="Radar WhatsApp",
                channel="whatsapp",
                destination="+51987654321",
                min_priority="B",
            ),
            None,
            self.db,
        )

        self.assertEqual(updated.name, "Radar WhatsApp")
        self.assertEqual(updated.channel, "whatsapp")
        self.assertEqual(updated.destination, "+51987654321")
        self.assertEqual(updated.min_priority, "B")

    def test_deletes_rule_and_associated_alert_history(self) -> None:
        alert = Alert(
            opportunity_id=42,
            rule_id=self.rule.id,
            alert_type="new_process",
            status="pending",
            message="Nueva oportunidad",
        )
        self.db.add(alert)
        self.db.commit()

        delete_rule(self.rule.id, None, self.db)

        self.assertIsNone(self.db.get(AlertRule, self.rule.id))
        self.assertEqual(list(self.db.scalars(select(Alert)).all()), [])

    def test_periodic_evaluation_does_not_create_deadline_alerts(self) -> None:
        self.assertEqual(evaluate_alerts(self.db), [])
        self.assertEqual(list(self.db.scalars(select(Alert)).all()), [])

    def test_description_keywords_match_any_phrase_without_accents_or_case(self) -> None:
        configured = "Internet SATELITAL, fibra óptica, enlace de datos"
        self.assertTrue(_matches_rule_keywords("Servicio de internet satelital para sedes rurales", configured))
        self.assertTrue(_matches_rule_keywords("Implementación de FIBRA OPTICA", configured))
        self.assertFalse(_matches_rule_keywords("Compra de mobiliario para oficinas", configured))
        self.assertTrue(_matches_rule_keywords("Cualquier proceso", ""))

    def test_new_process_alert_is_created_once_and_matches_entity_text(self) -> None:
        self.rule.keywords = "municipalidad satelital"
        self.rule.min_priority = "C"
        run = ScrapeRun(source="mercado_publico_lmp_gc", status="completed")
        opportunity = Opportunity(
            source="mercado_publico_lmp_gc",
            external_id="CL-NEW-1",
            nomenclature="CL-NEW-1",
            entity="Municipalidad Satelital",
            description="Servicio de comunicaciones",
            priority="C",
        )
        self.db.add_all([run, opportunity])
        self.db.flush()
        self.db.add(OpportunitySnapshot(
            opportunity_id=opportunity.id,
            run_id=run.id,
            content_hash="hash",
            change_type="created",
        ))
        self.db.commit()

        first = evaluate_new_opportunity_alerts(self.db, run.id)
        second = evaluate_new_opportunity_alerts(self.db, run.id)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(list(self.db.scalars(select(Alert)).all())), 1)

    def test_country_scoped_rule_ignores_the_other_countrys_opportunities(self) -> None:
        self.rule.min_priority = "C"
        self.rule.country = "peru"
        run = ScrapeRun(source="mercado_publico_lmp_gc", status="completed")
        chile_opportunity = Opportunity(
            source="mercado_publico_lmp_gc",
            external_id="CL-SCOPED-1",
            nomenclature="CL-SCOPED-1",
            entity="Municipalidad de Santiago",
            description="Servicio de comunicaciones",
            priority="C",
        )
        peru_opportunity = Opportunity(
            source="oece_ocds_api",
            external_id="PE-SCOPED-1",
            nomenclature="PE-SCOPED-1",
            entity="Gobierno Regional de Lima",
            description="Servicio de comunicaciones",
            priority="C",
        )
        self.db.add_all([run, chile_opportunity, peru_opportunity])
        self.db.flush()
        self.db.add_all([
            OpportunitySnapshot(opportunity_id=chile_opportunity.id, run_id=run.id, content_hash="cl-hash", change_type="created"),
            OpportunitySnapshot(opportunity_id=peru_opportunity.id, run_id=run.id, content_hash="pe-hash", change_type="created"),
        ])
        self.db.commit()

        created = evaluate_new_opportunity_alerts(self.db, run.id)

        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].opportunity_id, peru_opportunity.id)

    def test_list_alerts_includes_opportunity_and_rule_details(self) -> None:
        self.rule.min_priority = "C"
        run = ScrapeRun(source="mercado_publico_lmp_gc", status="completed")
        opportunity = Opportunity(
            source="mercado_publico_lmp_gc",
            external_id="CL-LIST-1",
            nomenclature="CL-LIST-1",
            entity="Municipalidad de Listado",
            description="Servicio satelital de prueba",
            priority="C",
        )
        self.db.add_all([run, opportunity])
        self.db.flush()
        self.db.add(OpportunitySnapshot(
            opportunity_id=opportunity.id,
            run_id=run.id,
            content_hash="list-hash",
            change_type="created",
        ))
        self.db.commit()
        evaluate_new_opportunity_alerts(self.db, run.id)

        results = list_alerts(None, self.db)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["entity"], "Municipalidad de Listado")
        self.assertEqual(results[0]["description"], "Servicio satelital de prueba")
        self.assertEqual(results[0]["channel"], "email")
        self.assertEqual(results[0]["country"], "chile")

    def test_list_alerts_flags_alerts_from_deactivated_rules(self) -> None:
        self.rule.min_priority = "C"
        run = ScrapeRun(source="mercado_publico_lmp_gc", status="completed")
        opportunity = Opportunity(
            source="mercado_publico_lmp_gc",
            external_id="CL-DEACTIVATED-1",
            nomenclature="CL-DEACTIVATED-1",
            entity="Municipalidad Desactivada",
            description="Servicio satelital de prueba",
            priority="C",
        )
        self.db.add_all([run, opportunity])
        self.db.flush()
        self.db.add(OpportunitySnapshot(
            opportunity_id=opportunity.id,
            run_id=run.id,
            content_hash="deactivated-hash",
            change_type="created",
        ))
        self.db.commit()
        evaluate_new_opportunity_alerts(self.db, run.id)

        # A rule turned off after its alert was generated must not disappear
        # from history, but the frontend needs to know not to surface it as
        # a "recent" alert on the country's Home module.
        self.rule.is_active = False
        self.db.commit()

        results = list_alerts(None, self.db)

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0]["rule_is_active"])

    def test_closed_historical_process_does_not_create_new_alert(self) -> None:
        self.rule.min_priority = "C"
        run = ScrapeRun(source="mercado_publico_lmp_gc", status="completed")
        opportunity = Opportunity(
            source="mercado_publico_browser",
            external_id="CL-HISTORICAL-1",
            nomenclature="CL-HISTORICAL-1",
            description="Servicio de internet",
            status="Proceso Culminado",
            proposal_deadline=datetime.utcnow() - timedelta(days=30),
            priority="C",
        )
        self.db.add_all([run, opportunity])
        self.db.flush()
        self.db.add(OpportunitySnapshot(
            opportunity_id=opportunity.id,
            run_id=run.id,
            content_hash="historical-hash",
            change_type="created",
        ))
        self.db.commit()

        self.assertEqual(evaluate_new_opportunity_alerts(self.db, run.id), [])
        self.assertEqual(list(self.db.scalars(select(Alert)).all()), [])

    def test_pending_historical_alert_is_marked_skipped(self) -> None:
        opportunity = Opportunity(
            source="mercado_publico_browser",
            external_id="CL-HISTORICAL-2",
            nomenclature="CL-HISTORICAL-2",
            status="Proceso Culminado",
            proposal_deadline=datetime.utcnow() - timedelta(days=10),
        )
        self.db.add(opportunity)
        self.db.flush()
        alert = Alert(
            opportunity_id=opportunity.id,
            rule_id=self.rule.id,
            alert_type="new_process",
            status="waiting_channel",
            message="Nueva oportunidad",
        )
        self.db.add(alert)
        self.db.commit()

        send_pending_alerts(self.db)
        self.db.refresh(alert)

        self.assertEqual(alert.status, "skipped")
        self.assertIn("histórico o vencido", alert.last_error)


if __name__ == "__main__":
    unittest.main()
