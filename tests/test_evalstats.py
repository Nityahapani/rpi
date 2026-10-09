"""Behavioural tests for rpi/evalstats.py on constructed cases with known answers."""
import numpy as np
import pytest

from rpi.evalstats import (calibrate, clark_west, dm_test, interval_scores, mincer_zarnowitz,
                           pit_uniformity, walk_forward_quantiles)


def test_dm_prefers_the_better_forecast_and_is_symmetric():
    rng = np.random.default_rng(0)
    actual = rng.normal(0, 1, 240)
    good = actual + rng.normal(0, 0.4, 240)
    bad = actual + rng.normal(0, 1.2, 240)
    d = dm_test(good - actual, bad - actual, h=1)
    assert d["t_hln"] < 0 and d["p_two_sided"] < 1e-6 and d["favours"] == "first"
    flipped = dm_test(bad - actual, good - actual, h=1)
    assert flipped["p_two_sided"] == pytest.approx(d["p_two_sided"], rel=1e-9)


def test_dm_hln_is_conservative_at_small_n():
    rng = np.random.default_rng(1)
    e1, e2 = rng.normal(0, 0.5, 12), rng.normal(0, 1.0, 12)
    d = dm_test(e1, e2, h=1)
    assert abs(d["t_hln"]) <= abs(d["t"])          # HLN shrinks the statistic toward zero


def test_mincer_zarnowitz_recovers_the_calibration_line():
    rng = np.random.default_rng(2)
    f = rng.normal(0.005, 0.01, 400)
    a_hat = f + rng.normal(0, 0.0005, 400)
    mz = mincer_zarnowitz(a_hat, f)
    assert abs(mz["a"]) < 0.001 and abs(mz["b"] - 1) < 0.05 and mz["p_joint"] > 0.02
    biased = mincer_zarnowitz(f - 0.01, f)         # forecast systematically too low
    assert biased["p_joint"] < 1e-6 and biased["b"] == pytest.approx(1.0, abs=0.05)


def test_clark_west_size_and_power_in_its_own_nesting_setup():
    """CW compares a LARGER model to a NESTED one: under H0 the larger model's extra signal has zero coefficient.

    Null shape: y = m + e, small = m, large = m + w with w independent of y  =>  adj = 2*e*w, E[adj] = 0.
    Alternative: the small model omits a real driver (f_small = 0), the large model captures it.
    """
    rng = np.random.default_rng(3)
    n = 400
    # --- size: no evidence for the larger model when its extra term is pure noise
    ts = []
    for _ in range(60):
        m = rng.normal(0, 0.01, n)
        y = m + rng.normal(0, 0.01, n)
        w = rng.normal(0, 0.01, n)
        ts.append(clark_west(y, m, m + w, h=1)["t"])
    ts = np.array(ts)
    assert np.mean(ts > 1.645) < 0.15                  # roughly nominal one-sided size
    # --- power: the larger model captures a driver the nested one misses
    z = rng.normal(0, 1, n)
    y = 3.0 * z + rng.normal(0, 1, n)
    cw = clark_west(y, np.zeros(n), 3.0 * z, h=1)
    assert cw["t"] > 5 and cw["p_one_sided"] < 1e-4 and cw["favours"] == "larger"


def test_walk_forward_and_calibration_on_a_calibrated_forecaster():
    """If errors are really N(0,1) and the machine only knows past errors, coverage should come out near nominal."""
    rng = np.random.default_rng(4)
    e = rng.normal(0, 1, 600)
    Q = walk_forward_quantiles(e, np.linspace(0.05, 0.95, 19), min_train=50)
    for alpha in (0.10, 0.05):
        s = interval_scores(e[50:], Q[50:], np.linspace(0.05, 0.95, 19), alpha)
        assert abs(s["coverage"] - (1 - alpha)) < 0.06
        assert s["mean_interval_score"] > 0 and s["crps"] > 0
    cal = calibrate(e, min_train=50)
    assert set(cal) >= {"alpha_0.1", "alpha_0.05", "pit", "taus"}
    assert abs(cal["alpha_0.05"]["coverage"] - 0.95) < 0.06


def test_calibration_flags_an_overconfident_forecaster():
    """A forecaster whose stated band is far too narrow must show below-nominal coverage and u-shaped PIT."""
    rng = np.random.default_rng(5)
    e = rng.normal(0, 1, 400)
    narrow = np.column_stack([np.full(400, -0.3), np.zeros(400), np.full(400, 0.3)])   # too tight vs sd 1
    s = interval_scores(e, narrow, np.array([0.05, 0.5, 0.95]), 0.10)
    assert s["coverage"] < 0.5                      # nominal 90%
    assert s["below_pct"] > 0.2 or s["above_pct"] > 0.2


def test_pit_uniformity_accepts_iid_and_rejects_a_shifting_forecast():
    rng = np.random.default_rng(6)
    e = rng.normal(0, 1, 500)
    p_ok = pit_uniformity(e, min_train=50)
    assert p_ok["p_uniform"] > 0.01
    drift = np.concatenate([np.zeros(250), np.full(250, 4.0)]) + rng.normal(0, 0.2, 500)
    p_bad = pit_uniformity(drift, min_train=50)
    assert p_bad["p_uniform"] < 1e-6


def test_bh_fdr_is_monotone_and_controls_the_family():
    from rpi.evalstats import bh_fdr
    p = [0.001, 0.008, 0.02, 0.04, 0.2, 0.6, 0.9]
    q = bh_fdr(p)
    assert all(q[i] <= q[i + 1] + 1e-12 for i in range(len(q) - 1))       # monotone
    assert all(qi >= pi - 1e-12 for qi, pi in zip(q, p))                  # never below the raw p
    assert q[0] < 0.05 and q[-1] >= 0.9
    assert np.isnan(bh_fdr([np.nan, 0.5])[0])
