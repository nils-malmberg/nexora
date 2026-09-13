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
        assets = session.scalars(select(models.Instrument)).all()
        providers = session.scalars(select(models.Provider)).all()
        feeds = session.scalars(select(models.ProviderFeed)).all()
        assert len(assets) == 1
        assert assets[0].provider == "fixture" and assets[0].user_id is None
        assert len(providers) == 3
        assert len(feeds) == 3
        assert {p.type for p in providers} == {"rss", "calendar_ics"}
        bars = session.scalars(select(models.OhlcBar).where(models.OhlcBar.instrument_id == assets[0].id)).all()
        assert 480 <= len(bars) <= 530  # ~2 years of weekdays, seeded once (idempotent)
        assert all(b.source == "fixture" and b.low <= b.close <= b.high for b in bars)
    finally:
        session.close()
