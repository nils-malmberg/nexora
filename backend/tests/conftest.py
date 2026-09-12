from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401 - registers tables on Base.metadata
from app.db import Base

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def make_asset(db_session):
    def _make(symbol: str = "DEMO", name: str = "Demo SA", market: str = "XPAR", currency: str = "EUR") -> models.Asset:
        asset = models.Asset(symbol=symbol, name=name, market=market, currency=currency)
        db_session.add(asset)
        db_session.commit()
        return asset

    return _make


@pytest.fixture()
def make_provider(db_session):
    def _make(name: str, type: str, config: dict | None = None, enabled: bool = True) -> models.Provider:
        provider = models.Provider(name=name, type=type, config=config or {}, enabled=enabled)
        db_session.add(provider)
        db_session.commit()
        return provider

    return _make


def read_fixture_bytes(*parts: str) -> bytes:
    return (FIXTURES_DIR.joinpath(*parts)).read_bytes()


def read_fixture_text(*parts: str) -> str:
    return (FIXTURES_DIR.joinpath(*parts)).read_text(encoding="utf-8")
