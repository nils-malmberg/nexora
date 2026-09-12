from app.pipeline.assets import resolve_asset


def test_resolve_asset_none_hint_is_unmatched(db_session):
    resolution = resolve_asset(db_session, None, 0.5)
    assert resolution.asset_id is None
    assert resolution.method == "unmatched"


def test_resolve_asset_by_explicit_id(db_session, make_asset):
    asset = make_asset(symbol="DEMO")
    resolution = resolve_asset(db_session, asset.id, 0.5)
    assert resolution.asset_id == asset.id
    assert resolution.method == "explicit"
    assert resolution.confidence == 1.0


def test_resolve_asset_by_symbol_keyword(db_session, make_asset):
    asset = make_asset(symbol="DEMO")
    resolution = resolve_asset(db_session, "demo", 0.42)
    assert resolution.asset_id == asset.id
    assert resolution.method == "keyword"
    assert resolution.confidence == 0.42


def test_resolve_asset_unknown_symbol_is_unmatched(db_session, make_asset):
    make_asset(symbol="DEMO")
    resolution = resolve_asset(db_session, "UNKNOWN", 0.5)
    assert resolution.asset_id is None
    assert resolution.method == "unmatched"
