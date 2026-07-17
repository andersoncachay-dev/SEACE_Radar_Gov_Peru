from __future__ import annotations

import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import User
from backend.app.routers.opportunity_view_states import get_view_state, save_view_state
from backend.app.schemas import OpportunityViewStateUpdate


class OpportunityViewStateTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.user = User(email="uno@example.com", full_name="Usuario Uno", first_name="Usuario", last_name="Uno", access_profile="both", password_hash="test")
        self.other = User(email="dos@example.com", full_name="Usuario Dos", first_name="Usuario", last_name="Dos", access_profile="both", password_hash="test")
        self.db.add_all([self.user, self.other])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_state_is_upserted_and_isolated_by_user(self) -> None:
        first = save_view_state("ocds.Peru", OpportunityViewStateUpdate(state={"runIds": [1, 2], "keywords": ["internet"]}), self.user, self.db)
        self.assertEqual(first.state["runIds"], [1, 2])

        updated = save_view_state("ocds.Peru", OpportunityViewStateUpdate(state={"runIds": [3], "keywords": ["satelital"]}), self.user, self.db)
        self.assertEqual(updated.state["runIds"], [3])
        self.assertEqual(get_view_state("ocds.Peru", self.user, self.db).state["keywords"], ["satelital"])

        with self.assertRaises(HTTPException) as missing:
            get_view_state("ocds.Peru", self.other, self.db)
        self.assertEqual(missing.exception.status_code, 404)

    def test_invalid_scope_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as invalid:
            save_view_state("admin.global", OpportunityViewStateUpdate(state={}), self.user, self.db)
        self.assertEqual(invalid.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
