"""Test configuration.

DB-touching tests run against a PostgreSQL testcontainer whose schema is built
by ``alembic upgrade head``.  Per-test isolation is achieved through transaction
rollback, so each test starts from a clean state without re-running migrations.

Pure-logic tests (token_generator, analytics aggregation, link_state, etc.)
touch no database and remain instant.

Fixtures
--------
pg_engine        — session-scoped; starts the Postgres container and applies
                   Alembic migrations once per test session.
db_session       — function-scoped; wraps each test in a savepoint that is
                   rolled back at teardown, giving per-test isolation.
client           — function-scoped; FastAPI TestClient wired to db_session.
"""

import os

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

os.environ.setdefault("SECRET", "test-secret-value")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from backend.main import app  # noqa: E402  — env vars must be set first
from backend.router import get_db  # noqa: E402


# ---------------------------------------------------------------------------
# PostgreSQL testcontainer — shared across the whole test session
# ---------------------------------------------------------------------------

_POSTGRES_IMAGE = "postgres:16-alpine"


@pytest.fixture(scope="session")
def pg_container():
    """Start a throwaway Postgres container for the test session."""
    with PostgresContainer(image=_POSTGRES_IMAGE) as container:
        yield container


@pytest.fixture(scope="session")
def pg_engine(pg_container):
    """Create a SQLAlchemy engine against the container and run Alembic."""
    url = pg_container.get_connection_url()

    # SQLAlchemy requires the psycopg2 scheme for synchronous use.
    url = url.replace("postgresql+psycopg2://", "postgresql://", 1)

    engine = create_engine(url)

    # Build schema via Alembic (tests the migrations themselves).
    ini_path = os.path.join(
        os.path.dirname(__file__), "..", "alembic.ini"
    )
    alembic_cfg = AlembicConfig(ini_path)
    alembic_cfg.set_main_option("sqlalchemy.url", url)
    # Prevent Alembic's fileConfig from replacing pytest's log-capture handlers,
    # which would break caplog in tests that run after migration setup.
    alembic_cfg.attributes["no_configure_logging"] = True
    alembic_command.upgrade(alembic_cfg, "head")

    yield engine
    engine.dispose()


# ---------------------------------------------------------------------------
# Per-test isolation via savepoint rollback
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine(pg_engine):
    """Alias so existing tests that reference db_engine still work."""
    return pg_engine


@pytest.fixture
def db_session(pg_engine):
    """Open a connection, begin a transaction, expose it as a Session.

    A SAVEPOINT is established before each test and rolled back afterwards,
    so every test starts from a pristine (but migration-built) schema.
    """
    connection = pg_engine.connect()
    transaction = connection.begin()

    SessionFactory = sessionmaker(bind=connection)
    session = SessionFactory()

    # Patch session.commit to flush-only so tests don't actually commit.
    session.commit = session.flush  # type: ignore[method-assign]

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient whose DB is the per-test rolled-back session."""

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()
