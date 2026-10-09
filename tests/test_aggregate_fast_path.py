"""The numpy rewrite of impute_relatives must be numerically identical to the scalar version it replaced.

The pandas implementation below is a FROZEN ORACLE: it is the exact code that shipped before the vectorisation
(git 138bb44, rpi/index/aggregate.py) and must not be "fixed" - if it and the live implementation ever disagree,
the live one has changed behaviour and that is a regression, not a test bug.
"""
import numpy as np
import pandas as pd
import pytest

from rpi.index.aggregate import impute_relatives


def _reference_impute(rel, observed, items, w, method="division", trend_window=12, min_history=3, seasonal=None):
    div = items.set_index("item_id")["division"].reindex(rel.columns)
    filled = rel.copy()
    imputed = pd.DataFrame(False, index=rel.index, columns=rel.columns)
    for t in rel.index:
        obs = observed.loc[t] & rel.loc[t].notna()
        if obs.all():
            continue
        overall = np.average(rel.loc[t][obs], weights=w[obs]) if obs.any() else 0.0
        for d in div.unique():
            cols = div.index[div == d]
            o = obs[cols]
            val = np.average(rel.loc[t, cols][o], weights=w[cols][o]) if o.any() else overall
            miss = cols[~o.values]
            filled.loc[t, miss] = val
            imputed.loc[t, miss] = True
            if method in ("own_trend", "seasonal_trend"):
                pos = rel.index.get_loc(t)
                for c in miss:
                    if method == "seasonal_trend" and seasonal and c in seasonal and not observed[c].iloc[pos + 1:].any():
                        clim, seas = seasonal[c]
                        filled.loc[t, c] = clim + float(seas[t.month - 1])
                        continue
                    hist = rel[c].iloc[1:pos][observed[c].iloc[1:pos].to_numpy()].dropna()
                    if len(hist) >= min_history:
                        filled.loc[t, c] = float(np.mean(hist.iloc[-trend_window:]))
    return filled, imputed


def _assert_same(rel, observed, items, w, **kw):
    a_f, a_i = impute_relatives(rel, observed, items, w, **kw)
    b_f, b_i = _reference_impute(rel, observed, items, w, **kw)
    assert a_i.equals(b_i), "imputation flags differ"
    pd.testing.assert_frame_equal(a_f, b_f, check_exact=False, atol=1e-15, rtol=0)


def _synth(seed, n_p=14, n_i=9, missing=0.35):
    rng = np.random.default_rng(seed)
    P = pd.period_range("2025-03", periods=n_p, freq="M")
    cols = [f"i{j:02d}" for j in range(n_i)]
    steps = rng.normal(0.004, 0.02, size=(n_p, n_i))
    rel = pd.DataFrame(np.cumsum(steps, axis=0), index=P, columns=cols)
    seen = rng.random((n_p, n_i)) > missing
    seen[0] = True
    # occasionally observed-but-NaN: the scalar code treats those as missing too
    rel[seen & (rng.random((n_p, n_i)) < 0.06)] = np.nan
    n = pd.DataFrame(seen.astype(int) * rng.integers(1, 4, (n_p, n_i)), index=P, columns=cols)
    items = pd.DataFrame({"item_id": cols, "division": [("04" if j % 3 else "12") for j in range(n_i)]})
    w = pd.Series(rng.uniform(0.2, 2.0, n_i), index=cols)
    seasonal = {c: (0.004, np.linspace(-0.01, 0.02, 12)) for c in cols[:4]}
    return rel, n, items, w, seasonal


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
@pytest.mark.parametrize("method", ["division", "own_trend", "seasonal_trend"])
def test_fast_path_matches_frozen_oracle_on_synthetic(seed, method):
    rel, n, items, w, seasonal = _synth(seed)
    observed = n.ge(2) & rel.notna()
    observed.iloc[0] = n.iloc[0].ge(1) & rel.iloc[0].notna()
    _assert_same(rel, observed, items, w, method=method, seasonal=seasonal)


def test_fast_path_matches_oracle_edge_cases():
    P = pd.period_range("2026-01", periods=4, freq="M")
    rel = pd.DataFrame({"a": [0.0, np.nan, np.nan, np.nan], "b": [0.0, np.nan, np.nan, np.nan]}, index=P)
    n = pd.DataFrame(0, index=P, columns=["a", "b"])
    items = pd.DataFrame({"item_id": ["a", "b"], "division": ["01", "01"]})
    w = pd.Series({"a": 1.0, "b": 1.0})
    observed = n.ge(2) & rel.notna()
    observed.iloc[0] = n.iloc[0].ge(1) & rel.iloc[0].notna()
    for method in ("division", "own_trend", "seasonal_trend"):
        _assert_same(rel, observed, items, w, method=method)


def test_fast_path_matches_oracle_on_the_real_quotes_panel():
    """The panel the engine actually aggregates: 66 items, missing months, real seasonal tables."""
    from rpi import db
    from rpi.config import ROOT, load_settings
    from rpi.index.panel import load_quotes, quotes_to_arrays
    from rpi.index.elementary import rel_from_lp
    from rpi.seasonal import load_tables

    s = load_settings()
    cfg = s["index"]
    conn = db.connect(ROOT / "data/rpi.sqlite")
    q = load_quotes(conn, "unit_price", cfg["min_days_per_month"], cfg.get("min_days_by_source"))
    periods = pd.period_range(q["period"].min(), q["period"].max(), freq="M")
    arrays = quotes_to_arrays(q, periods)
    items = pd.read_sql_query("SELECT * FROM items", conn)
    w = pd.read_sql_query("SELECT * FROM weights", conn).set_index("item_id")["weight"]
    cols = [c for c in w.index if c in set(items["item_id"])]
    rel = pd.DataFrame(np.nan, index=periods, columns=cols)
    n = pd.DataFrame(0, index=periods, columns=cols)
    for it, lp in arrays.items():
        if it in rel.columns:
            r, k = rel_from_lp(lp, 1, cfg["max_abs_log_change"])
            rel[it], n[it] = r, k
    min_m = items.set_index("item_id")["tier"].map(lambda t: cfg.get("min_matched_by_tier", {}).get(t, cfg["min_matched"])).astype(int).reindex(cols).fillna(2)
    observed = n.ge(min_m, axis=1) & rel.notna()
    observed.iloc[0] = n.iloc[0].ge(1) & rel.iloc[0].notna()
    seasonal = load_tables(ROOT)
    for method in ("division", "own_trend", "seasonal_trend"):
        _assert_same(rel, observed, items, w, method=method, seasonal=seasonal)
