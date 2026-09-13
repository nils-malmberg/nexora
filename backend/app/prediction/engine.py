"""Experimental prediction engine — specs/PREDICTION.md.

Pure functions (no DB, no network): build a leakage-free supervised dataset
from a daily price series, evaluate base models and a stacked *meta-model*
with a strictly chronological walk-forward, and report metrics against a
naive benchmark. Everything is reproducible from (config, series, seed).

Anti-leakage rules, enforced by construction and by tests
(tests/unit/test_prediction_leakage.py):

- every feature at date t uses observations at t or earlier only (lags,
  trailing windows); rolling statistics are computed *inside* each training
  fold, never on the full series;
- the target at t is the forward h-period log return (t -> t+h), so the last
  h rows have no target and are excluded from training;
- folds are contiguous in time: train on [0, split), test on
  [split + h - 1, next split) - the `h - 1` gap guarantees no training
  target overlaps a test feature window;
- scalers/models are fit on the training fold only.

Outputs are educational: point forecasts with empirical intervals and the
metrics needed to judge whether the model beats "no change" at all — never a
price target or a signal.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

CODE_VERSION = "pred-2026.09.1"

BASE_MODELS = ("naive_last", "historical_mean", "ridge", "random_forest", "gradient_boosting")
DEFAULT_MODELS = ("naive_last", "ridge", "random_forest", "gradient_boosting")


@dataclass
class ExperimentConfig:
    horizon: int = 5  # periods ahead
    lags: int = 10
    windows: tuple[int, ...] = (5, 20, 60)
    models: tuple[str, ...] = DEFAULT_MODELS
    meta_model: str = "ridge_stacking"  # ridge_stacking | mean
    n_folds: int = 5
    min_train: int = 120
    seed: int = 42
    interval_confidence: float = 0.8

    @classmethod
    def from_dict(cls, raw: dict) -> ExperimentConfig:
        cfg = cls()
        for key in ("horizon", "lags", "n_folds", "min_train", "seed"):
            if key in raw and raw[key] is not None:
                setattr(cfg, key, int(raw[key]))
        if raw.get("windows"):
            cfg.windows = tuple(sorted({int(w) for w in raw["windows"] if int(w) >= 2}))
        if raw.get("models"):
            cfg.models = tuple(m for m in raw["models"] if m in BASE_MODELS) or DEFAULT_MODELS
        if raw.get("meta_model") in ("ridge_stacking", "mean"):
            cfg.meta_model = raw["meta_model"]
        if raw.get("interval_confidence"):
            cfg.interval_confidence = float(raw["interval_confidence"])
        cfg.horizon = max(1, min(cfg.horizon, 60))
        cfg.lags = max(1, min(cfg.lags, 60))
        cfg.n_folds = max(2, min(cfg.n_folds, 12))
        cfg.min_train = max(60, min(cfg.min_train, 2000))
        cfg.interval_confidence = min(0.99, max(0.5, cfg.interval_confidence))
        return cfg

    def to_dict(self) -> dict:
        return {
            "horizon": self.horizon,
            "lags": self.lags,
            "windows": list(self.windows),
            "models": list(self.models),
            "meta_model": self.meta_model,
            "n_folds": self.n_folds,
            "min_train": self.min_train,
            "seed": self.seed,
            "interval_confidence": self.interval_confidence,
        }


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------


def dataset_fingerprint(dates: list, closes: list) -> str:
    h = hashlib.sha256()
    for d, c in zip(dates, closes, strict=True):
        h.update(f"{d.isoformat() if hasattr(d, 'isoformat') else d}|{float(c):.6f};".encode())
    return h.hexdigest()


@dataclass
class Dataset:
    dates: list
    features: np.ndarray  # (n, k)
    feature_names: list[str]
    target: np.ndarray  # (n,) forward log return; NaN where unknown (last h rows)
    last_close: float


def build_dataset(dates: list, closes: list, cfg: ExperimentConfig) -> Dataset:
    c = np.array([float(x) for x in closes], dtype=float)
    n = len(c)
    with np.errstate(divide="ignore", invalid="ignore"):
        lr = np.concatenate([[np.nan], np.log(c[1:] / c[:-1])])

    cols: list[np.ndarray] = []
    names: list[str] = []
    for lag in range(1, cfg.lags + 1):
        shifted = np.full(n, np.nan)
        shifted[lag:] = lr[:-lag] if lag else lr
        cols.append(shifted)
        names.append(f"ret_lag_{lag}")
    for w in cfg.windows:
        mean = np.full(n, np.nan)
        std = np.full(n, np.nan)
        mom = np.full(n, np.nan)
        for i in range(w, n):
            seg = lr[i - w + 1 : i + 1]
            if np.isnan(seg).any():
                continue
            mean[i] = seg.mean()
            std[i] = seg.std(ddof=0)
            mom[i] = math.log(c[i] / c[i - w]) if c[i - w] > 0 else np.nan
        cols += [mean, std, mom]
        names += [f"ret_mean_{w}", f"ret_std_{w}", f"momentum_{w}"]
    # trailing RSI-like oscillator on a 14-window, past only
    rsi = np.full(n, np.nan)
    for i in range(14, n):
        seg = lr[i - 13 : i + 1]
        if np.isnan(seg).any():
            continue
        gains, losses = seg[seg > 0].sum(), -seg[seg < 0].sum()
        rsi[i] = 100.0 if losses == 0 else 100.0 - 100.0 / (1.0 + gains / losses)
    cols.append(rsi)
    names.append("rsi_14")

    features = np.column_stack(cols) if cols else np.empty((n, 0))
    target = np.full(n, np.nan)
    h = cfg.horizon
    for i in range(0, n - h):
        if c[i] > 0 and c[i + h] > 0:
            target[i] = math.log(c[i + h] / c[i])
    return Dataset(dates=list(dates), features=features, feature_names=names, target=target, last_close=float(c[-1]))


def usable_rows(ds: Dataset) -> np.ndarray:
    return ~np.isnan(ds.features).any(axis=1)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class _Naive:
    """Predicts a zero forward return ("no change") — the benchmark every
    other model must beat to be worth anything."""

    def fit(self, X, y):
        return self

    def predict(self, X):
        return np.zeros(len(X))


class _HistoricalMean:
    def fit(self, X, y):
        self.mean_ = float(np.mean(y)) if len(y) else 0.0
        return self

    def predict(self, X):
        return np.full(len(X), self.mean_)


def make_model(name: str, seed: int):
    if name == "naive_last":
        return _Naive()
    if name == "historical_mean":
        return _HistoricalMean()
    if name == "ridge":
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        return make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    if name == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        return RandomForestRegressor(n_estimators=150, max_depth=6, min_samples_leaf=5, random_state=seed, n_jobs=1)
    if name == "gradient_boosting":
        from sklearn.ensemble import GradientBoostingRegressor

        return GradientBoostingRegressor(
            n_estimators=150, max_depth=3, learning_rate=0.05, subsample=0.8, random_state=seed
        )
    raise ValueError(f"unknown model {name}")


class MetaModel:
    """Stacking: a ridge regression (non-negative, no intercept) over the base
    models' *out-of-fold* predictions, or a plain mean. Fitted only on
    predictions the base models made for dates they had not trained on."""

    def __init__(self, kind: str):
        self.kind = kind
        self.weights_: np.ndarray | None = None

    def fit(self, P: np.ndarray, y: np.ndarray) -> MetaModel:
        k = P.shape[1]
        if self.kind == "mean" or len(y) < 5 * k:
            self.weights_ = np.full(k, 1.0 / k)
            return self
        from scipy.optimize import nnls

        w, _ = nnls(P, y)
        if w.sum() <= 0:
            w = np.full(k, 1.0 / k)
        self.weights_ = w / w.sum()
        return self

    def predict(self, P: np.ndarray) -> np.ndarray:
        return P @ self.weights_


# ---------------------------------------------------------------------------
# Walk-forward evaluation
# ---------------------------------------------------------------------------


@dataclass
class FoldResult:
    index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    n_train: int
    n_test: int
    metrics: dict[str, dict[str, float]]


@dataclass
class ExperimentResult:
    ok: bool
    reason: str | None
    config: dict
    n_observations: int
    feature_names: list[str]
    folds: list[FoldResult] = field(default_factory=list)
    metrics: dict[str, dict[str, float | None]] = field(default_factory=dict)
    predictions: list[dict] = field(default_factory=list)
    latest_forecast: dict | None = None
    meta_weights: dict[str, float] = field(default_factory=dict)
    dataset_hash: str | None = None


def _metrics(y: np.ndarray, p: np.ndarray, residual_q: tuple[float, float] | None = None) -> dict[str, float]:
    err = p - y
    out = {
        "mae": float(np.abs(err).mean()),
        "rmse": float(math.sqrt((err**2).mean())),
        "direction_accuracy": float((np.sign(p) == np.sign(y)).mean()),
        "bias": float(err.mean()),
    }
    if residual_q is not None:
        lo, hi = residual_q
        out["interval_coverage"] = float(((y >= p + lo) & (y <= p + hi)).mean())
    return out


def walk_forward(ds: Dataset, cfg: ExperimentConfig, dates_iso: list[str]) -> ExperimentResult:
    mask = usable_rows(ds)
    has_target = ~np.isnan(ds.target)
    idx = np.where(mask & has_target)[0]
    n = len(idx)
    min_needed = cfg.min_train + cfg.n_folds * max(cfg.horizon, 10)
    if n < min_needed:
        return ExperimentResult(
            False, f"insufficient data: {n} usable rows, need at least {min_needed}", cfg.to_dict(), n, ds.feature_names
        )

    X, y = ds.features[idx], ds.target[idx]
    h = cfg.horizon
    # Expanding-window folds: split points evenly over the post-min_train region.
    splits = np.linspace(cfg.min_train, n, cfg.n_folds + 1).astype(int)
    models = list(cfg.models)
    oof_pred = {m: np.full(n, np.nan) for m in models}
    folds: list[FoldResult] = []
    residuals = {m: [] for m in models}
    alpha = (1 - cfg.interval_confidence) / 2

    for f in range(cfg.n_folds):
        train_end = splits[f]
        test_start = min(n, train_end + h - 1)  # gap so no train target overlaps test features
        test_end = splits[f + 1]
        if test_end - test_start < 3:
            continue
        Xtr, ytr = X[:train_end], y[:train_end]
        Xte, yte = X[test_start:test_end], y[test_start:test_end]
        fold_metrics: dict[str, dict[str, float]] = {}
        for m in models:
            model = make_model(m, cfg.seed + f)
            model.fit(Xtr, ytr)
            p = np.asarray(model.predict(Xte), dtype=float)
            oof_pred[m][test_start:test_end] = p
            fold_metrics[m] = _metrics(yte, p)
            residuals[m].extend((yte - p).tolist())
        folds.append(
            FoldResult(
                index=f,
                train_start=dates_iso[idx[0]],
                train_end=dates_iso[idx[train_end - 1]],
                test_start=dates_iso[idx[test_start]],
                test_end=dates_iso[idx[test_end - 1]],
                n_train=int(train_end),
                n_test=int(test_end - test_start),
                metrics=fold_metrics,
            )
        )

    tested = ~np.isnan(oof_pred[models[0]])
    if tested.sum() < 10:
        return ExperimentResult(
            False, "walk-forward produced too few out-of-sample points", cfg.to_dict(), n, ds.feature_names
        )

    P = np.column_stack([oof_pred[m][tested] for m in models])
    y_oos = y[tested]
    meta = MetaModel(cfg.meta_model).fit(P, y_oos)
    meta_pred = meta.predict(P)
    meta_res = y_oos - meta_pred

    overall: dict[str, dict[str, float | None]] = {}
    for j, m in enumerate(models):
        q = (float(np.quantile(residuals[m], alpha)), float(np.quantile(residuals[m], 1 - alpha)))
        overall[m] = _metrics(y_oos, P[:, j], q)
    q_meta = (float(np.quantile(meta_res, alpha)), float(np.quantile(meta_res, 1 - alpha)))
    overall["meta"] = _metrics(y_oos, meta_pred, q_meta)
    naive_rmse = overall.get("naive_last", overall[models[0]])["rmse"]
    for k in overall:
        overall[k]["rmse_vs_naive"] = (overall[k]["rmse"] / naive_rmse) if naive_rmse and naive_rmse > 0 else None

    tested_idx = idx[tested]
    predictions = [
        {
            "date": dates_iso[tested_idx[i]],
            "actual": float(y_oos[i]),
            "meta": float(meta_pred[i]),
            **{m: float(P[i, j]) for j, m in enumerate(models)},
        }
        for i in range(len(tested_idx))
    ]

    # Final refit on everything usable (features known) to produce one
    # forward-looking, clearly-labelled forecast with an empirical interval.
    last_row = np.where(mask)[0][-1]
    final_models = {}
    X_final = ds.features[[last_row]]
    point_by_model = {}
    for m in models:
        model = make_model(m, cfg.seed).fit(X, y)
        final_models[m] = model
        point_by_model[m] = float(np.asarray(model.predict(X_final))[0])
    meta_point = float(meta.predict(np.array([[point_by_model[m] for m in models]]))[0])
    latest = {
        "as_of": dates_iso[last_row],
        "horizon": h,
        "last_close": ds.last_close,
        "expected_log_return": meta_point,
        "interval_confidence": cfg.interval_confidence,
        "interval_log_return": [meta_point + q_meta[0], meta_point + q_meta[1]],
        "implied_price": ds.last_close * math.exp(meta_point),
        "implied_price_interval": [
            ds.last_close * math.exp(meta_point + q_meta[0]),
            ds.last_close * math.exp(meta_point + q_meta[1]),
        ],
        "by_model": point_by_model,
        "disclaimer": (
            "Expérimental : projection statistique d'un modèle entraîné sur le passé, avec un intervalle "
            "empirique calibré sur ses propres erreurs hors échantillon. Ce n'est ni un objectif de prix, "
            "ni un signal, ni un conseil."
        ),
    }
    return ExperimentResult(
        ok=True,
        reason=None,
        config=cfg.to_dict(),
        n_observations=n,
        feature_names=ds.feature_names,
        folds=folds,
        metrics=overall,
        predictions=predictions,
        latest_forecast=latest,
        meta_weights={m: float(w) for m, w in zip(models, meta.weights_, strict=True)},
    )
