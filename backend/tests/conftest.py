"""
tests/conftest.py - Shared test fixtures, owned by Rajnish Maurya .

Tests run against a real PostgreSQL test database, rebuilt from
database/schema.sql + database/seed.sql before EVERY test, so tests never
depend on each other. After seeding, every login gets TEST_PASSWORD, and
ownership is read from the database instead of being hard-coded.

Set TEST_DATABASE_URL before running pytest (it is wiped on every run:
never point it at real data). Persons 2 and 3 reuse these fixtures.
"""
import os
from pathlib import Path

import psycopg
import pytest

def _test_url_from_env_file() -> str | None:
    """Fallback: read TEST_DATABASE_URL from backend/.env when it is not set in the terminal."""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("TEST_DATABASE_URL="):
                return line.split("=", 1)[1].strip() or None
    return None


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _test_url_from_env_file()
if not TEST_DATABASE_URL:
    raise RuntimeError("Set TEST_DATABASE_URL (in the terminal or in backend/.env) to a throwaway PostgreSQL database")

# Configure the app BEFORE it is imported.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256-signing"
os.environ["AI_ENABLED"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"

from fastapi.testclient import TestClient  # noqa: E402

from app.core.auth import hash_password  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.main import create_app  # noqa: E402


from types import SimpleNamespace  # noqa: E402
from app.core.auth import create_access_token  # noqa: E402


def _bearer(staff_code: str) -> dict:
    """Ready-made login header for a seeded staff member (used by Person 2's tests)."""
    return {"Authorization": f"Bearer {create_access_token(SimpleNamespace(staff_code=staff_code))}"}


COORD = _bearer("COORD-01")    # owns participants 1, 3, 4, 8, 11
COORD2 = _bearer("COORD-02")   # owns participants 2, 5, 6, 7, 9, 10, 12
REV = _bearer("REV-01")        # reviews participants 1, 2, 4, 5, 8, 12
REV2 = _bearer("REV-02")       # reviews participants 3, 6, 7, 9, 10, 11


DATABASE_DIR = Path(__file__).resolve().parents[2] / "database"
SCHEMA_SQL = (DATABASE_DIR / "schema.sql").read_text()
SEED_SQL = (DATABASE_DIR / "seed.sql").read_text()
PSYCOPG_URL = TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://")

TEST_PASSWORD = "Test-Password-123"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)     # hashed once; bcrypt is slow on purpose


def run_sql(sql: str, params=None):
    with psycopg.connect(PSYCOPG_URL, autocommit=True) as conn:
        cursor = conn.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


def query(sql: str, params=None) -> list[tuple]:
    return run_sql(sql, params)


@pytest.fixture(autouse=True)
def fresh_database():
    get_sessionmaker.cache_clear()
    run_sql(SCHEMA_SQL)
    run_sql(SEED_SQL)
    run_sql("UPDATE users SET password_hash = %s", (TEST_PASSWORD_HASH,))
    yield


@pytest.fixture(scope="session")
def app():
    get_settings.cache_clear()
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = get_sessionmaker()()
    yield session
    session.close()


# ---------- helpers that read the seed instead of hard-coding it ----------

def email_of(staff_code: str) -> str:
    return query("SELECT email FROM users WHERE staff_code = %s", (staff_code,))[0][0]


def staff_codes(role: str) -> list[str]:
    rows = query("SELECT s.staff_code FROM staff_members s JOIN users u USING (staff_code) "
                 "WHERE s.role = %s AND s.active ORDER BY s.staff_code", (role,))
    return [r[0] for r in rows]


def owned_by(staff_code: str) -> set[int]:
    column = "coordinator_code" if staff_code.startswith("COORD-") else "reviewer_code"
    return {r[0] for r in query(f"SELECT participant_id FROM participants WHERE {column} = %s", (staff_code,))}


def login(client: TestClient, staff_code: str, password: str = TEST_PASSWORD):
    return client.post("/api/auth/login", json={"email": email_of(staff_code), "password": password})


def auth_headers(client: TestClient, staff_code: str) -> dict:
    response = login(client, staff_code)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def coordinators() -> list[str]:
    codes = staff_codes("COORDINATOR")
    assert len(codes) >= 2, "Seed needs at least two coordinators with login accounts"
    return codes


@pytest.fixture
def reviewers() -> list[str]:
    codes = staff_codes("REVIEWER")
    assert len(codes) >= 2, "Seed needs at least two reviewers with login accounts"
    return codes


@pytest.fixture
def coord1(client, coordinators):
    return auth_headers(client, coordinators[0])


@pytest.fixture
def coord2(client, coordinators):
    return auth_headers(client, coordinators[1])


@pytest.fixture
def rev1(client, reviewers):
    return auth_headers(client, reviewers[0])


@pytest.fixture
def rev2(client, reviewers):
    return auth_headers(client, reviewers[1])


@pytest.fixture
def db_conn():
    """Plain psycopg connection for SQL checks (used by Person 2's tests)."""
    with psycopg.connect(PSYCOPG_URL, autocommit=True) as conn:
        yield conn