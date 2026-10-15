from __future__ import annotations

import unittest

from fastapi import HTTPException

from backend.app.models import User
from backend.app.routers.favorites import FavoriteIn, delete_favorite, get_favorites, put_favorite
from backend.app.security import hash_password
from backend.app.services.favorite_service import favorite_keys
from backend.app.services.historico import query_service
from backend.tests.test_historico_import import HistoricoFixture


class FavoriteTests(HistoricoFixture):
    def setUp(self) -> None:
        super().setUp()
        self.user = User(email="u@example.com", full_name="Usuario", password_hash=hash_password("Clave12345"))
        self.other = User(email="o@example.com", full_name="Otro", password_hash=hash_password("Clave12345"))
        self.db.add_all([self.user, self.other])
        self.db.commit()

    def _star(self, kind: str, ref_key: str, user: User | None = None) -> None:
        put_favorite(FavoriteIn(kind=kind, ref_key=ref_key, label="x"), current_user=user or self.user, db=self.db)

    def test_add_is_idempotent_per_user_and_remove_works(self) -> None:
        self._star("opportunity", "42")
        self._star("opportunity", "42")
        self._star("opportunity", "42", user=self.other)
        self.assertEqual([item.ref_key for item in get_favorites(current_user=self.user, db=self.db)], ["42"])
        delete_favorite("opportunity", "42", current_user=self.user, db=self.db)
        self.assertEqual(get_favorites(current_user=self.user, db=self.db), [])
        self.assertEqual(len(get_favorites(current_user=self.other, db=self.db)), 1)

    def test_rejects_unknown_kind(self) -> None:
        with self.assertRaises(HTTPException):
            self._star("hist_unknown", "1")

    def test_favorites_only_filters_every_list_and_survives_reimport(self) -> None:
        self._import(self._fixture_files())
        filters = query_service.Filters()
        contracting = query_service.list_contractings(self.db, filters)["items"][0]
        expiring = query_service.list_expiring(self.db, filters)["items"][0]
        recurring = query_service.list_recurring(self.db, filters)["items"][0]
        pac = query_service.list_pac(self.db, filters)["items"][0]
        for kind, row in (("hist_contratacion", contracting), ("hist_contratacion", expiring), ("hist_recurrente", recurring), ("hist_pac", pac)):
            self._star(kind, row["fav_key"])

        # Re-importing rebuilds the Histórico rows (new ids); keys must still match.
        self._import(self._fixture_files())
        only = query_service.Filters(favorite_keys=favorite_keys(self.db, self.user.id))
        self.assertIn(contracting["fav_key"], [row["fav_key"] for row in query_service.list_contractings(self.db, only)["items"]])
        self.assertEqual([row["fav_key"] for row in query_service.list_expiring(self.db, only)["items"]], [expiring["fav_key"]])
        self.assertEqual([row["fav_key"] for row in query_service.list_recurring(self.db, only)["items"]], [recurring["fav_key"]])
        self.assertEqual([row["fav_key"] for row in query_service.list_pac(self.db, only)["items"]], [pac["fav_key"]])

        none = query_service.Filters(favorite_keys=favorite_keys(self.db, self.other.id))
        self.assertEqual(query_service.list_contractings(self.db, none)["total"], 0)
        self.assertEqual(query_service.list_pac(self.db, none)["total"], 0)

    def test_lists_carry_latest_comment(self) -> None:
        from backend.app.routers.historico import CommentIn, create_comment

        self._import(self._fixture_files())
        row = query_service.list_expiring(self.db, query_service.Filters())["items"][0]
        self.assertIsNone(row["comment"])
        create_comment(CommentIn(kind="hist_contratacion", ref_key=row["fav_key"], body="Primera"), user=self.user, db=self.db)
        create_comment(CommentIn(kind="hist_contratacion", ref_key=row["fav_key"], body="Llamar en noviembre"), user=self.other, db=self.db)
        listed = next(item for item in query_service.list_expiring(self.db, query_service.Filters())["items"] if item["fav_key"] == row["fav_key"])
        self.assertEqual((listed["comment"]["body"], listed["comment"]["user_name"], listed["comment_count"]), ("Llamar en noviembre", "Otro", 2))
        same_award = next(item for item in query_service.list_contractings(self.db, query_service.Filters())["items"] if item["fav_key"] == row["fav_key"])
        self.assertEqual(same_award["comment_count"], 2)  # Por vencer and Historial share the note
        self.assertIn(("comment_text", "Último comentario"), query_service.EXPORT_COLUMNS["vencimientos"])


if __name__ == "__main__":
    unittest.main()
