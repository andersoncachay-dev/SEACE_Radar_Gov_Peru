from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.hist_scope import use_country
from backend.app.models import User
from backend.app.routers.historico import CommentIn, create_comment, delete_comment, list_comments
from backend.app.security import hash_password


class HistCommentTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, future=True)
        self.peru, self.chile = factory(), use_country(factory(), "chile")
        self.author = User(email="a@example.com", full_name="Ana Autora", password_hash=hash_password("Clave12345"))
        self.other = User(email="o@example.com", full_name="Otro", password_hash=hash_password("Clave12345"))
        self.admin = User(email="ad@example.com", full_name="Admin", password_hash=hash_password("Clave12345"), role="admin")
        self.peru.add_all([self.author, self.other, self.admin])
        self.peru.commit()

    def test_comments_are_per_record_and_country(self) -> None:
        key = "734-75-LP23|1|76.000.000-1"
        created = create_comment(CommentIn(kind="hist_contratacion", ref_key=key, body="  Llamar al jefe TI antes de noviembre "), user=self.author, db=self.chile)
        self.assertEqual(created["body"], "Llamar al jefe TI antes de noviembre")
        self.assertEqual(created["user_name"], "Ana Autora")
        listed = list_comments("hist_contratacion", key, user=self.other, db=self.chile)
        self.assertEqual([item["body"] for item in listed], ["Llamar al jefe TI antes de noviembre"])
        self.assertFalse(listed[0]["can_delete"])
        self.assertEqual(list_comments("hist_contratacion", key, user=self.author, db=self.peru), [])  # Perú does not see Chile notes
        self.assertEqual(list_comments("hist_contratacion", "otra-clave", user=self.author, db=self.chile), [])

    def test_only_author_or_admin_can_delete(self) -> None:
        created = create_comment(CommentIn(kind="hist_pac", ref_key="2026|1|7|1", body="Nota"), user=self.author, db=self.peru)
        with self.assertRaises(HTTPException):
            delete_comment(created["id"], user=self.other, db=self.peru)
        delete_comment(created["id"], user=self.admin, db=self.peru)
        self.assertEqual(list_comments("hist_pac", "2026|1|7|1", user=self.author, db=self.peru), [])

    def test_rejects_unknown_kind(self) -> None:
        with self.assertRaises(HTTPException):
            list_comments("opportunity", "1", user=self.author, db=self.peru)


if __name__ == "__main__":
    unittest.main()
