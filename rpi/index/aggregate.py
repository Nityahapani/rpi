"""Upper-level aggregation: relative imputation + Young (fixed-weight) index.

Missing item relatives are imputed with the weighted mean (log) relative of observed items in the
same division (fallback: all observed items). Imputing RELATIVES, not levels, keeps the chain
consistent. Every imputation is flagged and reported as a weight-coverage diagnostic.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def impute_relatives(rel: pd.DataFrame, observed: pd.DataFrame, items: pd.DataFrame, w: pd.Series,
                     method: str = "division", trend_window: int = 12, min_history: int = 3, seasonal: dict | None = None):
    """rel/observed: (periods x items). Returns (rel_filled, imputed_flags).

    method="division": a missing relative takes the weighted mean relative of observed items in its division.
    method="own_trend": it takes the MEAN of the item's own last `trend_window` (12) genuinely observed relatives (its
        long-run drift; items with < min_history observations fall back to the division mean). Back-test on the 20 months of
        official Gujarat-urban item indices (one-month-ahead, n=12): total RMSE 0.63 pp vs 0.74 pp for zero change and
        0.74 pp for a 3-month median; short trend windows extrapolate noise (item-level RMSE 4.5 pp vs 3.6 pp for zero).
        This stops a discrete
        administered step in one item (e.g. a PNG tariff hike) from being smeared onto unrelated items such as rent
        in months where the official index has not been published yet (nowcast months).

    method="seasonal_trend": like own_trend, but a TRAILING gap (nowcast month) of an item that has a seasonal table (rpi/seasonal.py: long-run mean monthly change plus EB-shrunk
        calendar-month deviation from 11 years of official Gujarat-urban data) is filled with that prior; other items fall back to own_trend.
        Pseudo-real-time test (2023-2025, untouched): index RMSE 0.61 vs 0.85 pp (1 month), 0.95 vs 1.43 pp (2 months), DM p <= 0.001.
    """
    cols = list(rel.columns)
    n_p = len(rel.index)
    rel_np = rel.to_numpy(dtype=float)
    obs_np = observed.reindex(columns=cols).to_numpy(dtype=bool)
    w_np = w.reindex(cols).to_numpy(dtype=float)
    div_np = items.set_index("item_id")["division"].reindex(cols).to_numpy(dtype=object)

    filled = rel_np.copy()
    imp_np = np.zeros(rel_np.shape, dtype=bool)
    # A cell with a NaN division belonged to no `div == d` group in the scalar loop and so was never filled; keep that.
    groups = [np.flatnonzero(div_np == d) for d in pd.unique(div_np) if d == d]

    kcount = tmean = has_seas = seas_val = last_obs = None
    if method in ("own_trend", "seasonal_trend"):
        # Per item: count and mean of the last `trend_window` OBSERVED relatives strictly before t (excluding row 0),
        # precomputed with prefix sums; the scalar loop below then needs no pandas slicing.
        kcount = np.zeros((n_p, len(cols)), dtype=int)
        tmean = np.full((n_p, len(cols)), np.nan)
        for j in range(len(cols)):
            ok = obs_np[1:, j] & ~np.isnan(rel_np[1:, j])
            pos_c = np.flatnonzero(ok) + 1
            vals = rel_np[pos_c, j]
            k = np.searchsorted(pos_c, np.arange(n_p))
            kcount[:, j] = k
            lo = np.maximum(0, k - trend_window)
            if len(vals):
                cs = np.concatenate([[0.0], np.cumsum(vals)])
                tmean[:, j] = np.where(k > 0, (cs[k] - cs[lo]) / np.maximum(k - lo, 1), np.nan)
        last_obs = np.where(obs_np.any(axis=0), n_p - 1 - np.argmax(obs_np[::-1, :], axis=0), -1)
        has_seas = np.zeros((n_p, len(cols)), dtype=bool)
        seas_val = np.full((n_p, len(cols)), np.nan)
        if method == "seasonal_trend" and seasonal:
            months = np.array([p.month for p in rel.index])
            for j, c in enumerate(cols):
                if c in seasonal:
                    clim, seas = seasonal[c]
                    has_seas[:, j] = True
                    seas_val[:, j] = clim + seas[months - 1]

    for t in range(n_p):
        obs = obs_np[t] & ~np.isnan(rel_np[t])
        if obs.all():
            continue
        pos_all = np.flatnonzero(obs)
        overall = float(np.average(rel_np[t, pos_all], weights=w_np[pos_all])) if len(pos_all) else 0.0
        for g in groups:
            o = obs[g]
            val = float(np.average(rel_np[t, g[o]], weights=w_np[g[o]])) if o.any() else overall
            miss = g[~o]
            if len(miss) == 0:
                continue
            filled[t, miss] = val
            imp_np[t, miss] = True
            if kcount is not None:
                for j in miss:
                    # Only TRAILING gaps (no observation of the item in any later month) are forecasts, which is what the prior was tested for;
                    # an interior gap (e.g. the splice month where an independent feed starts) has later data and keeps the own-trend rule.
                    if has_seas[t, j] and last_obs[j] <= t:
                        filled[t, j] = seas_val[t, j]
                    elif kcount[t, j] >= min_history:
                        filled[t, j] = tmean[t, j]
    return pd.DataFrame(filled, index=rel.index, columns=cols), pd.DataFrame(imp_np, index=rel.index, columns=cols)


def aggregate(rel: pd.DataFrame, n: pd.DataFrame, items: pd.DataFrame, weights: pd.Series,
              min_matched=2, impute: str = "division", seasonal: dict | None = None):
    """rel, n: (periods x items) log relatives and matched counts.
    Returns dict(total, divisions, items, coverage, coverage_by_tier, imputed)."""
    cols = [c for c in weights.index if c in set(items["item_id"])]
    rel = rel.reindex(columns=cols)
    n = n.reindex(columns=cols).fillna(0)
    w = weights.reindex(cols)
    mm = min_matched if isinstance(min_matched, pd.Series) else pd.Series(min_matched, index=cols)
    mm = mm.reindex(cols).fillna(2)
    observed = n.ge(mm, axis=1) & rel.notna()
    observed.iloc[0] = n.iloc[0].ge(1) & rel.iloc[0].notna()      # base period: need >=1 quote
    filled, imputed = impute_relatives(rel, observed, items, w, method=impute, seasonal=seasonal)
    filled.iloc[0] = 0.0
    levels = 100.0 * np.exp(filled.cumsum())
    div = items.set_index("item_id")["division"].reindex(cols)
    total = (levels * w).sum(axis=1) / w.sum()
    divisions = pd.DataFrame({
        d: (levels[div.index[div == d]] * w[div == d]).sum(axis=1) / w[div == d].sum()
        for d in sorted(div.unique())})
    tier = items.set_index("item_id")["tier"].reindex(cols)
    cov = (observed * w).sum(axis=1) / w.sum()
    cov_tier = pd.DataFrame({
        t: (observed.loc[:, tier.index[tier == t]] * w[tier == t]).sum(axis=1) / w.sum()
        for t in sorted(tier.unique())})
    return dict(total=total, divisions=divisions, items=levels, coverage=cov,
                coverage_by_tier=cov_tier, imputed=imputed)


def rebase(df, base_period):
    """Rebase so that base_period == 100."""
    return df / df.loc[base_period] * 100.0
