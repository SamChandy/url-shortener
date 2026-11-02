"""Synchronous SQLAlchemy 2.0 setup for Flask.

The engine is created lazily by `init_db()` (called from the app factory), so
tests can point the app at a different database.
"""
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, scoped_session, sessionmaker

# Deterministic constraint names make Alembic migrations predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# One session per thread/request; configured in init_db().
SessionLocal: scoped_session[Session] = scoped_session(sessionmaker(expire_on_commit=False))
_engine: Engine | None = None


def init_db(url: str) -> Engine:
    """Create the engine and bind the session factory to it."""
    global _engine
    kwargs = {} if url.startswith("sqlite") else {"pool_size": 10, "max_overflow": 20}
    _engine = create_engine(url, pool_pre_ping=True, **kwargs)
    SessionLocal.configure(bind=_engine)
    return _engine


def get_engine() -> Engine:
    """The engine created by init_db() (used by tests to create/drop tables)."""
    if _engine is None:
        raise RuntimeError("init_db() has not been called yet")
    return _engine


def get_db() -> Session:
    """Return the current request's session (the Flask equivalent of a DI dependency)."""
    return SessionLocal()


def close_db(_exc: BaseException | None = None) -> None:
    """Called on app-context teardown: release the session back to the pool."""
    SessionLocal.remove()
