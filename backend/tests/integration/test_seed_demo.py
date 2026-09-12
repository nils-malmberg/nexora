from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from scripts import seed_demo


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_seed_is_idempotent(monkeypatch):
    session_factory = _session_factory()
    monkeypatch.setattr(seed_demo, "SessionLocal", session_factory)

    seed_demo.seed()
    seed_demo.seed()

    session = session_factory()
    try:
        assets = session.scalars(select(models.Asset)).all()
        providers = session.scalars(select(models.Provider)).all()
        feeds = session.scalars(select(models.ProviderFeed)).all()
        assert len(assets) == 1
        assert len(providers) == 3
        assert len(feeds) == 3
        assert {p.type for p in providers} == {"rss", "calendar_ics"}
    finally:
        session.close()
