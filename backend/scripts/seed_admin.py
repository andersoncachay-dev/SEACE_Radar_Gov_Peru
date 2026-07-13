from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import select

from backend.app.database import SessionLocal
from backend.app.models import User
from backend.app.security import hash_password


def main() -> None:
    email = os.getenv("ADMIN_EMAIL", "admin@seace-radar.local")
    password = os.getenv("ADMIN_PASSWORD", "Admin12345")
    full_name = os.getenv("ADMIN_FULL_NAME", "Administrador SEACE Radar")
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user:
            user.full_name = full_name
            user.role = "admin"
            user.is_active = True
            user.password_hash = hash_password(password)
            action = "updated"
        else:
            db.add(User(email=email, full_name=full_name, role="admin", password_hash=hash_password(password)))
            action = "created"
        db.commit()
        print(f"Admin user {action}: {email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
