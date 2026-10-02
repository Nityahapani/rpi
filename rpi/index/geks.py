"""GEKS-Jevons multilateral index with rolling window + movement splice.

Used as a robustness check against chain drift from promotions / product churn.
For a complete panel, GEKS-Jevons equals the chained Jevons (Jevons is transitive);
the two diverge when the panel is unbalanced - the gap is a drift diagnostic.
"""
from __future__ import annotations
import numpy as np


def bilateral_log(lp: np.ndarray, min_matched: int = 2) -> np.ndarray:
    """B[s,t] = mean over quotes present at both s and t of (lp[t]-lp[s]); NaN if too few."""
    T = lp.shape[0]
    B = np.full((T, T), np.nan)
    for s in range(T):
        B[s, s] = 0.0
        for t in range(s + 1, T):
            d = lp[t] - lp[s]
            ok = ~np.isnan(d)
            if ok.sum() >= min_matched:
                B[s, t] = d[ok].mean()
                B[t, s] = -B[s, t]
    return B


def _geks_window(B: np.ndarray, idx: list[int]) -> np.ndarray:
    """Log GEKS levels (relative to idx[0]) for periods in idx, using only that window."""
    b0 = idx[0]
    out = np.full(len(idx), np.nan)
    for k, t in enumerate(idx):
        vals = []
        for l in idx:
            a, b = B[b0, l], B[l, t]
            if not (np.isnan(a) or np.isnan(b)):
                vals.append(a + b)
        if vals:
            out[k] = np.mean(vals)
    return out


def geks_rel(lp: np.ndarray, window: int = 13, min_matched: int = 2):
    """Return (rel[T], n[T]) of log relatives implied by a rolling GEKS-Jevons index."""
    T = lp.shape[0]
    n = np.array([int(np.sum(~np.isnan(lp[t]))) for t in range(T)])
    rel = np.full(T, np.nan)
    live = np.flatnonzero(n >= 1)
    if live.size == 0:
        return rel, n
    # Leading periods with no quote at all (a panel stretched by pre-base register events) must not poison the window:
    # with b0 empty every bilateral comparison to the window base is NaN and the whole index collapses to NaN.
    t0 = int(live[0])
    sub = lp[t0:]
    r_sub, _ = _geks_core(sub, window, min_matched)
    rel[t0:] = r_sub
    return rel, n


def _geks_core(lp: np.ndarray, window: int, min_matched: int):
    T = lp.shape[0]
    B = bilateral_log(lp, min_matched)
    level = np.full(T, np.nan)
    w = min(window, T)
    first = _geks_window(B, list(range(w)))
    level[:w] = first
    for end in range(w, T):
        idx = list(range(end - w + 1, end + 1))
        g = _geks_window(B, idx)
        prev, cur = g[-2], g[-1]
        if np.isnan(prev) or np.isnan(cur) or np.isnan(level[end - 1]):
            level[end] = np.nan
        else:
            level[end] = level[end - 1] + (cur - prev)
    rel = np.full(T, np.nan)
    rel[0] = 0.0
    rel[1:] = level[1:] - level[:-1]
    return rel, None
