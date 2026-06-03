import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./qr_codes.db")

_is_sqlite = DATABASE_URL.startswith("sqlite")

# SQLite needs check_same_thread=False; PostgreSQL must NOT receive that arg.
_connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)


if _is_sqlite:
    # WAL mode improves concurrent read performance for SQLite only.
    @event.listens_for(engine, "connect")
    def set_wal_mode(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
