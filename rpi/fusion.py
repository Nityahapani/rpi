"""Fused best-estimate nowcast of the official-basis index (inventory AK).  NOT part of the independent index and NOT counted in the independent share.

The independent index uses each gated proxy one-for-one (beta = 1).  This module asks a different question: what is the best estimate of the official Gujarat-urban item change in
a month the official figure has not yet appeared, given (a) a seasonal prior built from 11 years of official history and (b) the proxy?  Per item and month, both are noisy
predictions of the same target, combined with inverse-variance weights (stacking of two forecasts, independent errors assumed):

    PRIOR   m_t = clim + shrunk calendar-month deviation                      error variance sp2  (pseudo-out-of-sample, years 2019-2024)
    PROXY   b * d_proxy_t                                                    error variance s2   b, s2 estimated on the item's own past (proxy, official) pairs,
                                                                             shrunk toward a prior slope b0 (1, or a pooled state slope) with weight n/(n+4) and toward
                                                                             the cross-item median residual variance with weight n/(n+4)
    FUSED   (m/sp2 + b d/s2) / (1/sp2 + 1/s2)

All rules, the shrinkage constant (4) and the origins are fixed before the backtest.  Items fed by administered prices (tariffs, spot metals, PNG) enter one-for-one (they ARE the
price); items with no independent source use the prior.  Index-level change = sum_i w_i * item change (base-month Young weights, price-updated).  Pure functions; runner is
scripts/fusion_backtest.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .seasonal import seasonal_table

NU = 4.0
MIN_PAIRS = 3
DIRECT_SOURCES = ("tariff", "gr_metals", "gr_png")
FLOOR_SD = 0.0025          # 0.25 pp monthly: no item is ever treated as exactly known


def build_tables(d2012: pd.DataFrame, mapping: pd.DataFrame, cutoff: str) -> dict:
    """item_id -> (clim, seas[12]) from the 2012-base Gujarat-urban history with periods <= cutoff."""
    P = d2012.pivot_table(index="period", columns="item", values="index_value").sort_index()
    P.index = pd.PeriodIndex(P.index, freq="M")
    P = P[P.index <= pd.Period(cutoff, freq="M")]
    P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M"))
    D = np.log(P.where(P > 0)).diff()
    out = {}
    for r in mapping.itertuples():
        if r.cpi2012_item in D.columns:
            t = seasonal_table(D[r.cpi2012_item])
            out[r.item_id] = (float(t.clim.iloc[0]), t.seas.to_numpy(float))
    return out


def prior_change(tables: dict, item: str, period: str) -> float:
    if item not in tables:
        return 0.0
    clim, seas = tables[item]
    return clim + float(seas[pd.Period(period, freq="M").month - 1])


def prior_sd(d2012: pd.DataFrame, mapping: pd.DataFrame, first_year=2019, last_year=2024) -> dict:
    """pseudo-out-of-sample SD of the prior's error: tables built with data before year y predict the months of y."""
    P = d2012.pivot_table(index="period", columns="item", values="index_value").sort_index()
    P.index = pd.PeriodIndex(P.index, freq="M")
    P = P.reindex(pd.period_range(P.index.min(), P.index.max(), freq="M"))
    D = np.log(P.where(P > 0)).diff()
    err: dict[str, list] = {}
    for y in range(first_year, last_year + 1):
        tabs = build_tables(d2012, mapping, f"{y - 1}-12")
        for r in mapping.itertuples():
            if r.item_id in tabs and r.cpi2012_item in D.columns:
                for m in range(1, 13):
                    per = pd.Period(f"{y}-{m:02d}", freq="M")
                    if per in D.index and D.loc[per, r.cpi2012_item] == D.loc[per, r.cpi2012_item]:
                        err.setdefault(r.item_id, []).append(float(D.loc[per, r.cpi2012_item]) - prior_change(tabs, r.item_id, str(per)))
    return {k: max(float(np.sqrt(np.mean(np.square(v)))), FLOOR_SD) for k, v in err.items() if len(v) >= 12}


def own_fit(dP: pd.Series, dO: pd.Series, before: str):
    """no-intercept slope, its n and residual variance on pairs strictly before `before`."""
    j = pd.concat([dP.rename("p"), dO.rename("o")], axis=1).dropna()
    j = j[j.index < before]
    n = len(j)
    if n < MIN_PAIRS or float((j.p ** 2).sum()) == 0:
        return np.nan, n, np.nan
    b = float((j.p * j.o).sum() / (j.p ** 2).sum())
    s2 = float(((j.o - b * j.p) ** 2).sum() / max(n - 1, 1))
    return b, n, s2


def calibrate(dP: pd.Series, dO: pd.Series, before: str, b0: float, pool_s2: float) -> tuple[float, float, int]:
    """shrunk (b, s2, n)"""
    b, n, s2 = own_fit(dP, dO, before)
    if not np.isfinite(b):
        return b0, pool_s2, n
    lam = n / (n + NU)
    return float(lam * b + (1 - lam) * b0), float((n * s2 + NU * pool_s2) / (n + NU)), n


def fuse(m: float, sp2: float, bd: float, s2: float) -> tuple[float, float]:
    wp, ws = 1 / sp2, 1 / s2
    return (wp * m + ws * bd) / (wp + ws), 1 / (wp + ws)


def item_estimates(t: str, cls: dict, dP: dict, dO: dict, tables: dict, sp: dict, b0: dict | None = None) -> dict:
    """item -> dict(prior, raw, cal, fused, var_fused, var_raw...) for target month t, using only pairs before t.
    cls: item -> 'gated' | 'direct' | 'prior'; dP/dO: item -> monthly log-change Series (proxy / official)."""
    b0 = b0 or {}
    own = {i: own_fit(dP[i], dO[i], t) for i in cls if cls[i] in ("gated", "direct") and i in dP and i in dO}
    s2s = [v[2] for v in own.values() if np.isfinite(v[2]) and v[1] >= 5]
    pool_s2 = float(np.median(s2s)) if s2s else 0.02 ** 2
    out = {}
    for i, c in cls.items():
        m = prior_change(tables, i, t)
        sp2 = sp.get(i, 0.02) ** 2
        r = dict(cls=c, prior=m, var_prior=sp2)
        if c in ("gated", "direct") and i in dP and t in dP[i].index and dP[i][t] == dP[i][t]:
            x = float(dP[i][t])
            b, s2, n = calibrate(dP[i], dO[i], t, b0.get(i, 1.0), pool_s2)
            r.update(raw=x, cal=b * x, b=b, s2=max(s2, FLOOR_SD ** 2), n_pairs=n)
            if c == "gated":
                f, v = fuse(m, sp2, b * x, r["s2"])
                r.update(fused=f, var_fused=v)
            else:                                         # administered: one-for-one, discrepancy variance = pooled
                r.update(fused=x, var_fused=r["s2"])
        else:
            r.update(fused=m, var_fused=sp2)
        out[i] = r
    return out


def index_change(est: dict, w: pd.Series, key: str) -> float:
    return float(sum(w.get(i, 0.0) * r.get(key, r["fused"] if key != "prior" else r["prior"]) for i, r in est.items()))


def aggregate_sd(est: dict, w: pd.Series, key="var_fused") -> float:
    return float(np.sqrt(sum((w.get(i, 0.0) ** 2) * r[key] for i, r in est.items())))
