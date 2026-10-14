from __future__ import annotations

import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import User
from backend.app.routers.app_settings import DEFAULT_BRAND, get_tenant_brand, update_tenant_brand
from backend.app.schemas import TenantBrandIn
from backend.app.security import hash_password

PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class TenantBrandTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine, future=True)()
        self.admin = User(email="admin@example.com", full_name="Admin", password_hash=hash_password("Admin12345"), role="admin")
        self.db.add(self.admin)
        self.db.commit()

    def test_default_brand_when_unset(self):
        brand = get_tenant_brand(db=self.db)
        self.assertEqual(brand.primary, DEFAULT_BRAND["primary"])
        self.assertEqual(brand.logoUrl, DEFAULT_BRAND["logoUrl"])

    def test_saves_and_reads_brand(self):
        update_tenant_brand(TenantBrandIn(name="Acme Telecom", logoUrl=PNG, primary="#0B6E74"), current_user=self.admin, db=self.db)
        brand = get_tenant_brand(db=self.db)
        self.assertEqual(brand.name, "Acme Telecom")
        self.assertEqual(brand.primary, "#0b6e74")
        self.assertEqual(brand.logoUrl, PNG)

    def test_rejects_svg_and_remote_logos(self):
        for logo in ("data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", "https://example.com/logo.png", "javascript:alert(1)"):
            with self.assertRaises(HTTPException):
                update_tenant_brand(TenantBrandIn(name="Acme", logoUrl=logo, primary="#185bc1"), current_user=self.admin, db=self.db)

    def test_rejects_oversized_logo(self):
        # The schema caps the field (422 at the API) before the router check.
        with self.assertRaises((HTTPException, ValidationError)):
            update_tenant_brand(TenantBrandIn(name="Acme", logoUrl="data:image/png;base64," + "A" * 399_990, primary="#185bc1"), current_user=self.admin, db=self.db)


if __name__ == "__main__":
    unittest.main()
