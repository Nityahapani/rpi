import numpy as np
import pandas as pd

from rpi.index.aggregate import aggregate
from rpi.seasonal import calibrate_wholesale, fuse, prior, seasonal_table


def _series(n_years=8, amp=0.05, noise=0.0, drift=0.002, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2014-01", periods=12 * n_years, freq="M")
    m = np.array([p.month for p in idx])
    return pd.Series(drift + amp * np.sin(2 * np.pi * m / 12) + noise * rng.standard_normal(len(idx)), index=idx)


def test_seasonal_table_recovers_a_clean_seasonal_pattern():
    s = _series()
    t = seasonal_table(s)
    assert abs(t.clim.iloc[0] - 0.002) < 1e-3
    truth = 0.05 * np.sin(2 * np.pi * np.arange(1, 13) / 12)
    assert np.corrcoef(t.seas.values, truth)[0, 1] > 0.99


def test_seasonal_table_shrinks_pure_noise_toward_zero():
    t = seasonal_table(_series(amp=0.0, noise=0.05, seed=3))
    assert t.seas.abs().max() < 0.03          # noise-only months are shrunk hard


def test_short_history_gives_flat_prior():
    t = seasonal_table(_series(n_years=2))
    assert (t.seas == 0).all()


def test_fuse_is_precision_weighted_and_falls_back_when_wholesale_is_useless():
    assert abs(fuse(0.01, 0.2, b0=1.0, sigma_wb=1e-4, sigma_prior=1.0) - 0.2) < 1e-3     # precise wholesale dominates
    assert abs(fuse(0.01, 0.2, b0=0.3, sigma_wb=1.0, sigma_prior=1e-4) - 0.01) < 1e-3    # precise prior dominates
    x = fuse(0.0, 0.2, b0=0.3, sigma_wb=0.1, sigma_prior=0.1)
    assert abs(x - 0.03) < 1e-9                                                           # equal precision: mean of 0 and 0.3*0.2


def test_calibration_only_touches_months_after_first_independent_month():
    idx = pd.period_range("2026-06", periods=5, freq="M")
    rel = pd.DataFrame({"X": [0.05, 0.05, np.nan, 0.20, 0.20]}, index=idx)
    n = pd.DataFrame({"X": [1, 1, 0, 1, 1]}, index=idx)
    tables = {"X": (0.0, np.zeros(12))}
    cal = {"X": dict(b0=0.5, sigma_wb=0.1, sigma_prior=0.1)}
    out, log = calibrate_wholesale(rel, n, {"X": "2026-08"}, cal, tables)
    assert out["X"].iloc[0] == 0.05 and out["X"].iloc[1] == 0.05      # before the cutoff: official stand-in untouched
    assert np.isnan(out["X"].iloc[2])                                   # splice month stays missing (imputed later)
    assert abs(out["X"].iloc[3] - 0.05) < 1e-9 and len(log) == 2        # (0 + 0.5*0.2)/2


def test_seasonal_trend_imputation_uses_the_table_and_falls_back_to_own_trend():
    idx = pd.period_range("2026-01", periods=8, freq="M")
    rel = pd.DataFrame({"a": 0.01, "b": 0.01, "c": 0.01}, index=idx)
    rel.loc[idx[-1], ["b", "c"]] = np.nan
    n = pd.DataFrame(1, index=idx, columns=rel.columns)
    n.loc[idx[-1], ["b", "c"]] = 0
    items = pd.DataFrame({"item_id": ["a", "b", "c"], "division": ["01", "01", "01"], "tier": ["A", "A", "A"]})
    w = pd.Series({"a": 1.0, "b": 1.0, "c": 1.0})
    seas = np.zeros(12); seas[idx[-1].month - 1] = 0.1
    out = aggregate(rel, n, items, w, 1, impute="seasonal_trend", seasonal={"b": (0.0, seas)})
    lv = out["items"]
    assert out["imputed"]["b"].iloc[-1] and out["imputed"]["c"].iloc[-1]
    assert abs(np.log(lv["b"].iloc[-1] / lv["b"].iloc[-2]) - 0.1) < 1e-9      # table prior
    assert abs(np.log(lv["c"].iloc[-1] / lv["c"].iloc[-2]) - 0.01) < 1e-9     # no table -> own 12-month mean


def test_prior_missing_item_returns_none():
    assert prior({}, "Z", pd.Period("2026-01", "M")) is None


def test_interior_gap_keeps_own_trend_but_trailing_gap_uses_the_table():
    idx = pd.period_range("2026-01", periods=8, freq="M")
    rel = pd.DataFrame({"a": 0.01, "b": 0.01}, index=idx)
    rel.loc[idx[3], "b"] = np.nan           # interior gap (splice-like)
    rel.loc[idx[-1], "b"] = np.nan          # trailing gap (nowcast)
    n = pd.DataFrame(1, index=idx, columns=rel.columns); n.loc[idx[3], "b"] = 0; n.loc[idx[-1], "b"] = 0
    items = pd.DataFrame({"item_id": ["a", "b"], "division": ["01", "01"], "tier": ["A", "A"]})
    seas = np.full(12, 0.1)
    lv = aggregate(rel, n, items, pd.Series({"a": 1.0, "b": 1.0}), 1, impute="seasonal_trend", seasonal={"b": (0.0, seas)})["items"]["b"]
    assert abs(np.log(lv.iloc[3] / lv.iloc[2]) - 0.01) < 1e-9     # interior: own trend
    assert abs(np.log(lv.iloc[-1] / lv.iloc[-2]) - 0.1) < 1e-9    # trailing: table
