"""One-factor dynamic model estimated by maximum likelihood with a Kalman filter.

State:       f_t = phi * f_{t-1} + eta_t,   eta_t ~ N(0, 1)   (scale fixed by the variance of eta)
Observation: y_it = mu_i + lambda_i * f_t + eps_it,  eps_it ~ N(0, h_i)
NaN observations are skipped in the update step, so the model is exact on ragged panels.
Pure numpy/scipy: no statsmodels dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

LOG2PI = np.log(2.0 * np.pi)


@dataclass
class DFMParams:
    mu: np.ndarray       # (n,) series means
    lam: np.ndarray      # (n,) loadings
    h: np.ndarray        # (n,) idiosyncratic variances
    phi: float           # factor AR(1) coefficient, |phi| < 1


@dataclass
class Filtered:
    a: np.ndarray        # (T,) filtered factor mean E[f_t | y_1..t]
    P: np.ndarray        # (T,) filtered factor variance
    a_pred: np.ndarray   # (T,) one-step prediction E[f_t | y_1..t-1]
    P_pred: np.ndarray   # (T,) one-step prediction variance
    loglik: float


def _unpack(x: np.ndarray, n: int, mu: np.ndarray) -> DFMParams:
    return DFMParams(mu=mu, lam=x[:n], h=np.exp(x[n:2 * n]), phi=float(np.tanh(x[2 * n])))


def kalman(y: np.ndarray, p: DFMParams) -> Filtered:
    """Filter a (T, n) array; NaN marks a missing observation."""
    T, _ = y.shape
    x = y - p.mu
    a_prev = 0.0
    P_prev = 1.0 / (1.0 - p.phi ** 2)     # stationary prior for f_0
    a_out, P_out = np.zeros(T), np.zeros(T)
    a_pred, P_pred = np.zeros(T), np.zeros(T)
    ll = 0.0
    for t in range(T):
        a_p = p.phi * a_prev
        P_p = p.phi ** 2 * P_prev + 1.0
        a_pred[t], P_pred[t] = a_p, P_p
        obs = ~np.isnan(x[t])
        m = int(obs.sum())
        if m == 0:
            a_prev, P_prev = a_p, P_p
        else:
            lam = p.lam[obs]
            v = x[t, obs] - lam * a_p
            F = P_p * np.outer(lam, lam) + np.diag(p.h[obs])
            L = np.linalg.cholesky(F)
            z = np.linalg.solve(L, v)
            ll += -0.5 * (m * LOG2PI + 2.0 * np.log(np.diag(L)).sum() + z @ z)
            Fi_lam = np.linalg.solve(F, lam)
            a_prev = a_p + P_p * (Fi_lam @ v)
            P_prev = P_p - P_p * P_p * (lam @ Fi_lam)
        a_out[t], P_out[t] = a_prev, P_prev
    return Filtered(a=a_out, P=P_out, a_pred=a_pred, P_pred=P_pred, loglik=float(ll))


def fit(y: np.ndarray, starts: int = 4, seed: int = 0) -> tuple[DFMParams, Filtered]:
    """Maximum likelihood fit on a (T, n) array with NaNs for missing values."""
    _, n = y.shape
    mu = np.nanmean(y, axis=0)
    centred = y - mu
    sd = np.nanstd(centred, axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    rng = np.random.default_rng(seed)

    def negll(x: np.ndarray) -> float:
        val = kalman(y, _unpack(x, n, mu)).loglik
        return -val if np.isfinite(val) else 1e12

    bounds = [(None, None)] * n + [(np.log(1e-6), np.log(1e4))] * n + [(-2.5, 2.5)]
    best = None
    for s in range(max(1, starts)):
        signs = np.ones(n) if s == 0 else rng.choice([-1.0, 1.0], size=n)
        x0 = np.concatenate([signs * sd / sd.mean(),
                             np.log(0.5 * sd ** 2 + 1e-4),
                             [0.3 if s == 0 else rng.normal(0.0, 0.5)]])
        res = minimize(negll, x0, method="L-BFGS-B", bounds=bounds)
        if best is None or res.fun < best.fun:
            best = res
    params = _unpack(best.x, n, mu)
    # the factor has no natural sign: make the largest loading positive
    if params.lam[np.argmax(np.abs(params.lam))] < 0:
        params = DFMParams(mu=mu, lam=-params.lam, h=params.h, phi=params.phi)
    return params, kalman(y, params)


def cusum(y: np.ndarray, p: DFMParams, f: Filtered, level: float = 0.948) -> dict[int, dict | None]:
    """Per-series CUSUM of standardised one-step prediction errors.

    Approximate: boundary level*(1 + 2r) with r = t/T (Brown-Durbin-Evans form). Indicative only
    on short samples, where it has little power.
    """
    x = y - p.mu
    out: dict[int, dict | None] = {}
    for i in range(y.shape[1]):
        ok = ~np.isnan(x[:, i])
        if ok.sum() < 3:
            out[i] = None
            continue
        e = (x[ok, i] - p.lam[i] * f.a_pred[ok]) / np.sqrt(p.lam[i] ** 2 * f.P_pred[ok] + p.h[i])
        k = len(e)
        W = np.cumsum(e) / np.sqrt(k)
        r = np.arange(1, k + 1) / k
        breach = np.where(np.abs(W) > level * (1.0 + 2.0 * r))[0]
        out[i] = {"max_abs": float(np.max(np.abs(W))),
                  "first_breach_index": int(breach[0]) if breach.size else None,
                  "n": k}
    return out
