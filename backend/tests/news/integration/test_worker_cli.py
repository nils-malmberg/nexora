import httpx
import respx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.db import Base
from app.worker import cli
from tests.conftest import read_fixture_bytes

RSS_URL = "https://example-issuer.test/rss.xml"


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


@respx.mock
def test_sync_one_runs_named_provider(monkeypatch, capsys):
    session_factory = _session_factory()
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    session = session_factory()
    provider = models.Provider(name="issuer-rss", type="rss")
    session.add(provider)
    session.flush()
    session.add(models.ProviderFeed(provider_id=provider.id, url=RSS_URL))
    session.commit()

    respx.get(RSS_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))

    exit_code = cli.sync_one("issuer-rss")
    assert exit_code == 0
    assert "status=success" in capsys.readouterr().out


def test_sync_one_unknown_provider_returns_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "SessionLocal", _session_factory())
    exit_code = cli.sync_one("does-not-exist")
    assert exit_code == 1
    assert "no provider named" in capsys.readouterr().err


@respx.mock
def test_sync_all_runs_every_enabled_provider(monkeypatch, capsys):
    session_factory = _session_factory()
    monkeypatch.setattr(cli, "SessionLocal", session_factory)
    session = session_factory()
    enabled = models.Provider(name="issuer-rss", type="rss", enabled=True)
    disabled = models.Provider(name="disabled-rss", type="rss", enabled=False)
    session.add_all([enabled, disabled])
    session.flush()
    session.add(models.ProviderFeed(provider_id=enabled.id, url=RSS_URL))
    session.commit()

    respx.get(RSS_URL).mock(return_value=httpx.Response(200, content=read_fixture_bytes("rss", "valid_feed.xml")))

    exit_code = cli.sync_all()
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "issuer-rss" in out
    assert "disabled-rss" not in out
