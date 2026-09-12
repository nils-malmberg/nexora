from __future__ import annotations


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def test_export_includes_only_my_own_data(registered_user):
    client, csrf, _user_id = registered_user
    portfolio = client.post("/api/v1/portfolios", json={"name": "P"}, headers=_headers(csrf)).json()

    export = client.get("/api/v1/me/export")
    assert export.status_code == 200
    body = export.json()
    assert body["user"]["email"] == "alice@example.com"
    assert [p["id"] for p in body["portfolios"]] == [portfolio["id"]]


def test_delete_account_requires_correct_password(registered_user):
    client, csrf, _user_id = registered_user
    response = client.request(
        "DELETE", "/api/v1/me", json={"password": "totally wrong password"}, headers=_headers(csrf)
    )
    assert response.status_code == 401


def test_delete_account_cascades_and_invalidates_session(registered_user):
    client, csrf, _user_id = registered_user
    client.post("/api/v1/portfolios", json={"name": "P"}, headers=_headers(csrf))

    response = client.request(
        "DELETE", "/api/v1/me", json={"password": "correct horse battery staple"}, headers=_headers(csrf)
    )
    assert response.status_code == 204

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401
