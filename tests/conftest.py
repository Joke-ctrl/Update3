"""
Pytest fixtures. Each test gets an isolated SQLite DB and a TestClient
wired to it via dependency override — no shared state between tests.
"""
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DATABASE_URL", "sqlite:///./_pytest.db")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

import app.api.routes.auth as auth_routes
from app.database.base import Base
from app.database.session import get_db
from app.main import app
from app.models import user, auth_tokens  # noqa: F401


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Registration-approval codes (Telegram/email to the admin) and login
    # OTPs (email to the user) are never actually sent in tests — capture
    # the plaintext codes at the send call instead of hitting real
    # Telegram/SMTP providers.
    captured = {"registration": [], "login_otp": []}

    def _capture_registration_code(email, code, expires_minutes):
        captured["registration"].append((email, code))
        return True

    def _capture_login_otp(email, code, expires_minutes):
        captured["login_otp"].append((email, code))
        return True

    monkeypatch.setattr(auth_routes, "send_registration_code_notification", _capture_registration_code)
    monkeypatch.setattr(auth_routes, "send_login_otp_notification", _capture_login_otp)

    with TestClient(app) as c:
        c.captured_codes = captured
        yield c
    app.dependency_overrides.clear()
