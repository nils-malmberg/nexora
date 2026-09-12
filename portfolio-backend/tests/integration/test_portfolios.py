from __future__ import annotations


def _register(client, email: str) -> str:
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "correct horse battery staple"})
    assert response.status_code == 201, response.text
    return response.json()["csrf_token"]


def test_create_and_list_portfolio(registered_user):
    client, csrf_token, _user_id = registered_user
    create = client.post("/api/v1/portfolios", json={"name": "Compte principal"}, headers={"X-CSRF-Token": csrf_token})
    assert create.status_code == 201, create.text
    assert create.json()["base_currency"] == "EUR"

    listing = client.get("/api/v1/portfolios")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_update_portfolio_name(registered_user):
    client, csrf_token, _user_id = registered_user
    create = client.post("/api/v1/portfolios", json={"name": "Old name"}, headers={"X-CSRF-Token": csrf_token})
    portfolio_id = create.json()["id"]

    update = client.patch(
        f"/api/v1/portfolios/{portfolio_id}", json={"name": "New name"}, headers={"X-CSRF-Token": csrf_token}
    )
    assert update.status_code == 200
    assert update.json()["name"] == "New name"


def test_delete_portfolio(registered_user):
    client, csrf_token, _user_id = registered_user
    create = client.post("/api/v1/portfolios", json={"name": "To delete"}, headers={"X-CSRF-Token": csrf_token})
    portfolio_id = create.json()["id"]

    delete = client.delete(f"/api/v1/portfolios/{portfolio_id}", headers={"X-CSRF-Token": csrf_token})
    assert delete.status_code == 204

    get_after = client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert get_after.status_code == 404


def test_portfolio_not_found_for_unknown_id(registered_user):
    client, _csrf_token, _user_id = registered_user
    response = client.get("/api/v1/portfolios/does-not-exist")
    assert response.status_code == 404


def test_second_user_cannot_read_first_users_portfolio(client):
    """specs/SECURITY.md IDOR control: a portfolio belonging to another
    tenant must be indistinguishable from one that doesn't exist (404, not
    403 - a 403 would confirm the id exists to an attacker probing ids)."""
    csrf_a = _register(client, "owner@example.com")
    create = client.post("/api/v1/portfolios", json={"name": "Owner's portfolio"}, headers={"X-CSRF-Token": csrf_a})
    portfolio_id = create.json()["id"]

    client.cookies.clear()
    _register(client, "intruder@example.com")

    response = client.get(f"/api/v1/portfolios/{portfolio_id}")
    assert response.status_code == 404


def test_second_user_cannot_delete_first_users_portfolio(client):
    csrf_a = _register(client, "owner2@example.com")
    create = client.post("/api/v1/portfolios", json={"name": "Owner's portfolio"}, headers={"X-CSRF-Token": csrf_a})
    portfolio_id = create.json()["id"]

    client.cookies.clear()
    csrf_b = _register(client, "intruder2@example.com")

    response = client.delete(f"/api/v1/portfolios/{portfolio_id}", headers={"X-CSRF-Token": csrf_b})
    assert response.status_code == 404
