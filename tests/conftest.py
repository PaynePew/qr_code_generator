"""
Test configuration.

DB-touching tests run on a per-session Postgres testcontainer.
Schema is built by `alembic upgrade head` so migrations are exercised.
Each test gets per-test transaction-rollback isolation via a savepoint.

Pure-logic tests (no db_session / client fixture) touch no DB and stay instant.
"""

import os
import subprocess
import sys
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SECRET", "test-secret-value")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from backend.auth import get_current_user  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import User  # noqa: E402
from backend.router import get_db  # noqa: E402

# ---------------------------------------------------------------------------
# Session-scoped Postgres testcontainer
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def pg_container():
    """Start a Postgres testcontainer once for the whole test session."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_engine(pg_container):
    """
    Create a SQLAlchemy engine connected to the testcontainer Postgres.
    Run alembic upgrade head once to build the schema from migrations.
    """
    url = pg_container.get_connection_url()
    # testcontainers returns a psycopg2+driver URL; ensure it is the
    # standard postgresql:// scheme that SQLAlchemy understands.
    url = url.replace("postgresql+psycopg2://", "postgresql://", 1)

    # Build schema via Alembic so migrations are exercised.
    env = {**os.environ, "DATABASE_URL": url}
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
    )

    engine = create_engine(url)
    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Per-test transaction-rollback isolation
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(db_engine):
    """
    Open a connection, begin an outer transaction, and expose a Session that
    joins it via SAVEPOINTs (``join_transaction_mode="create_savepoint"``).
    Application-code ``session.commit()`` releases and restarts the savepoint
    instead of committing; the outer ``transaction.rollback()`` in teardown
    discards everything, leaving the database pristine for the next test
    without rebuilding the schema.
    """
    connection = db_engine.connect()
    transaction = connection.begin()

    Session = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient wired to the per-test transactional db_session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Authenticated test helpers (ADR 0009: login-to-create, owner stamping)
# ---------------------------------------------------------------------------

_user_seq = 0


def make_user(db_session, *, email: str | None = None, is_demo: bool = False) -> User:
    """Persist and return a User. Committed so a Link FK to users.id resolves.

    The commit lands inside the test's savepoint-wrapped session, so it is
    visible for the FK check yet still rolled back at teardown.
    """
    global _user_seq
    _user_seq += 1
    now = datetime(2026, 6, 3, 12, 0, 0)
    user = User(
        google_sub=f"sub-test-{_user_seq}",
        email=email or f"user{_user_seq}@example.com",
        name=f"Test User {_user_seq}",
        picture=None,
        created_at=now,
        last_login_at=now,
        is_demo=is_demo,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def owner(db_session) -> User:
    """A persisted User who owns Links created through the auth_client fixture."""
    return make_user(db_session)


@pytest.fixture
def auth_client(db_session, owner):
    """TestClient authenticated as the ``owner`` fixture.

    Overrides ``get_current_user`` so router endpoints see a logged-in User
    without exercising the full Google flow (covered in test_auth_router.py).
    Request the ``owner`` fixture alongside this one to assert on the authed User.
    """

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
