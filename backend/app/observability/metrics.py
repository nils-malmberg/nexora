"""Prometheus metrics for the whole application: auth/portfolio, market data
providers, the news ingestion pipeline, analytics and prediction. No label
ever carries a secret, an amount, or a licensed title."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# --- Auth / portfolio -------------------------------------------------------
auth_attempts_total = Counter("nexora_auth_attempts_total", "Auth attempts by kind and outcome", ["kind", "outcome"])
account_deletions_total = Counter("nexora_account_deletions_total", "Accounts deleted")
transactions_created_total = Counter("nexora_transactions_created_total", "Transactions created by type", ["type"])
analytics_requests_total = Counter("nexora_analytics_requests_total", "Analytics endpoint calls", ["endpoint"])

# --- Market data ------------------------------------------------------------
market_requests_total = Counter(
    "nexora_market_requests_total", "Outbound market-data requests by provider and outcome", ["provider", "outcome"]
)
market_request_latency_seconds = Histogram(
    "nexora_market_request_latency_seconds", "Outbound market-data request latency", ["provider"]
)
market_rate_limited_total = Counter(
    "nexora_market_rate_limited_total", "Requests refused locally by the per-provider token bucket", ["provider"]
)
market_provider_up = Gauge("nexora_market_provider_up", "1 if the market provider circuit is closed", ["provider"])
market_quote_age_seconds = Gauge(
    "nexora_market_quote_age_seconds", "Age of the freshest quote for an instrument", ["instrument_id"]
)
market_cache_hits_total = Counter("nexora_market_cache_hits_total", "Quote/history served from cache", ["kind"])

# --- News ingestion ---------------------------------------------------------
ingestion_runs_total = Counter(
    "nexora_ingestion_runs_total", "Ingestion runs by provider and outcome", ["provider_id", "status"]
)
ingestion_latency_seconds = Histogram("nexora_ingestion_latency_seconds", "Ingestion run duration", ["provider_id"])
items_processed_total = Counter(
    "nexora_items_processed_total",
    "Items processed by outcome",
    ["provider_id", "outcome"],
)
parsing_errors_total = Counter("nexora_parsing_errors_total", "Records rejected during normalize()", ["provider_id"])
missing_field_total = Counter("nexora_missing_field_total", "Records missing a given field", ["provider_id", "field"])
asset_freshness_age_seconds = Gauge(
    "nexora_asset_freshness_age_seconds",
    "Age of the most recent item for an instrument",
    ["instrument_id", "data_type"],
)
provider_up = Gauge("nexora_provider_up", "1 if the news provider circuit is closed, else 0", ["provider_id"])
provider_auto_disabled_total = Counter(
    "nexora_provider_auto_disabled_total",
    "Providers auto-disabled after too many consecutive failures (requires manual re-enable)",
    ["provider_id"],
)
stale_responses_total = Counter("nexora_stale_responses_total", "API responses served with stale=true", ["endpoint"])
collection_publication_lag_seconds = Histogram(
    "nexora_collection_publication_lag_seconds", "collected_at - publication_at", ["provider_id"]
)

# --- Prediction -------------------------------------------------------------
prediction_runs_total = Counter("nexora_prediction_runs_total", "Prediction experiments run by outcome", ["outcome"])
prediction_training_seconds = Histogram("nexora_prediction_training_seconds", "Wall time of one experiment run")
