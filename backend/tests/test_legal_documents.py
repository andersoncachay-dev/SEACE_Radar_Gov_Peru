from __future__ import annotations

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import User
from backend.app.routers.legal_documents import list_legal_documents, update_legal_document
from backend.app.schemas import LegalDocumentUpdate
from backend.app.security import hash_password


class LegalDocumentTests(unittest.TestCase):
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
        self.db.add(self.admin)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_lists_default_documents_without_stored_overrides(self) -> None:
        documents = list_legal_documents(self.db)

        self.assertEqual([item.key for item in documents], ["terms", "privacy", "confidentiality"])
        self.assertTrue(all(len(item.content) >= 100 for item in documents))

    def test_admin_update_is_returned_by_public_listing(self) -> None:
        replacement = "Última actualización: Julio 2026\n\n" + ("Contenido legal actualizado y validado. " * 5)
        updated = update_legal_document(
            "privacy",
            LegalDocumentUpdate(content=replacement),
            self.admin,
            self.db,
        )

        self.assertEqual(updated.content, replacement.strip())
        listed = {item.key: item for item in list_legal_documents(self.db)}
        self.assertEqual(listed["privacy"].content, replacement.strip())


if __name__ == "__main__":
    unittest.main()
