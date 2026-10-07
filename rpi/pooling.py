"""Partial pooling across states for a NATIONAL proxy (inventory AK).

Setting: a national retail price panel (DoCA all-India, rpi/collectors/doca.py) stands in for Gujarat-urban item indices.  Its fit to Gujarat is judged on about 10 monthly
changes, far too few to estimate a pass-through.  The same national panel can be compared with EVERY state's official index for the same item (37 states x 11 changes), which says
how far a state's official index moves when the national panel moves by 1% and how much it scatters.  Model, in monthly log changes, no intercept (as in rpi/pooled_checks.py):

    d_official[s,t] = b_s * d_national[t] + e,     b_s ~ N(b_bar, tau^2)

POOL   b_bar from the other states only.   OWN  the state's own OLS slope.   PP  empirical-Bayes shrinkage of OWN toward POOL, weight lam = tau^2 / (tau^2 + se_own^2),
tau^2 by method of moments over the other states' slopes.  Evaluation is leave-one-state-out AND leave-future-out: for a target month t the coefficients use only months < t,
and the state being predicted contributes only its own months < t.  Pure functions; the runner is scripts/national_pooling_test.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """no-intercept OLS: (b, se(b), residual variance); (nan, inf, nan) when under 3 points."""
    n = len(x)
    if n < 3 or float((x * x).sum()) == 0:
        return np.nan, np.inf, np.nan
    b = float((x * y).sum() / (x * x).sum())
    s2 = float(((y - b * x) ** 2).sum() / max(n - 1, 1))
    return b, float(np.sqrt(s2 / (x * x).sum())), s2


def pooled_slope(df: pd.DataFrame) -> tuple[float, float, float]:
    return slope(df.dn.values, df["do"].values)


def tau2_mom(df: pd.DataFrame, min_n: int = 4) -> float:
    """method-of-moments variance of true state slopes: var(b_s) - mean(se_s^2)."""
    bs, ses = [], []
    for _, g in df.groupby("state"):
        b, se, _ = slope(g.dn.values, g["do"].values)
        if len(g) >= min_n and np.isfinite(b) and np.isfinite(se):
            bs.append(b); ses.append(se ** 2)
    if len(bs) < 4:
        return 0.05
    return max(float(np.var(bs, ddof=1) - np.mean(ses)), 1e-4)


def shrink(own: tuple[float, float, float], pool_b: float, tau2: float) -> float:
    b, se, _ = own
    if not np.isfinite(b):
        return pool_b
    lam = tau2 / (tau2 + se ** 2)
    return float(lam * b + (1 - lam) * pool_b)


def predict_state(df: pd.DataFrame, state: str, t: str) -> dict:
    """Predictions of the official change of `state` in month t from each rule, using months < t only (state's own history included only for OWN / PP)."""
    past = df[df.t < t]
    others, mine = past[past.state != state], past[past.state == state]
    row = df[(df.state == state) & (df.t == t)]
    if row.empty or len(others) < 20:
        return {}
    dn = float(row.dn.iloc[0])
    pb, _, _ = pooled_slope(others)
    own = slope(mine.dn.values, mine["do"].values)
    pp = shrink(own, pb, tau2_mom(others))
    return dict(actual=float(row["do"].iloc[0]), ZERO=0.0, BETA1=dn, POOL=pb * dn, OWN=(own[0] * dn if np.isfinite(own[0]) else dn), PP=pp * dn, b_pool=pb, b_pp=pp)


def loso_lfo(df: pd.DataFrame, item: str, test_from: str) -> pd.DataFrame:
    d = df[df.item == item]
    rows = []
    for s in sorted(d.state.unique()):
        for t in sorted(d[(d.state == s) & (d.t >= test_from)].t.unique()):
            r = predict_state(d, s, t)
            if r:
                rows.append(dict(item=item, state=s, t=t, **r))
    return pd.DataFrame(rows)


def summarise(res: pd.DataFrame, rules=("ZERO", "BETA1", "OWN", "POOL", "PP")) -> pd.DataFrame:
    out = []
    for item, g in res.groupby("item"):
        row = dict(item=item, n=len(g))
        for r in rules:
            row[f"rmse_{r}"] = round(float(np.sqrt(((g[r] - g.actual) ** 2).mean())) * 100, 3)
        row["pp_vs_beta1"] = round(row["rmse_PP"] / row["rmse_BETA1"], 3)
        row["pp_wins_vs_beta1"] = round(float(((g.PP - g.actual).abs() < (g.BETA1 - g.actual).abs()).mean()), 3)
        out.append(row)
    return pd.DataFrame(out)
