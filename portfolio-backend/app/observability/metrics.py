from __future__ import annotations

from prometheus_client import Counter

auth_attempts_total = Counter(
    "nexora_portfolio_auth_attempts_total", "Auth attempts by kind and outcome", ["kind", "outcome"]
)
account_deletions_total = Counter("nexora_portfolio_account_deletions_total", "Accounts deleted")
transactions_created_total = Counter(
    "nexora_portfolio_transactions_created_total", "Transactions created by type", ["type"]
)
analytics_requests_total = Counter(
    "nexora_portfolio_analytics_requests_total", "Analytics endpoint calls by endpoint", ["endpoint"]
)
