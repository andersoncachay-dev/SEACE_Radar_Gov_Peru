from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import PasswordResetToken, User
from backend.app.security import hash_password, verify_password
from backend.app.services.password_reset_service import request_password_reset, reset_password


class PasswordResetTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.user = User(
            email="usuario@example.com",
            full_name="Usuario Prueba",
            first_name="Usuario",
            password_hash=hash_password("ClaveAnterior1"),
            is_active=True,
        )
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)

    def tearDown(self) -> None:
        self.db.close()

    def test_request_sends_link_and_stores_only_hash(self) -> None:
        with patch("backend.app.services.password_reset_service._send_email") as send_email:
            request_password_reset(self.db, "USUARIO@example.com")

        stored = self.db.scalar(select(PasswordResetToken))
        self.assertIsNotNone(stored)
        self.assertEqual(len(stored.token_hash), 64)
        message = send_email.call_args.args[1]
        raw_token = message.split("reset_token=", 1)[1].split("\n", 1)[0]
        self.assertNotIn(raw_token, stored.token_hash)
        self.assertTrue(reset_password(self.db, raw_token, "ClaveNueva123"))
        self.assertTrue(verify_password("ClaveNueva123", self.user.password_hash))
        self.assertFalse(reset_password(self.db, raw_token, "OtraClave123"))

    def test_expired_token_is_rejected(self) -> None:
        expired = PasswordResetToken(
            user_id=self.user.id,
            token_hash="0" * 64,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        self.db.add(expired)
        self.db.commit()
        self.assertFalse(reset_password(self.db, "token-inexistente-con-longitud-suficiente", "ClaveNueva123"))

    def test_unknown_email_has_same_silent_result(self) -> None:
        with patch("backend.app.services.password_reset_service._send_email") as send_email:
            self.assertIsNone(request_password_reset(self.db, "nadie@example.com"))
        send_email.assert_not_called()
        self.assertEqual(self.db.scalar(select(PasswordResetToken)), None)


if __name__ == "__main__":
    unittest.main()
