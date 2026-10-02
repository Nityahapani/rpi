"""Bootstrap uncertainty: resample quotes within each item (captures outlet/SKU sampling error).

Does NOT capture item-selection or weight error - say so in any publication.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .elementary import rel_from_lp
from .aggregate import aggregate


def bootstrap_total(arrays: dict, periods, items, weights, reps=200, seed=7, min_matched=2, clip=0.7, impute="division"):
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
        out.append(aggregate(rel, n, items, weights, min_matched, impute=impute)["total"].to_numpy())
    arr = np.array(out)
    return (pd.Series(np.nanpercentile(arr, 2.5, axis=0), index=periods),
            pd.Series(np.nanpercentile(arr, 97.5, axis=0), index=periods))
