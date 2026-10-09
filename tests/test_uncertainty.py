"""Uncertainty: the quotes-only bootstrap must reproduce the historical draws exactly, and the new components must load.

The frozen oracle below is the pre-refactor bootstrap_total (git 138bb44, rpi/index/uncertainty.py).
"""
import numpy as np
import pandas as pd
import pytest

from rpi.index.aggregate import aggregate
from rpi.index.elementary import rel_from_lp
from rpi.index.uncertainty import (bootstrap_replicates, bootstrap_total, mc_quantile_error,
                                   variance_decomposition)


def _old_bootstrap_total(arrays, periods, items, weights, reps=200, seed=7, min_matched=2, clip=0.7,
                         impute="division", seasonal=None):
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(reps):
        rel = pd.DataFrame(np.nan, index=periods, columns=sorted(arrays))
        n = pd.DataFrame(0, index=periods, columns=sorted(arrays))
        for it, lp in arrays.items():
            Q = lp.shape[1]
            cols = rng.integers(0, Q, Q) if Q else []
            mm_i = int(min_matched[it]) if isinstance(min_matched, pd.Series) else min_matched
            r, k = rel_from_lp(lp[:, cols] if Q else lp, mm_i, clip)
            rel[it], n[it] = r, k
        out.append(aggregate(rel, n, items, weights, min_matched, impute=impute, seasonal=seasonal)["total"].to_numpy())
    arr = np.array(out)
    return (pd.Series(np.nanpercentile(arr, 2.5, axis=0), index=periods),
            pd.Series(np.nanpercentile(arr, 97.5, axis=0), index=periods))


def _synth_arrays(seed=3, n_items=4, n_periods=6, n_quotes=5):
    rng = np.random.default_rng(seed)
    periods = pd.period_range("2025-05", periods=n_periods, freq="M")
    arrays = {}
    for j in range(n_items):
        lp = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, size=(n_periods, n_quotes)), axis=0))
        lp[0] = 100 * np.exp(rng.normal(0, 0.01, size=n_quotes))
        arrays[f"i{j}"] = lp
    items = pd.DataFrame({"item_id": list(arrays), "division": [("01", "12")[j % 2] for j in range(n_items)],
                          "tier": ["A"] * n_items})
    w = pd.Series(rng.uniform(0.5, 2.0, n_items), index=list(arrays))
    return arrays, periods, items, w


@pytest.mark.parametrize("seed", [7, 11])
def test_quotes_only_draws_are_unchanged(seed):
    arrays, periods, items, w = _synth_arrays()
    a = bootstrap_total(arrays, periods, items, w, 60, seed=seed, impute="own_trend")
    b = _old_bootstrap_total(arrays, periods, items, w, 60, seed=seed, impute="own_trend")
    pd.testing.assert_series_equal(a[0], b[0], check_exact=False, atol=0, rtol=1e-12)
    pd.testing.assert_series_equal(a[1], b[1], check_exact=False, atol=0, rtol=1e-12)


def test_quotes_only_draws_unchanged_on_real_panel():
    from rpi import db
    from rpi.config import ROOT, load_settings
    from rpi.index.panel import load_quotes, quotes_to_arrays
    s = load_settings()
    cfg = s["index"]
    conn = db.connect(ROOT / "data/rpi.sqlite")
    q = load_quotes(conn, "unit_price", cfg["min_days_per_month"], cfg.get("min_days_by_source"))
    periods = pd.period_range(q["period"].min(), q["period"].max(), freq="M")
    arrays = quotes_to_arrays(q, periods)
    items = pd.read_sql_query("SELECT * FROM items", conn)
    w = pd.read_sql_query("SELECT * FROM weights", conn).set_index("item_id")["weight"]
    a = bootstrap_total(arrays, periods, items, w, 40, impute="seasonal_trend")
    b = _old_bootstrap_total(arrays, periods, items, w, 40, impute="seasonal_trend")
    pd.testing.assert_series_equal(a[1], b[1], check_exact=False, atol=0, rtol=1e-12)


def test_cli_inputs_reproduce_the_published_band():
    """`rpi uncertainty` must decompose the band run_index publishes: same inputs, so equal reps give identical draws."""
    import sqlite3
    from rpi.config import ROOT, load_settings
    from rpi.index.engine import published_band_inputs, run_index
    s = load_settings()
    s = {**s, "index": {**s["index"], "bootstrap_reps": 15}}
    conn = sqlite3.connect(f"file:{ROOT / 'data/rpi.sqlite'}?mode=ro", uri=True)   # read-only: nothing may be written
    v = run_index(conn, s, store=False).variants["jevons_chain"]
    b = published_band_inputs(conn, s)
    assert b["base"] == b["periods"][0]
    arr = bootstrap_replicates(b["arrays"], b["periods"], b["items"], b["weights"], 15, components=("quotes",),
                               min_matched=b["min_matched"], clip=b["clip"], impute=b["impute"], seasonal=b["seasonal"])
    np.testing.assert_allclose(np.nanpercentile(arr, 2.5, axis=0), v.lo.to_numpy(dtype=float), rtol=1e-12, atol=0)
    np.testing.assert_allclose(np.nanpercentile(arr, 97.5, axis=0), v.hi.to_numpy(dtype=float), rtol=1e-12, atol=0)


def test_components_add_variance_and_decompose():
    arrays, periods, items, w = _synth_arrays(n_items=6, n_periods=8, n_quotes=3)
    runs = {}
    for name, comps in (("quotes", ("quotes",)), ("items", ("items",)), ("weights", ("weights",)),
                        ("all", ("quotes", "items", "weights"))):
        runs[name] = bootstrap_replicates(arrays, periods, items, w, 80, components=comps, impute="own_trend", seed=5)
    assert all(a.shape == (80, len(periods)) for a in runs.values())
    dec = variance_decomposition(runs, period_index=-1)
    assert dec["var"]["items"] > 0 and dec["var"]["weights"] > 0         # both new components move the result
    assert dec["var"]["all"] > dec["var"]["weights"]                     # the combined run carries all three
    assert abs(sum(dec["shares_pct"].values()) - 100.0) < 1e-6           # shares normalise on the marginal variances
    assert dec["combined_var"] == pytest.approx(dec["var"]["all"])
    se = mc_quantile_error(runs["all"], splits=40)
    assert float(np.mean(se["2.5"])) >= 0.0
