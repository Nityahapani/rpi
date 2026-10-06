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
    div = items.set_index("item_id")["division"].reindex(rel.columns)
    filled = rel.copy()
    imputed = pd.DataFrame(False, index=rel.index, columns=rel.columns)
    for t in rel.index:
        obs = observed.loc[t] & rel.loc[t].notna()
        if obs.all():
            continue
        overall = np.average(rel.loc[t][obs], weights=w[obs]) if obs.any() else 0.0
        for d in div.unique():
            cols = div.index[div == d]
            o = obs[cols]
            val = np.average(rel.loc[t, cols][o], weights=w[cols][o]) if o.any() else overall
            miss = cols[~o.values]
            filled.loc[t, miss] = val
            imputed.loc[t, miss] = True
            if method in ("own_trend", "seasonal_trend"):
                pos = rel.index.get_loc(t)
                for c in miss:
                    # Only TRAILING gaps (no observation of the item in any later month) are forecasts, which is what the prior was tested for;
                    # an interior gap (e.g. the splice month where an independent feed starts) has later data and keeps the own-trend rule.
                    if method == "seasonal_trend" and seasonal and c in seasonal and not observed[c].iloc[pos + 1:].any():
                        clim, seas = seasonal[c]
                        filled.loc[t, c] = clim + float(seas[t.month - 1])
                        continue
                    hist = rel[c].iloc[1:pos][observed[c].iloc[1:pos].to_numpy()].dropna()
                    if len(hist) >= min_history:
                        filled.loc[t, c] = float(np.mean(hist.iloc[-trend_window:]))
    return filled, imputed


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
