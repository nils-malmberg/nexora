from datetime import UTC, datetime, timedelta

from app.pipeline.scoring import ScoreInput, compute_relevance


def _base_input(**overrides) -> ScoreInput:
    now = datetime(2026, 9, 10, tzinfo=UTC)
    defaults = dict(
        asset_match_confidence=1.0,
        category="resultats",
        has_event_at=True,
        provenance_confidence=0.8,
        corroboration_count=0,
        reference_at=now,
        now=now,
    )
    defaults.update(overrides)
    return ScoreInput(**defaults)


def test_score_is_bounded_between_0_and_1():
    score, _ = compute_relevance(_base_input())
    assert 0.0 <= score <= 1.0


def test_recency_decreases_score_over_time():
    now = datetime(2026, 9, 10, tzinfo=UTC)
    fresh_score, _ = compute_relevance(_base_input(reference_at=now, now=now))
    old_score, _ = compute_relevance(_base_input(reference_at=now - timedelta(days=30), now=now))
    assert fresh_score > old_score


def test_category_weight_ranks_results_above_generic_category():
    high, _ = compute_relevance(_base_input(category="resultats"))
    low, _ = compute_relevance(_base_input(category="autre"))
    assert high > low


def test_corroboration_increases_score_but_is_capped():
    base, _ = compute_relevance(_base_input(corroboration_count=0))
    one, _ = compute_relevance(_base_input(corroboration_count=1))
    many, _ = compute_relevance(_base_input(corroboration_count=10))
    capped, _ = compute_relevance(_base_input(corroboration_count=3))
    assert base < one < many
    assert many == capped  # corroboration contribution is capped at 3+


def test_breakdown_is_explainable_and_reconstructs_total():
    score, breakdown = compute_relevance(_base_input())
    assert set(breakdown["subscores"]) == set(breakdown["weights"])
    reconstructed = sum(breakdown["contributions"].values())
    assert round(reconstructed, 4) == score
