import numpy as np
import pandas as pd

from econ.experiments.items_backtest import (
    MODEL_COLUMNS,
    _identity_shrunk_prediction,
    _recency_weights,
    archive_walk_forward,
    fit_huber,
    fit_huber_through_origin,
    fit_median_monthly_offset,
    predict_fold,
)
from econ.experiments.source_panel import live_release_targets, load_source_panel


def _synthetic_panel(n_months=16, n_items=6, seed=31):
    rng = np.random.default_rng(seed)
    rows = []
    common = np.zeros(n_months)
    for t in range(1, n_months):
        common[t] = 0.6 * common[t - 1] + rng.normal(0, 0.25)
    for i in range(n_items):
        alpha = rng.normal(0, 0.15)
        beta = 0.75 + 0.1 * i
        x = rng.normal(0.4, 1.0, n_months)
        y = alpha + beta * x + common + rng.normal(0, 0.15, n_months)
        for t in range(n_months):
            rows.append({
                "period": str(pd.Period("2025-01", freq="M") + t),
                "item_id": f"F{i + 1:03d}", "quality": "exact", "weight": 1.0 + i,
                "x": x[t], "y": y[t], "n_matched": 2,
                "source_ids": "test_source", "max_input_fetched_at": "2025-01-01T00:00:00+00:00",
                "same_as_official": False,
            })
    return pd.DataFrame(rows)


def test_source_panel_uses_only_independent_observed_quotes_and_keeps_equal_pairs():
    panel = load_source_panel()
    assert not panel.empty
    assert panel.period.min() >= "2025-02"
    assert not panel.source_ids.str.contains("official_link", regex=False).any()
    # Equality is a diagnostic only. Genuine source changes that happen to equal the target
    # remain eligible; they are not removed by looking at y.
    assert panel.same_as_official.any()


def test_as_of_panel_contains_no_same_day_or_later_source_fetches():
    targets = live_release_targets()
    if targets.empty:
        return
    cutoff = targets.first_seen_on.min()
    panel = load_source_panel(as_of=cutoff)
    fetched = pd.to_datetime(panel.max_input_fetched_at, utc=True, errors="coerce").dropna()
    assert len(fetched) > 0
    assert (fetched < pd.Timestamp(cutoff, tz="UTC")).all()


def test_huber_irls_reduces_single_outlier_influence():
    x = np.linspace(-2, 2, 60)
    y = 0.2 + 1.1 * x
    y[-1] += 30.0
    p = pd.DataFrame({"period": [str(pd.Period("2025-01", freq="M") + (i // 5)) for i in range(len(x))],
                      "item_id": [f"F{i % 5:03d}" for i in range(len(x))],
                      "weight": 1.0, "x": x, "y": y})
    a, b = fit_huber(p, 1.345)
    ols_b = np.polyfit(x, y, 1)[0]
    assert abs(b - 1.1) < abs(ols_b - 1.1)
    assert np.isfinite(a)


def test_predictions_do_not_read_outer_test_target():
    panel = _synthetic_panel(n_months=18)
    target = sorted(panel.period.unique())[-1]
    train = panel[panel.period < target]
    test = panel[panel.period == target].copy()
    original = predict_fold(train, test)
    test["y"] = test.y + 1_000_000.0
    changed = predict_fold(train, test)
    for col in MODEL_COLUMNS:
        assert np.allclose(original[col], changed[col], equal_nan=True), col


def test_walk_forward_keeps_rows_that_match_official_exactly():
    panel = _synthetic_panel(n_months=14, n_items=4)
    panel["y"] = panel.x
    panel["same_as_official"] = True
    pred = archive_walk_forward(panel, min_train_months=8)
    assert len(pred) > 0
    assert pred.same_as_official.all()
    assert pred.period.min() > panel.period.min()


def test_identity_shrink_interpolates_between_raw_and_huber():
    panel = _synthetic_panel(n_months=12)
    train = panel[panel.period < "2025-11"]
    test = panel[panel.period == "2025-11"]
    alpha, beta = fit_huber(train, 1.345)
    raw = _identity_shrunk_prediction(test, alpha, beta, 0.0)
    full = _identity_shrunk_prediction(test, alpha, beta, 1.0)
    assert np.allclose(raw, test.x)
    assert np.allclose(full, alpha + beta * test.x)


def test_recency_weights_downweight_old_months_and_sum_to_one():
    panel = _synthetic_panel(n_months=10, n_items=4)
    weights = _recency_weights(panel, 3.0)
    month_weights = pd.Series(weights).groupby(panel.period).sum()
    assert np.isclose(weights.sum(), 1.0)
    assert month_weights.iloc[-1] > month_weights.iloc[0]
    assert np.all(np.diff(month_weights.to_numpy()) > 0)


def test_median_monthly_offset_is_robust_to_one_extreme_month():
    rows = []
    offsets = [1.0, 1.0, 1.0, 1.0, 100.0]
    for t, offset in enumerate(offsets):
        for item, x in enumerate((-1.0, 1.0)):
            rows.append({"period": str(pd.Period("2025-01", freq="M") + t),
                         "item_id": f"F{item:03d}", "weight": 1.0,
                         "x": x, "y": x + offset})
    assert fit_median_monthly_offset(pd.DataFrame(rows)) == 1.0


def test_huber_through_origin_recovers_clean_proportional_relation():
    rows = []
    for t in range(6):
        for x in (-2.0, -1.0, 1.0, 2.0):
            rows.append({"period": str(pd.Period("2025-01", freq="M") + t),
                         "item_id": f"F{len(rows) % 4:03d}", "weight": 1.0,
                         "x": x, "y": 1.4 * x})
    beta = fit_huber_through_origin(pd.DataFrame(rows))
    assert abs(beta - 1.4) < 1e-6
