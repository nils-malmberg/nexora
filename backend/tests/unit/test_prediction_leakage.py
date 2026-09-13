"""Anti-leakage and validation tests for the prediction engine
(specs/TESTING.md: 'Tests anti-fuite avec sentinelles futures, validation
chronologique, baseline naïve, reproductibilité et vérification de feature
timestamps')."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from app.prediction.engine import (
    CODE_VERSION,
    ExperimentConfig,
    MetaModel,
    build_dataset,
    dataset_fingerprint,
    usable_rows,
    walk_forward,
)


def _series(n=400, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0002, 0.01, n)
    closes = list(100 * np.exp(np.cumsum(r)))
    start = datetime(2024, 1, 1, tzinfo=UTC)
    dates = [start + timedelta(days=i) for i in range(n)]
    return dates, closes


def test_features_never_use_future_sentinels():
    """Corrupting every price after date t must leave the feature row at t
    untouched, and must change the target at t only through P_{t+h}."""
    dates, closes = _series()
    cfg = ExperimentConfig(horizon=5, lags=10, windows=(5, 20))
    ds = build_dataset(dates, closes, cfg)
    t = 250
    poisoned = list(closes)
    for i in range(t + 1, len(poisoned)):
        poisoned[i] = 1e6  # absurd future sentinel
    ds2 = build_dataset(dates, poisoned, cfg)
    np.testing.assert_array_equal(ds.features[: t + 1], ds2.features[: t + 1])
    # target at t depends on P_{t+h}: it must differ (the sentinel is in the future window)
    assert ds.target[t] != ds2.target[t]
    # targets strictly before t - h are untouched
    np.testing.assert_array_equal(ds.target[: t - cfg.horizon], ds2.target[: t - cfg.horizon])


def test_target_is_forward_return_and_last_rows_have_no_target():
    dates, closes = _series(n=50)
    cfg = ExperimentConfig(horizon=5, lags=3, windows=(5,))
    ds = build_dataset(dates, closes, cfg)
    assert np.isnan(ds.target[-5:]).all()
    assert np.isclose(ds.target[10], np.log(closes[15] / closes[10]))
    # a lagged-return feature at t equals the return realised at t - lag
    lag1 = ds.features[20, ds.feature_names.index("ret_lag_1")]
    assert np.isclose(lag1, np.log(closes[19] / closes[18]))


def test_walk_forward_folds_are_chronological_and_gapped():
    dates, closes = _series(n=400)
    cfg = ExperimentConfig(horizon=5, n_folds=4, min_train=120, models=("naive_last", "ridge"))
    ds = build_dataset(dates, closes, cfg)
    result = walk_forward(ds, cfg, [d.isoformat() for d in dates])
    assert result.ok, result.reason
    assert len(result.folds) >= 3
    prev_test_end = None
    for fold in result.folds:
        assert fold.train_end < fold.test_start  # trained strictly before tested
        train_end = datetime.fromisoformat(fold.train_end)
        test_start = datetime.fromisoformat(fold.test_start)
        assert (test_start - train_end).days >= cfg.horizon - 1  # no target/feature overlap
        if prev_test_end is not None:
            assert datetime.fromisoformat(fold.test_start) > prev_test_end  # never re-test an earlier date
        prev_test_end = datetime.fromisoformat(fold.test_end)
    # Out-of-sample predictions are all inside test windows (never on training data).
    tested_dates = {p["date"] for p in result.predictions}
    first_train_end = datetime.fromisoformat(result.folds[0].train_end)
    assert all(datetime.fromisoformat(d) > first_train_end for d in tested_dates)


def test_naive_benchmark_is_reported_and_random_walk_is_not_beaten_massively():
    dates, closes = _series(n=500, seed=42)  # a pure random walk: nothing to learn
    cfg = ExperimentConfig(horizon=5, n_folds=5, models=("naive_last", "historical_mean", "ridge"))
    ds = build_dataset(dates, closes, cfg)
    result = walk_forward(ds, cfg, [d.isoformat() for d in dates])
    assert result.ok
    assert set(result.metrics) == {"naive_last", "historical_mean", "ridge", "meta"}
    assert result.metrics["naive_last"]["rmse_vs_naive"] == 1.0
    # On a random walk no model should beat "no change" by a wide margin.
    assert result.metrics["meta"]["rmse_vs_naive"] > 0.8
    assert 0 <= result.metrics["meta"]["interval_coverage"] <= 1
    assert abs(sum(result.meta_weights.values()) - 1) < 1e-6
    assert result.latest_forecast["horizon"] == 5
    assert "objectif de prix" in result.latest_forecast["disclaimer"]


def test_experiment_is_reproducible_and_fingerprinted():
    dates, closes = _series(n=400, seed=3)
    cfg = ExperimentConfig(horizon=3, n_folds=3, models=("naive_last", "random_forest"), seed=123)
    ds = build_dataset(dates, closes, cfg)
    iso = [d.isoformat() for d in dates]
    a = walk_forward(ds, cfg, iso)
    b = walk_forward(ds, cfg, iso)
    assert a.metrics == b.metrics
    assert a.latest_forecast["expected_log_return"] == b.latest_forecast["expected_log_return"]
    assert dataset_fingerprint(dates, closes) == dataset_fingerprint(dates, list(closes))
    assert dataset_fingerprint(dates, closes) != dataset_fingerprint(dates, [c * 1.01 for c in closes])
    assert CODE_VERSION.startswith("pred-")


def test_insufficient_data_is_refused_not_guessed():
    dates, closes = _series(n=100)
    cfg = ExperimentConfig(horizon=5, min_train=120)
    ds = build_dataset(dates, closes, cfg)
    result = walk_forward(ds, cfg, [d.isoformat() for d in dates])
    assert result.ok is False
    assert "insufficient" in result.reason
    assert result.latest_forecast is None


def test_meta_model_weights_are_non_negative_and_sum_to_one():
    rng = np.random.default_rng(0)
    y = rng.normal(0, 0.01, 200)
    P = np.column_stack([y + rng.normal(0, 0.005, 200), rng.normal(0, 0.01, 200), np.zeros(200)])
    meta = MetaModel("ridge_stacking").fit(P, y)
    assert np.all(meta.weights_ >= 0) and abs(meta.weights_.sum() - 1) < 1e-9
    assert meta.weights_[0] > meta.weights_[1]  # the informative model gets the weight
    mean = MetaModel("mean").fit(P, y)
    assert np.allclose(mean.weights_, 1 / 3)


def test_config_bounds_are_clamped():
    cfg = ExperimentConfig.from_dict(
        {"horizon": 999, "lags": 0, "n_folds": 1, "models": ["ridge", "bogus"], "windows": [1, 5, 5, 20]}
    )
    assert cfg.horizon == 60 and cfg.lags == 1 and cfg.n_folds == 2
    assert cfg.models == ("ridge",)
    assert cfg.windows == (5, 20)


def test_usable_rows_exclude_warmup():
    dates, closes = _series(n=100)
    cfg = ExperimentConfig(lags=10, windows=(5, 20, 60))
    ds = build_dataset(dates, closes, cfg)
    mask = usable_rows(ds)
    assert not mask[:60].any()  # the 60-day window needs 60 returns
    assert mask[61:].all()
