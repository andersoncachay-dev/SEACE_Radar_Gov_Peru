from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.config import settings
from backend.app.models import Alert, AlertRule
from backend.app.services.notification_service import send_pending_alerts


class AlertDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.rule = AlertRule(
            name="Prueba comercial",
            channel="email",
            destination="ventas@example.com",
            min_priority="A",
            hours_before_deadline=48,
            is_active=True,
        )
        self.db.add(self.rule)
        self.db.commit()
        self.db.refresh(self.rule)

    def tearDown(self) -> None:
        self.db.close()

    def _alert(self) -> Alert:
        alert = Alert(
            opportunity_id=1,
            rule_id=self.rule.id,
            alert_type="new_process",
            status="pending",
            message="Mensaje comercial original",
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def test_success_keeps_provider_tracking(self) -> None:
        alert = self._alert()
        with patch("backend.app.services.notification_service._send_email", return_value="provider-123"):
            send_pending_alerts(self.db)
        self.db.refresh(alert)
        self.assertEqual(alert.status, "sent")
        self.assertEqual(alert.attempt_count, 1)
        self.assertEqual(alert.provider_message_id, "provider-123")
        self.assertIsNotNone(alert.sent_at)

    def test_failure_retries_then_stops_without_changing_message(self) -> None:
        alert = self._alert()
        with patch("backend.app.services.notification_service._send_email", side_effect=RuntimeError("provider unavailable")):
            for _ in range(5):
                send_pending_alerts(self.db)
                self.db.refresh(alert)
                if alert.next_attempt_at:
                    alert.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
                    self.db.commit()
        self.db.refresh(alert)
        self.assertEqual(alert.status, "failed")
        self.assertEqual(alert.attempt_count, 5)
        self.assertEqual(alert.message, "Mensaje comercial original")
        self.assertIn("provider unavailable", alert.last_error)

    def test_disabled_whatsapp_waits_without_consuming_attempts(self) -> None:
        self.rule.channel = "whatsapp"
        self.rule.destination = "+51999999999"
        self.db.commit()
        alert = self._alert()
        disabled_settings = replace(settings, whatsapp_enabled=False)

        with (
            patch("backend.app.services.notification_service.settings", disabled_settings),
            patch("backend.app.services.notification_service._send_whatsapp") as send_whatsapp,
        ):
            send_pending_alerts(self.db)

        self.db.refresh(alert)
        self.assertEqual(alert.status, "waiting_channel")
        self.assertEqual(alert.attempt_count, 0)
        self.assertIsNone(alert.next_attempt_at)
        send_whatsapp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
