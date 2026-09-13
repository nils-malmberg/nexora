"""Admin console, educational content, profile/sessions and export."""

from __future__ import annotations

from app.education_content import ARTICLES, CATEGORIES
from tests.conftest import auth_headers, register


def _headers(csrf):
    return auth_headers(csrf)


# --- admin -----------------------------------------------------------------------


def test_first_user_is_admin_and_others_are_not(registered_user):
    client, csrf, _ = registered_user
    assert client.get("/api/v1/auth/me").json()["user"]["is_admin"] is True
    bob_csrf, _ = register(client, email="bob@example.com")
    assert client.get("/api/v1/auth/me").json()["user"]["is_admin"] is False
    assert client.get("/api/v1/admin/market-providers").status_code == 403


def test_admin_market_providers_listing_and_toggle(registered_user):
    client, csrf, _ = registered_user
    providers = client.get("/api/v1/admin/market-providers").json()
    names = {p["name"] for p in providers}
    assert "fixture" in names  # equity + fx providers in the test config
    for p in providers:
        assert "env_var" in p and "secret" not in str(p).lower()  # never a credential value

    off = client.post(
        "/api/v1/admin/market-providers/fixture/enabled",
        json={"enabled": False, "reason": "maintenance"},
        headers=_headers(csrf),
    )
    assert off.status_code == 200 and off.json()["enabled"] is False and off.json()["disabled_reason"] == "maintenance"
    status = client.get("/api/v1/providers/status").json()
    equity = next(m for m in status["market"] if m["role"] == "equity")
    assert equity["enabled"] is False and equity["healthy"] is False
    on = client.post("/api/v1/admin/market-providers/fixture/enabled", json={"enabled": True}, headers=_headers(csrf))
    assert on.json()["enabled"] is True

    audit = client.get("/api/v1/admin/audit").json()
    actions = [a["action"] for a in audit]
    assert "market_provider.disable" in actions and "market_provider.enable" in actions
    assert (
        client.post(
            "/api/v1/admin/market-providers/nope/enabled", json={"enabled": True}, headers=_headers(csrf)
        ).status_code
        == 404
    )


# --- education ---------------------------------------------------------------------


def test_education_is_public_searchable_and_complete(client):
    listed = client.get("/api/v1/education").json()
    assert len(listed) == len(ARTICLES) >= 15
    assert {a["category"] for a in listed} <= set(CATEGORIES)
    categories = client.get("/api/v1/education/categories").json()
    assert {c["key"] for c in categories} == set(CATEGORIES)

    hits = client.get("/api/v1/education", params={"q": "markowitz"}).json()
    assert any(a["slug"] == "markowitz" for a in hits)
    only_theory = client.get("/api/v1/education", params={"category": "theorie"}).json()
    assert all(a["category"] == "theorie" for a in only_theory) and only_theory

    article = client.get("/api/v1/education/twr-mwr").json()
    assert article["sections"] and article["what_it_measures"] and article["method"] and article["limitations"]
    assert "valorisation" in article["related"]
    assert client.get("/api/v1/education/nope").status_code == 404


def test_education_never_prescribes():
    forbidden = ("achetez", "vendez", "vous devriez")
    for slug, article in ARTICLES.items():
        text = " ".join(
            [
                article["title"],
                article["summary"],
                article["what_it_measures"],
                article["method"],
                article["limitations"],
            ]
            + [s["heading"] + " " + s["body"] for s in article["sections"]]
        ).lower()
        for word in forbidden:
            assert word not in text, f"{slug} contains '{word}'"
        for related in article["related"]:
            assert related in ARTICLES, f"{slug} links to unknown article {related}"


# --- me ------------------------------------------------------------------------------


def test_profile_update_sessions_and_export(registered_user):
    client, csrf, user_id = registered_user
    updated = client.patch(
        "/api/v1/me",
        json={"display_name": "Alice", "reference_currency": "usd", "display_timezone": "Europe/Paris"},
        headers=_headers(csrf),
    )
    assert updated.status_code == 200 and updated.json()["reference_currency"] == "USD"
    assert (
        client.patch("/api/v1/me", json={"display_timezone": "Mars/Olympus"}, headers=_headers(csrf)).status_code == 422
    )

    # A second login opens a second session; revoke-others keeps only the newest.
    client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "correct horse battery staple"})
    me = client.get("/api/v1/auth/me").json()
    sessions = client.get("/api/v1/me/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    assert client.post("/api/v1/me/sessions/revoke-others", headers=_headers(me["csrf_token"])).status_code == 204
    assert len(client.get("/api/v1/me/sessions").json()) == 1

    export = client.get("/api/v1/me/export").json()
    assert export["user"]["id"] == user_id
    assert set(export) >= {
        "portfolios",
        "instruments",
        "transactions",
        "watchlist_instrument_ids",
        "import_jobs",
        "prediction_experiments",
    }
