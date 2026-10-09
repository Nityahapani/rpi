"""Bootstrap uncertainty with SEPARABLE components.

Three sources of error are resampled independently so their contributions can be reported separately:

* ``quotes``      - resample the quote columns within each item (outlet/SKU sampling error). This is the component the
                    published 95% band has always used; the RNG draw order for this component is unchanged, so a
                    quotes-only run reproduces the historical band exactly.
* ``items``       - resample which item-month cells are observed, at each item's historical observation rate
                    (selection / availability error: an item that is missing in a month is filled by the engine's
                    imputation rules, so its weight is carried by a modelled value).
* ``weights``     - multiply each item weight by lognormal noise, sd = ``weight_sigma`` in log points (weight error:
                    the hierarchical fit in rpi/hierweights.py recovers MoSPI's shares with finite precision, and
                    the item weights are a modelled object, not a published one).

The published CI is a LEVEL band and the honest summary of what it covers is the variance decomposition in
``data/official/uncertainty_decomposition.json`` (written by ``rpi uncertainty``). It does NOT cover the error in the
fill rules used for nowcast months - that is measured separately, in real time, by ``rpi.panel_eval`` (coverage of the
nowcast band) - nor model error in the seasonal prior itself.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .elementary import rel_from_lp
from .aggregate import aggregate

COMPONENTS = ("quotes", "items", "weights")


def _min_matched_for(items_df, weights, min_matched):
    if isinstance(min_matched, pd.Series):
        return min_matched
    return pd.Series(min_matched, index=weights.index)


def _availability_from(rel0: pd.DataFrame, n0: pd.DataFrame, mm: pd.Series) -> pd.Series:
    """Historical observation rate per item (share of months where the item had enough matched quotes)."""
    observed = n0.ge(mm, axis=1) & rel0.notna()
    observed.iloc[0] = n0.iloc[0].ge(1) & rel0.iloc[0].notna()
    return observed.mean(axis=0).reindex(rel0.columns).fillna(0.0)


def bootstrap_replicates(arrays: dict, periods, items, weights, reps: int = 1000, *,
                         components: tuple = ("quotes",), min_matched=2, clip: float = 0.7,
                         impute: str = "division", seasonal: dict | None = None,
                         weight_sigma: float = 0.10, availability: pd.Series | None = None,
                         mask_from=None, seed: int = 7) -> np.ndarray:
    """Return a (reps x periods) array of the total index level from each replicate. See module docstring.

    `mask_from` (a monthly Period) restricts the item-availability component to months >= it - normally the month
    after the last official release, which is where items are genuinely unobserved in the published vintage.
    Without it, every month is masked at the item's historical observation rate, which also measures how much the
    level PATH would have moved had earlier months been missed - a real question, but a bigger one than the tail.
    """
    bad = [c for c in components if c not in COMPONENTS]
    if bad:
        raise ValueError(f"unknown bootstrap component(s): {bad}")
    rng = np.random.default_rng(seed)
    cols = sorted(arrays)
    mm = _min_matched_for(items, weights, min_matched).reindex(cols).fillna(2)
    # NB: `weights` is passed to aggregate unchanged - items that carry weight but have no quotes are imputed by
    # aggregate exactly as in the historical bootstrap; dropping them here would silently change the index level.

    if "items" in components and availability is None:
        rel0 = pd.DataFrame(np.nan, index=periods, columns=cols)
        n0 = pd.DataFrame(0, index=periods, columns=cols)
        for it, lp in arrays.items():
            mm_i = int(mm[it])
            r, k = rel_from_lp(lp, mm_i, clip)
            rel0[it], n0[it] = r, k
        availability = _availability_from(rel0, n0, mm)
    if availability is not None:
        availability = availability.reindex(cols).fillna(1.0).to_numpy(float)

    out = []
    for _ in range(reps):
        rel = pd.DataFrame(np.nan, index=periods, columns=cols)
        n = pd.DataFrame(0, index=periods, columns=cols)
        for it, lp in arrays.items():
            Q = lp.shape[1]
            take = rng.integers(0, Q, Q) if Q else []
            r, k = rel_from_lp(lp[:, take] if Q else lp, int(mm[it]), clip)
            rel[it], n[it] = r, k
        if availability is not None:
            keep = rng.random((len(periods), len(cols))) < availability
            if mask_from is not None:
                keep = keep | (np.asarray(periods < mask_from)[:, None])
            rel = rel.where(keep, np.nan)
            n = n.where(keep, 0)
        w = weights
        if "weights" in components:
            w = weights * np.exp(weight_sigma * rng.standard_normal(len(weights)))
        tot = aggregate(rel, n, items, w, min_matched, impute=impute, seasonal=seasonal)["total"].to_numpy()
        out.append(tot)
    return np.array(out)


def bootstrap_total(arrays: dict, periods, items, weights, reps=200, seed=7, min_matched=2, clip=0.7,
                    impute="division", seasonal=None):
    """Quotes-only bootstrap (historical behaviour, unchanged draws): returns (lo, hi) 2.5/97.5 percentiles."""
    arr = bootstrap_replicates(arrays, periods, items, weights, reps, components=("quotes",),
                               min_matched=min_matched, clip=clip, impute=impute, seasonal=seasonal, seed=seed)
    return (pd.Series(np.nanpercentile(arr, 2.5, axis=0), index=periods),
            pd.Series(np.nanpercentile(arr, 97.5, axis=0), index=periods))


def quantiles(arr: np.ndarray, qs=(2.5, 97.5)) -> tuple[np.ndarray, ...]:
    return tuple(np.nanpercentile(arr, q, axis=0) for q in qs)


def mc_quantile_error(arr: np.ndarray, qs=(2.5, 97.5), splits: int = 100, seed: int = 99) -> dict:
    """Monte-Carlo standard error of each percentile, from `splits` half-sample reruns (se = sd of the split quantiles / sqrt(2))."""
    rng = np.random.default_rng(seed)
    n = arr.shape[0]
    half = n // 2
    draws = {q: [] for q in qs}
    for _ in range(splits):
        idx = rng.choice(n, size=half, replace=False)
        for q in qs:
            draws[q].append(np.nanpercentile(arr[idx], q, axis=0))
    out = {}
    for q in qs:
        d = np.array(draws[q])
        out[str(q)] = np.nanstd(d, axis=0, ddof=1) / np.sqrt(2.0)
    return out


def variance_decomposition(runs: dict[str, np.ndarray], period_index: int = -1) -> dict:
    """Variance shares from single-component runs plus their combination. `runs` maps component name -> (reps x periods) array.

    Each single-component run turns ONE component on and the others off, so the variances are marginal. They need not
    add up to the combined variance: item masking blanks cells that the quotes component would otherwise resample, so
    the combination is typically SUB-additive. The gap is reported (`additivity_gap`) rather than hidden; the shares are
    normalised on the marginal variances.
    """
    v = {k: float(np.nanvar(a[:, period_index])) for k, a in runs.items()}
    singles = {k: v.get(k, np.nan) for k in COMPONENTS}
    s = float(np.nansum(list(singles.values())))
    shares = {k: (100.0 * x / s if s and x == x else np.nan) for k, x in singles.items()}
    combined = float(v.get("all", np.nan))
    return {"var": v, "singles": singles, "singles_sum": s, "shares_pct": shares,
            "combined_var": combined, "additivity_gap": combined - s if combined == combined else np.nan,
            "additivity_gap_pct": (100.0 * (combined - s) / s if s else np.nan),
            "note": "marginal single-component variances, normalised; sub-additive gaps are expected because item "
                    "masking removes the cells the quotes component would resample"}
