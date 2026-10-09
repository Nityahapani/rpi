"""Forecast-evaluation statistics shared by the pseudo-real-time exercises (rpi.panel_eval, rpi.nowcast_eval).

Everything here works on ARRAYS OF ERRORS (forecast - actual), so the same code scores the 11-year panel replay
(item-level and index-level) and the live vintage log. Conventions:

* DM (Diebold-Mariano, 1995, squared-error loss) with the h-step autocovariance estimator and the
  Harvey-Leybourne-Newbold (1997) small-sample correction; the corrected statistic is compared with t_{n-1}
  (HLN's recommended practice). Negative t favours the FIRST forecast.
* MZ (Mincer-Zarnowitz): regress actual on forecast; a *useful* forecast has a=0, b=1. Estimated with
  Newey-West HAC errors (lag h-1) because h-step errors overlap; joint Wald test of (a,b)=(0,1).
* CW (Clark-West, 2007): one-sided test for a LARGER model against a NESTED one, correcting for the
  downward bias of the MSE comparison. Only valid for nested pairs.
* Calibration: the walk-forward (expanding-window) empirical quantiles of past errors form the predictive
  distribution at each origin - distribution-free, no fitted distribution. From them: realised coverage of a
  central interval, PIT uniformity (chi-square on 10 bins), interval score and CRPS (pinball-loss integral).
"""
from __future__ import annotations

import numpy as np
from scipy import stats


def _clean(*arrays):
    a = [np.asarray(x, dtype=float).ravel() for x in arrays]
    m = np.ones(len(a[0]), dtype=bool)
    for x in a:
        m &= ~np.isnan(x)
    return [x[m] for x in a] if len(a) > 1 else a[0][m]


def newey_west_se(d: np.ndarray, lags: int = 0) -> float:
    """SE of the mean of a series with Bartlett-kernel HAC variance (lags = overlap-1 for h-step errors)."""
    d = np.asarray(d, float)
    n = len(d)
    if n < 2:
        return np.nan
    m = d.mean()
    s = float(((d - m) ** 2).mean())
    for k in range(1, min(lags, n - 1) + 1):
        c = float(((d[k:] - m) * (d[:-k] - m)).mean())
        s += 2.0 * (1.0 - k / (lags + 1.0)) * c
    return float(np.sqrt(max(s, 1e-300) / n))


def bh_fdr(pvalues, alpha: float = 0.05) -> list[float]:
    """Benjamini-Hochberg q-values for a FAMILY of tests (prevents the "one of 54 comparisons came out at p=0.04"
    problem). Pre-specify the family - here, the DM comparisons within one horizon and one index framing.
    Returns q-values aligned with the input order; NaN p-values pass through as NaN.
    """
    p = np.asarray(pvalues, float)
    ok = ~np.isnan(p)
    q = np.full(p.shape, np.nan, dtype=float)
    idx = np.flatnonzero(ok)
    if not len(idx):
        return list(q)
    order = idx[np.argsort(p[idx])]
    m = len(order)
    prev = 1.0
    for rank, i in enumerate(order[::-1], start=1):     # walk from the largest p, enforce monotonicity
        prev = min(prev, p[i] * m / (m - rank + 1))
        q[i] = prev
    return list(q)


def dm_test(e1, e2, h: int = 1, hln: bool = True) -> dict:
    """Diebold-Mariano on squared-error loss; e1 = candidate, e2 = benchmark. Negative t favours e1."""
    e1, e2 = _clean(e1, e2)
    n = len(e1)
    if n < 4:
        return {"n": n, "t": np.nan, "p_two_sided": np.nan, "note": "too few paired errors"}
    d = e1 ** 2 - e2 ** 2
    se = newey_west_se(d, lags=max(0, h - 1))
    t = float(d.mean() / se) if se > 0 else np.nan
    t_hln = t * float(np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)) if hln else t
    p = 2.0 * float(stats.t.sf(abs(t_hln), df=n - 1))
    return {"n": n, "mean_loss_diff": float(d.mean()), "t": t, "t_hln": t_hln, "p_two_sided": p,
            "favours": "first" if t_hln < 0 else "second",
            "note": "squared-error loss; Bartlett HAC (lag h-1)" + ("; Harvey-Leybourne-Newbold corrected, t_{n-1}" if hln else "")}


def mincer_zarnowitz(actual, forecast, h: int = 1) -> dict:
    """Regress actual = a + b*forecast + u with HAC errors; joint test of a=0, b=1."""
    actual, forecast = _clean(actual, forecast)
    n = len(actual)
    if n < 4 or np.allclose(forecast, forecast[0]):
        return {"n": n, "a": np.nan, "b": np.nan, "p_joint": np.nan, "note": "degenerate input"}
    X = np.column_stack([np.ones(n), forecast])
    beta, *_ = np.linalg.lstsq(X, actual, rcond=None)
    u = actual - X @ beta
    L = max(1, h - 1)
    G = X * u[:, None]
    S = G.T @ G
    for k in range(1, min(L, n - 1) + 1):
        w = 1.0 - k / (L + 1.0)
        Gk = G[k:].T @ G[:-k]
        S += w * (Gk + Gk.T)
    XtX_inv = np.linalg.inv(X.T @ X)
    V = XtX_inv @ S @ XtX_inv
    diff = np.array([beta[0], beta[1] - 1.0])
    W = float(diff @ np.linalg.solve(V, diff))
    p = float(stats.chi2.sf(W, df=2))
    r2 = 1.0 - float((u ** 2).sum() / ((actual - actual.mean()) ** 2).sum()) if actual.std() > 0 else np.nan
    return {"n": n, "a": float(beta[0]), "b": float(beta[1]), "se_a": float(np.sqrt(V[0, 0])),
            "se_b": float(np.sqrt(V[1, 1])), "wald": W, "p_joint": p, "r2": r2,
            "note": "HAC (lag h-1); b<1 = forecast too variable, b>1 = too smooth"}


def clark_west(actual, f_nested, f_large, h: int = 1) -> dict:
    """One-sided Clark-West test that the LARGER (encompassing) forecast beats the nested one."""
    actual, f_nested, f_large = _clean(actual, f_nested, f_large)
    n = len(actual)
    if n < 4:
        return {"n": n, "t": np.nan, "p_one_sided": np.nan}
    adj = (actual - f_nested) ** 2 - ((actual - f_large) ** 2 - (f_large - f_nested) ** 2)
    se = newey_west_se(adj, lags=max(0, h - 1))
    t = float(adj.mean() / se) if se > 0 else np.nan
    return {"n": n, "t": t, "p_one_sided": float(stats.t.sf(t, df=n - 1)),
            "favours": "larger" if t > 0 else "nested",
            "note": "one-sided; valid only for nested models"}


# ---- calibration of a predictive distribution built from past errors (walk-forward, distribution-free) ------------------
def walk_forward_quantiles(errors: np.ndarray, taus, min_train: int = 12, expanding: bool = True, window: int | None = None) -> np.ndarray:
    """For each origin i >= min_train return the empirical quantiles of the errors BEFORE i. Shape (n, len(taus))."""
    e = np.asarray(errors, float)
    n = len(e)
    out = np.full((n, len(taus)), np.nan)
    for i in range(min_train, n):
        past = e[:i] if expanding or window is None else e[max(0, i - window):i]
        past = past[~np.isnan(past)]
        if len(past) >= min_train:
            out[i] = np.quantile(past, taus)
    return out


def pit_uniformity(errors: np.ndarray, min_train: int = 12) -> dict:
    """PIT values = ECDF of past errors evaluated at the current error; chi-square test of uniformity (10 bins)."""
    e = np.asarray(errors, float)
    pits = []
    for i in range(min_train, len(e)):
        past = e[:i]
        past = past[~np.isnan(past)]
        if len(past) >= min_train and not np.isnan(e[i]):
            pits.append(float((past <= e[i]).mean()))
    pits = np.array(pits)
    if len(pits) < 20:
        return {"n": int(len(pits)), "p_uniform": np.nan}
    bins = np.clip((pits * 10).astype(int), 0, 9)
    cnt = np.bincount(bins, minlength=10)
    chi2 = float(((cnt - len(pits) / 10) ** 2 / (len(pits) / 10)).sum())
    return {"n": int(len(pits)), "chi2": chi2, "p_uniform": float(stats.chi2.sf(chi2, df=9)),
            "hist": [int(c) for c in cnt], "note": "PIT uniform => calibrated; u-shape => too narrow, hump => too wide"}


def interval_scores(errors: np.ndarray, quantiles: np.ndarray, taus, alpha: float) -> dict:
    """Coverage, mean interval score and CRPS (pinball integral) of the predictive distribution given by `quantiles`."""
    e = np.asarray(errors, float)
    Q = np.asarray(quantiles, float)
    taus = np.asarray(taus, float)
    ok = ~np.isnan(e) & ~np.isnan(Q).any(axis=1)
    e, Q = e[ok], Q[ok]
    n = len(e)
    if n == 0:
        return {"n": 0}
    i_lo = int(np.argmin(np.abs(taus - alpha / 2.0)))
    i_hi = int(np.argmin(np.abs(taus - (1.0 - alpha / 2.0))))
    lo, hi = Q[:, i_lo], Q[:, i_hi]
    inside = (e >= lo) & (e <= hi)
    width = hi - lo
    below, above = e < lo, e > hi
    iscore = width + (2.0 / alpha) * (lo - e) * below + (2.0 / alpha) * (e - hi) * above
    # pinball loss: mean over grid of tau * max(e - q, 0) + (1-tau) * max(q - e, 0); CRPS = 2 * integral over tau
    pin = taus[None, :] * np.maximum(e[:, None] - Q, 0.0) + (1.0 - taus)[None, :] * np.maximum(Q - e[:, None], 0.0)
    crps = 2.0 * float(np.trapezoid(pin.mean(axis=0), taus))
    return {"n": int(n), "coverage": float(inside.mean()), "nominal": float(1.0 - alpha),
            "mean_width": float(width.mean()), "mean_interval_score": float(iscore.mean()),
            "crps": float(crps), "below_pct": float(below.mean()), "above_pct": float(above.mean())}


def calibrate(errors: np.ndarray, taus_grid=(0.05, 0.95, 19), min_train: int = 12) -> dict:
    """Run the whole calibration battery for one error series: walk-forward quantiles -> coverage/PIT/IS/CRPS.

    `taus_grid` = (lo, hi, n) or an explicit sequence. Returns a dict with 90% and 95% central intervals, CRPS, PIT.
    """
    if isinstance(taus_grid, tuple):
        lo, hi, k = taus_grid
        taus = np.linspace(lo, hi, int(k))
    else:
        taus = np.asarray(taus_grid, float)
    Q = walk_forward_quantiles(errors, taus, min_train=min_train)
    out = {"taus": [round(float(t), 3) for t in taus]}
    for alpha in (0.10, 0.05):
        out[f"alpha_{alpha}"] = interval_scores(errors, Q, taus, alpha)
    out["pit"] = pit_uniformity(errors, min_train=min_train)
    return out
