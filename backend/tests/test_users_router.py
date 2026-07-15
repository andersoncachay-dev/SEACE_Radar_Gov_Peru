from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import User
from backend.app.routers.users import update_user
from backend.app.schemas import UserUpdate
from backend.app.security import hash_password, verify_password


class UserUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.admin = User(
            email="admin@example.com",
            full_name="Admin Radar",
            first_name="Admin",
            last_name="Radar",
            password_hash=hash_password("Admin12345"),
            role="admin",
        )
        self.user = User(
            email="usuario@example.com",
            full_name="Usuario Original",
            first_name="Usuario",
            last_name="Original",
            position="Analista",
            address="Lima",
            phone_peru="+51999999999",
            access_profile="peru",
            password_hash=hash_password("Original123"),
        )
        self.other = User(
            email="otro@example.com",
            full_name="Otro Usuario",
            first_name="Otro",
            last_name="Usuario",
            password_hash=hash_password("Original123"),
        )
        self.db.add_all([self.admin, self.user, self.other])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_updates_profile_and_email_without_replacing_password(self) -> None:
        original_hash = self.user.password_hash
        updated = update_user(
            self.user.id,
            UserUpdate(
                email="NUEVO@EXAMPLE.COM",
                first_name="Andrea",
                last_name="Valdivia",
                position="Ejecutiva comercial",
                address="Santiago",
                phone_peru="",
                phone_chile="+56999999999",
                access_profile="chile",
                role="viewer",
            ),
            self.admin,
            self.db,
        )

        self.assertEqual(updated.email, "nuevo@example.com")
        self.assertEqual(updated.full_name, "Andrea Valdivia")
        self.assertEqual(updated.access_profile, "chile")
        self.assertEqual(updated.password_hash, original_hash)
        self.assertTrue(verify_password("Original123", updated.password_hash))

    def test_rejects_an_email_already_used_by_another_user(self) -> None:
        with self.assertRaises(HTTPException) as context:
            update_user(
                self.user.id,
                UserUpdate(email="OTRO@example.com"),
                self.admin,
                self.db,
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(self.user.email, "usuario@example.com")


if __name__ == "__main__":
    unittest.main()
