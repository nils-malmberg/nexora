from __future__ import annotations


def _headers(csrf_token: str) -> dict:
    return {"X-CSRF-Token": csrf_token}


def _make_portfolio(client, csrf_token: str) -> str:
    response = client.post("/api/v1/portfolios", json={"name": "P"}, headers=_headers(csrf_token))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(client, portfolio_id: str, csrf_token: str, csv_text: str, filename: str = "import.csv"):
    return client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        files={"file": (filename, csv_text.encode("utf-8"), "text/csv")},
        headers=_headers(csrf_token),
    )


def test_upload_detects_headers_and_suggests_mapping(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = "date,type,symbol,asset_class,quantity,unit_price,currency,fees,account,external_id\n"
    response = _upload(client, portfolio_id, csrf, csv_text)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["suggested_mapping"]["date"] == "date"
    assert body["suggested_mapping"]["symbol"] == "symbol"
    assert body["total_rows"] == 0


def test_upload_requires_csrf(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports",
        files={"file": ("x.csv", b"date,type\n", "text/csv")},
    )
    assert response.status_code == 403


def test_upload_rejects_too_many_rows(registered_user, monkeypatch):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    from app.config import settings

    monkeypatch.setattr(settings, "csv_import_max_rows", 2)
    csv_text = "date,type,quantity,unit_price,currency\n" + "\n".join(
        f"2026-01-0{i},depot,1,100,EUR" for i in range(1, 5)
    )
    response = _upload(client, portfolio_id, csrf, csv_text)
    assert response.status_code == 413


def test_upload_rejects_empty_file(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    response = _upload(client, portfolio_id, csrf, "")
    assert response.status_code == 422


def test_full_happy_path_upload_preview_commit(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = (
        "date,type,symbol,asset_class,quantity,unit_price,currency,fees,account,external_id\n"
        "2026-01-01,depot,,,1,5000,EUR,0,,dep-1\n"
        "2026-01-02,achat,AAA,action,10,100,EUR,5,,buy-1\n"
        "2026-01-03,dividende,AAA,,1,20,EUR,0,,div-1\n"
    )
    upload = _upload(client, portfolio_id, csrf, csv_text)
    assert upload.status_code == 201, upload.text
    job_id = upload.json()["id"]

    preview = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["status"] == "previewed"
    assert preview_body["valid_count"] == 3
    assert preview_body["error_count"] == 0
    assert all(row["status"] == "valid" for row in preview_body["rows"])
    # New instrument flagged, never silent.
    aaa_rows = [r for r in preview_body["rows"] if r["canonical"]["symbol"] == "AAA"]
    assert any("sera créé automatiquement" in m for r in aaa_rows for m in r["messages"])

    commit = client.post(f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/commit", headers=_headers(csrf))
    assert commit.status_code == 200, commit.text
    commit_body = commit.json()
    assert commit_body["status"] == "committed"
    assert commit_body["inserted_count"] == 3
    assert all(row["status"] == "inserted" for row in commit_body["rows"])

    positions = client.get(f"/api/v1/portfolios/{portfolio_id}/positions").json()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "AAA"
    assert positions[0]["quantity"] == "10.00000000"

    valuation = client.get(f"/api/v1/portfolios/{portfolio_id}/valuation").json()
    # 5000 deposit - 1000 (buy) - 5 (buy fees) + 20 (dividend) = 4015
    assert valuation["cash"] == "4015.000000"

    transactions = client.get(f"/api/v1/portfolios/{portfolio_id}/transactions").json()["items"]
    assert len(transactions) == 3


def test_oversell_within_same_batch_reported_as_error(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = (
        "date,type,symbol,asset_class,quantity,unit_price,currency,fees,account,external_id\n"
        "2026-01-01,achat,AAA,action,5,100,EUR,0,,buy-1\n"
        "2026-01-02,vente,AAA,,10,100,EUR,0,,sell-1\n"
    )
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]

    preview = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    body = preview.json()
    assert body["valid_count"] == 1
    assert body["error_count"] == 1
    sell_row = next(r for r in body["rows"] if r["canonical"]["type"] == "vente")
    assert sell_row["status"] == "error"
    assert "exceeds available position" in sell_row["messages"][0]


def test_duplicate_external_id_marked_duplicate_not_error(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    # First, a real transaction with external_id "dup-1".
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "type": "depot",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "100",
            "currency": "EUR",
            "external_id": "dup-1",
        },
        headers=_headers(csrf),
    )
    csv_text = "date,type,quantity,unit_price,currency,external_id\n" "2026-01-05,depot,1,200,EUR,dup-1\n"
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]
    preview = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    body = preview.json()
    assert body["duplicate_count"] == 1
    assert body["error_count"] == 0
    assert body["rows"][0]["status"] == "duplicate"


def test_duplicate_via_fingerprint_without_external_id(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "type": "depot",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "300",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    csv_text = "date,type,quantity,unit_price,currency\n2026-01-01,depot,1,300,EUR\n"
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]
    preview = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    body = preview.json()
    assert body["duplicate_count"] == 1


def test_transfert_row_rejected_explicitly(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = "date,type,quantity,unit_price,currency\n2026-01-01,transfert,1,100,EUR\n"
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]
    preview = client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    body = preview.json()
    assert body["error_count"] == 1
    assert body["rows"][0]["status"] == "error"


def test_valorisation_privee_row_creates_valuation(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    instrument = client.post(
        "/api/v1/instruments",
        json={"symbol": "PRIVCSV", "name": "Startup", "asset_class": "actif_prive", "currency": "EUR"},
        headers=_headers(csrf),
    ).json()
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/transactions",
        json={
            "instrument_id": instrument["id"],
            "type": "achat",
            "trade_date": "2026-01-01T00:00:00Z",
            "quantity": "1",
            "unit_price": "10000",
            "currency": "EUR",
        },
        headers=_headers(csrf),
    )
    csv_text = "date,type,symbol,quantity,unit_price,currency\n" "2026-06-01,valorisation_privee,PRIVCSV,1,15000,EUR\n"
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    commit = client.post(f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/commit", headers=_headers(csrf))
    assert commit.status_code == 200, commit.text

    valuations = client.get(f"/api/v1/instruments/{instrument['id']}/private-valuations").json()
    assert len(valuations) == 1
    assert valuations[0]["method"] == "Import CSV"


def test_commit_twice_conflicts(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = "date,type,quantity,unit_price,currency\n2026-01-01,depot,1,100,EUR\n"
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    first = client.post(f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/commit", headers=_headers(csrf))
    assert first.status_code == 200
    second = client.post(f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/commit", headers=_headers(csrf))
    assert second.status_code == 409


def test_raw_rows_cleared_after_commit_but_report_kept(registered_user, db_session):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = "date,type,quantity,unit_price,currency\n2026-01-01,depot,1,100,EUR\n"
    upload = _upload(client, portfolio_id, csrf, csv_text)
    job_id = upload.json()["id"]
    client.post(
        f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/preview",
        json={"column_mapping": upload.json()["suggested_mapping"]},
        headers=_headers(csrf),
    )
    client.post(f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}/commit", headers=_headers(csrf))

    from app.models import ImportJob

    job = db_session.get(ImportJob, job_id)
    assert job.raw_rows is None
    assert job.row_results is not None

    report = client.get(f"/api/v1/portfolios/{portfolio_id}/imports/{job_id}")
    assert report.status_code == 200
    assert report.json()["rows"][0]["status"] == "inserted"


def test_import_job_not_owned_by_caller_is_404(registered_user):
    owner_client, owner_csrf, _owner_id = registered_user
    portfolio_id = _make_portfolio(owner_client, owner_csrf)
    csv_text = "date,type,quantity,unit_price,currency\n2026-01-01,depot,1,100,EUR\n"
    upload = _upload(owner_client, portfolio_id, owner_csrf, csv_text)
    job_id = upload.json()["id"]

    owner_client.cookies.clear()
    register = owner_client.post(
        "/api/v1/auth/register",
        json={"email": "intruder-import@example.com", "password": "correct horse battery staple"},
    )
    intruder_csrf = register.json()["csrf_token"]
    intruder_portfolio_id = _make_portfolio(owner_client, intruder_csrf)

    response = owner_client.get(f"/api/v1/portfolios/{intruder_portfolio_id}/imports/{job_id}")
    assert response.status_code == 404


def test_list_imports_returns_summaries(registered_user):
    client, csrf, _user_id = registered_user
    portfolio_id = _make_portfolio(client, csrf)
    csv_text = "date,type,quantity,unit_price,currency\n2026-01-01,depot,1,100,EUR\n"
    _upload(client, portfolio_id, csrf, csv_text)
    _upload(client, portfolio_id, csrf, csv_text)

    response = client.get(f"/api/v1/portfolios/{portfolio_id}/imports")
    assert response.status_code == 200
    assert len(response.json()) == 2
