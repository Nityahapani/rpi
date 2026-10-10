"""Bridge from the factor to the official CPI, nowcast with bands, and rolling-origin backtest.

Timing: the factor for month m is filtered from rpi division data up to and including m, so the
nowcast of the official MoM for m uses the same information the rpi has for month m.
Parameters used at month m are estimated only on data before m.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from econ import dfm
from econ.data import Panel, division_changes

Z80 = 1.2815515655446004   # 80% two-sided normal quantile
MIN_BRIDGE_MONTHS = 8      # official MoM observations needed before the first bridge is estimated


@dataclass
class Bridge:
    alpha: float
    beta: float
    sigma: float       # residual sd of official MoM on the factor
    n: int


@dataclass
class FactorRun:
    params: dfm.DFMParams
    f: pd.Series       # filtered factor mean, index = period
    P: pd.Series       # filtered factor variance, index = period


def fit_bridge(factor: pd.Series, official_mom: pd.Series) -> Bridge:
    both = pd.concat([factor.rename("f"), official_mom.rename("y")], axis=1).dropna()
    X = np.column_stack([np.ones(len(both)), both.f.values])
    coef, *_ = np.linalg.lstsq(X, both.y.values, rcond=None)
    resid = both.y.values - X @ coef
    dof = max(len(both) - 2, 1)
    return Bridge(alpha=float(coef[0]), beta=float(coef[1]),
                  sigma=float(np.sqrt(resid @ resid / dof)), n=len(both))


def _matrix(p: Panel, upto: str | None) -> tuple[np.ndarray, list[str]]:
    dc = division_changes(p)
    if upto is not None:
        dc = dc.loc[:upto]
    return dc[p.divisions].values, list(dc.index)


def factor_run(p: Panel, upto: str | None, params_upto: str | None = None) -> FactorRun:
    """Filter the factor through `upto`, with parameters estimated on data through `params_upto`."""
    y_all, idx = _matrix(p, upto)
    y_fit, _ = _matrix(p, params_upto or upto)
    params, _ = dfm.fit(y_fit)
    filt = dfm.kalman(y_all, params)
    return FactorRun(params=params, f=pd.Series(filt.a, index=idx), P=pd.Series(filt.P, index=idx))


def fixed_weight_mom(p: Panel) -> pd.Series:
    dc = division_changes(p)[p.divisions]
    return (dc * p.weights.values).sum(axis=1, min_count=len(p.divisions))


def _prev(periods: list[str], m: str) -> str:
    return periods[periods.index(m) - 1]


def backtest(p: Panel) -> pd.DataFrame:
    """Out-of-sample nowcasts of the official general MoM, one month at a time."""
    fw = fixed_weight_mom(p)
    official = p.official_mom
    rows = []
    for m in official.index:
        prior = official.loc[:m].iloc[:-1]
        if len(prior) < MIN_BRIDGE_MONTHS:
            continue
        prev = _prev(p.periods, m)
        run = factor_run(p, upto=m, params_upto=prev)
        br = fit_bridge(run.f.loc[:prev], prior)
        sd = np.sqrt(br.beta ** 2 * run.P.loc[m] + br.sigma ** 2)
        pred = br.alpha + br.beta * run.f.loc[m]
        rows.append({
            "period": m,
            "official_mom": official.loc[m],
            "dfm_nowcast": pred,
            "dfm_band80_lo": pred - Z80 * sd,
            "dfm_band80_hi": pred + Z80 * sd,
            "rpi_total_mom": p.rpi_total_mom.get(m, np.nan),
            "fixed_weight_mom": fw.get(m, np.nan),
            "mean_benchmark": prior.mean(),
        })
    return pd.DataFrame(rows).set_index("period")


def metrics(bt: pd.DataFrame) -> dict[str, dict[str, float]]:
    out = {}
    for col in ["dfm_nowcast", "rpi_total_mom", "fixed_weight_mom", "mean_benchmark"]:
        e = (bt[col] - bt["official_mom"]).dropna()
        out[col] = {"n": int(len(e)), "rmse": float(np.sqrt((e ** 2).mean())), "mae": float(e.abs().mean())}
    return out


def nowcast(p: Panel) -> dict:
    """Full-sample fit, bridge on all official months, nowcast for every rpi month without official data."""
    run = factor_run(p, upto=None)
    br = fit_bridge(run.f.loc[p.official_mom.index.intersection(run.f.index)], p.official_mom)
    rows = []
    for m in run.f.index:
        sd = np.sqrt(br.beta ** 2 * run.P.loc[m] + br.sigma ** 2)
        mom = br.alpha + br.beta * run.f.loc[m]
        rows.append({"period": m, "factor": run.f.loc[m], "factor_var": run.P.loc[m],
                     "mom_nowcast": mom, "band80_lo": mom - Z80 * sd, "band80_hi": mom + Z80 * sd,
                     "official_mom": p.official_mom.get(m, np.nan)})
    table = pd.DataFrame(rows).set_index("period")
    return {"run": run, "bridge": br, "table": table}
