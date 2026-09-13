from __future__ import annotations


def test_register_then_me(client):
    response = client.post(
        "/api/v1/auth/register", json={"email": "bob@example.com", "password": "correct horse battery staple"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == "bob@example.com"
    assert "csrf_token" in body

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    me_body = me.json()
    assert me_body["user"]["email"] == "bob@example.com"
    assert me_body["csrf_token"] == body["csrf_token"]


def test_register_duplicate_email_conflicts(client):
    payload = {"email": "dup@example.com", "password": "correct horse battery staple"}
    first = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    second = client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post(
        "/api/v1/auth/register", json={"email": "carol@example.com", "password": "correct horse battery staple"}
    )
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": "carol@example.com", "password": "wrong password"})
    assert response.status_code == 401


def test_login_rate_limited_after_repeated_failures(client):
    client.post("/api/v1/auth/register", json={"email": "dave@example.com", "password": "correct horse battery staple"})
    client.cookies.clear()
    for _ in range(10):
        client.post("/api/v1/auth/login", json={"email": "dave@example.com", "password": "wrong password"})
    response = client.post("/api/v1/auth/login", json={"email": "dave@example.com", "password": "wrong password"})
    assert response.status_code == 429


def test_me_requires_authentication(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_logout_revokes_session(registered_user):
    client, csrf_token, _user_id = registered_user
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    assert logout.status_code == 204

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 401


def test_mutating_request_without_csrf_token_rejected(registered_user):
    client, _csrf_token, _user_id = registered_user
    response = client.post("/api/v1/portfolios", json={"name": "Compte principal"})
    assert response.status_code == 403


def test_mutating_request_with_wrong_csrf_token_rejected(registered_user):
    client, _csrf_token, _user_id = registered_user
    response = client.post(
        "/api/v1/portfolios", json={"name": "Compte principal"}, headers={"X-CSRF-Token": "not-the-real-token"}
    )
    assert response.status_code == 403
