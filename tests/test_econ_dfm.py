"""Tests for the econ module: Kalman filter correctness, estimation, bridge, and the real panel loader."""
import numpy as np
import pandas as pd
from scipy.stats import multivariate_normal

from econ import dfm, evaluate
from econ.data import load_panel


def _simulate(T=60, n=5, phi=0.7, seed=1):
    rng = np.random.default_rng(seed)
    lam = rng.uniform(0.5, 1.5, n)
    h = rng.uniform(0.05, 0.3, n)
    f = np.zeros(T)
    f[0] = rng.normal(0, np.sqrt(1 / (1 - phi ** 2)))
    for t in range(1, T):
        f[t] = phi * f[t - 1] + rng.normal()
    y = f[:, None] * lam + rng.normal(0, np.sqrt(h), (T, n))
    return y, dfm.DFMParams(mu=np.zeros(n), lam=lam, h=h, phi=phi), f


def _joint_loglik(y, p):
    """Exact log-likelihood by building the joint Gaussian of all observed values (brute force)."""
    T, n = y.shape
    # state covariance of f over time: Cov(f_s, f_t) = phi^|s-t| / (1 - phi^2)
    idx = [(t, i) for t in range(T) for i in range(n) if not np.isnan(y[t, i])]
    vals = np.array([y[t, i] - p.mu[i] for t, i in idx])
    m = len(idx)
    C = np.zeros((m, m))
    for a, (t, i) in enumerate(idx):
        for b, (s, j) in enumerate(idx):
            C[a, b] = p.lam[i] * p.lam[j] * p.phi ** abs(t - s) / (1 - p.phi ** 2)
            if a == b:
                C[a, b] += p.h[i]
    return multivariate_normal(mean=np.zeros(m), cov=C).logpdf(vals)


def test_kalman_loglik_matches_brute_force():
    y, p, _ = _simulate(T=12, n=3)
    assert np.isclose(dfm.kalman(y, p).loglik, _joint_loglik(y, p), rtol=1e-9)


def test_kalman_loglik_matches_brute_force_with_missing_values():
    y, p, _ = _simulate(T=12, n=3, seed=4)
    y[2, 0] = np.nan
    y[5, :2] = np.nan
    y[7, :] = np.nan
    assert np.isclose(dfm.kalman(y, p).loglik, _joint_loglik(y, p), rtol=1e-9)


def test_filter_tracks_the_true_factor():
    y, p, f = _simulate(T=200, n=8, seed=3)
    filt = dfm.kalman(y, p)
    corr = np.corrcoef(filt.a[20:], f[20:])[0, 1]
    assert corr > 0.9


def test_fit_recovers_persistence_and_signs():
    y, p, _ = _simulate(T=300, n=8, phi=0.7, seed=5)
    est, filt = dfm.fit(y, starts=3)
    assert abs(est.phi - 0.7) < 0.15
    # loadings identified up to sign; the largest is made positive by convention
    assert np.all(np.sign(est.lam) == np.sign(est.lam[np.argmax(np.abs(est.lam))]) * np.sign(p.lam))
    assert np.isfinite(filt.loglik)


def test_fit_handles_ragged_panel():
    y, _, _ = _simulate(T=80, n=4, seed=9)
    y[::3, 1] = np.nan
    y[10:20, 3] = np.nan
    est, filt = dfm.fit(y, starts=2)
    assert np.isfinite(filt.loglik) and np.all(est.h > 0)


def test_bridge_recovers_known_coefficients():
    idx = pd.period_range("2025-01", periods=30, freq="M").astype(str)
    rng = np.random.default_rng(0)
    f = pd.Series(rng.normal(size=30), index=idx)
    y = pd.Series(0.4 + 0.8 * f.values + rng.normal(0, 0.05, 30), index=idx)
    br = evaluate.fit_bridge(f, y)
    assert abs(br.alpha - 0.4) < 0.05 and abs(br.beta - 0.8) < 0.05


def test_real_panel_loads_and_aligns():
    p = load_panel()
    assert len(p.divisions) == 11
    assert abs(p.weights.sum() - 1.0) < 1e-9
    assert 0.0 < p.uncovered_weight < 0.05          # division 02 is the only official division not in rpi
    assert "2026-10" in p.periods and "2026-08" in p.official_mom.index


def test_anchored_ridge_returns_weights_when_data_match_them():
    from econ import combine
    rng = np.random.default_rng(2)
    w = np.array([0.5, 0.3, 0.2])
    X = rng.normal(size=(12, 3))
    y = X @ w + 0.01 * rng.normal(size=12)
    pred, _ = combine._anchored_ridge(X, y, w, np.array([1.0, -1.0, 2.0]))
    assert abs(pred - (np.array([1.0, -1.0, 2.0]) @ w)) < 0.05


def test_ewma_last_weights_recent_values_more():
    from econ import combine
    assert combine._ewma_last(np.array([0.0, 0.0, 10.0]), 1.0) > combine._ewma_last(np.array([10.0, 0.0, 0.0]), 1.0)
    assert combine._ewma_last(np.array([]), 3.0) == 0.0
