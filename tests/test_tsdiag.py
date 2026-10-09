"""Behavioural tests for rpi/tsdiag.py: the tests must behave as their textbook counterparts on known series."""
import numpy as np
import pandas as pd

from rpi.tsdiag import adf, classical_decompose, kpss, ljung_box, report, residual_seasonality, seasonal_strength


def _periods(n, start="2010-01"):
    return pd.period_range(start, periods=n, freq="M")


def test_adf_and_kpss_agree_on_a_random_walk_and_a_mean_reverting_series():
    rng = np.random.default_rng(0)
    n = 480
    rw = pd.Series(np.cumsum(rng.normal(0, 1, n)), index=_periods(n))
    ar = pd.Series(rng.normal(0, 1, n), index=_periods(n))          # white noise: strongly stationary
    a_rw, a_ar = adf(rw), adf(ar)
    assert not a_rw["reject_unit_root_5pct"] and a_ar["reject_unit_root_5pct"]
    k_rw, k_ar = kpss(rw), kpss(ar)
    assert k_rw["reject_stationary_5pct"] and not k_ar["reject_stationary_5pct"]


def test_ljung_box_flags_autocorrelation_but_not_white_noise():
    rng = np.random.default_rng(1)
    n = 300
    wn = pd.Series(rng.normal(0, 1, n), index=_periods(n))
    ar1 = wn.copy()
    for i in range(1, n):
        ar1.iloc[i] = 0.8 * ar1.iloc[i - 1] + rng.normal(0, 1)
    assert ljung_box(wn)["p"] > 0.01
    assert ljung_box(ar1)["p"] < 1e-6


def test_seasonal_decomposition_recovers_planted_factors():
    rng = np.random.default_rng(2)
    n = 180
    idx = _periods(n)
    planted = np.array([1.02, 0.99, 1.00, 0.97, 1.01, 1.03, 0.98, 1.00, 1.02, 0.99, 0.98, 1.01])
    trend = np.linspace(100, 130, n)
    y = pd.Series(trend * planted[[p.month - 1 for p in idx]] * np.exp(rng.normal(0, 0.002, n)), index=idx)
    d = classical_decompose(y).dropna()
    est = d.groupby(d.index.month)["seasonal"].mean()
    assert np.corrcoef(est, pd.Series(planted, index=range(1, 13))) [0, 1] > 0.9
    assert abs(est.mean() - 1.0) < 1e-9                       # normalised
    s = seasonal_strength(y)
    assert s["seasonal_strength"] > 0.5 and s["trend_strength"] > 0.5
    r = residual_seasonality(d["seas_adj"])
    assert r["p"] > 0.05                                      # adjusted series has no calendar pattern left
    r_raw = residual_seasonality(y / y.rolling(12, center=True, min_periods=12).mean().bfill())
    assert r_raw["p"] < 0.05                                  # the raw detrended series does


def test_report_battery_has_the_expected_sections():
    rng = np.random.default_rng(3)
    y = pd.Series(100 + rng.normal(0, 1, 120), index=_periods(120))
    r = report(y)
    assert {"adf", "kpss", "ljung_box_level", "seasonal_strength", "residual_seasonality"} <= set(r)
    assert r["adf"]["n"] > 60 and r["kpss"]["n"] == 120
