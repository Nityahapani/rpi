"""Elementary (item-level) price relatives.

Matched-model Jevons: for each month-pair, the item relative is the geometric mean of
price relatives over quotes observed in BOTH months. Robust to SKU churn and stock-outs.
Relatives are returned in logs. Monthly chaining happens after imputation (see aggregate.py)
so that missing items never cause level jumps.
"""
from __future__ import annotations
import numpy as np


def rel_from_lp(lp: np.ndarray, min_matched: int = 2, clip: float = 0.7):
    """lp: (T x Q) log prices. Returns (rel[T], n[T]).

    rel[0] = 0 by definition (base). rel[t] = mean over matched quotes of clip(lp[t]-lp[t-1]),
    NaN when fewer than `min_matched` matched quotes. n[t] = number of matched quotes
    (n[0] = number of quotes observed in the base period).
    """
    T = lp.shape[0]
    rel = np.full(T, np.nan)
    n = np.zeros(T, dtype=int)
    rel[0] = 0.0
    n[0] = int(np.sum(~np.isnan(lp[0]))) if lp.shape[1] else 0
    if T > 1 and lp.shape[1]:
        d = lp[1:] - lp[:-1]
        ok = ~np.isnan(d)
        n[1:] = ok.sum(axis=1)
        d = np.clip(d, -clip, clip)
        s = np.where(ok, d, 0.0).sum(axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = s / np.where(n[1:] > 0, n[1:], 1)
        rel[1:] = np.where(n[1:] >= min_matched, r, np.nan)
    return rel, n
