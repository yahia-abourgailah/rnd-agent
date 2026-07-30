from collections.abc import Iterator

from sqlalchemy.orm import Session

from db.engine import SessionLocal


def get_session() -> Iterator[Session]:
    """One DB session per request, always closed afterwards.

    Read endpoints don't commit — they just borrow a pooled connection via
    SessionLocal (see db/engine.py) and return it when the request ends.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
