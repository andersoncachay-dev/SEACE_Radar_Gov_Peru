from __future__ import annotations

import unittest

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import Alert, AlertRule
from backend.app.routers.alerts import delete_rule, update_rule
from backend.app.schemas import AlertRuleUpdate
from backend.app.services.notification_service import _matches_rule_keywords, evaluate_alerts


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


if __name__ == "__main__":
    unittest.main()
