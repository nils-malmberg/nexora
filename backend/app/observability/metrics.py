"""Prometheus metrics for the ingestion pipeline and API.

Covers the measurements required by specs/NEWS_AND_EVENTS.md: per-provider
success/failure, freshness per asset, latency, collected/normalized/dedup
volume, missing-field rate, duplicate rate, parsing errors, staleness served,
and collection-to-publication lag. There is no separate cache layer (see
app/pipeline/cache.py), so `stale_responses_total` plays the role a cache-hit
ratio would in a system with one.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

ingestion_runs_total = Counter(
    "nexora_ingestion_runs_total", "Ingestion runs by provider and outcome", ["provider_id", "status"]
)
ingestion_latency_seconds = Histogram("nexora_ingestion_latency_seconds", "Ingestion run duration", ["provider_id"])
items_processed_total = Counter(
    "nexora_items_processed_total",
    "Items processed by outcome",
    ["provider_id", "outcome"],  # inserted|updated|duplicate|corroborates|skipped_parse_error|unmatched_asset
)
parsing_errors_total = Counter("nexora_parsing_errors_total", "Records rejected during normalize()", ["provider_id"])
missing_field_total = Counter("nexora_missing_field_total", "Records missing a given field", ["provider_id", "field"])
asset_freshness_age_seconds = Gauge(
    "nexora_asset_freshness_age_seconds", "Age of the most recent item for an asset", ["asset_id", "data_type"]
)
provider_up = Gauge("nexora_provider_up", "1 if the provider circuit is closed, else 0", ["provider_id"])
provider_auto_disabled_total = Counter(
    "nexora_provider_auto_disabled_total",
    "Providers auto-disabled after too many consecutive failures (requires manual re-enable)",
    ["provider_id"],
)
stale_responses_total = Counter("nexora_stale_responses_total", "API responses served with stale=true", ["endpoint"])
collection_publication_lag_seconds = Histogram(
    "nexora_collection_publication_lag_seconds", "collected_at - publication_at", ["provider_id"]
)
