"""Seasonal-trend nowcast prior and wholesale-feed calibration (sweep 27, inventory section AG/AH).

Why: a fill rule for months the official index has not reached.  A 12-month trailing mean (the old `own_trend` rule) chases noise
for volatile items.  Tested in pseudo-real time on 11 years of OFFICIAL Gujarat-urban item data (scripts/panel_nowcast_rules.py;
rules fixed in advance; selection origins 2018-2022, untouched test 2023-2025): the item's long-run mean monthly change plus an
empirical-Bayes-shrunk calendar-month deviation ("SEASC") cut index-level RMSE by 28% (1 month ahead) and 33% (2 months ahead) on the
untouched test (Diebold-Mariano p <= 0.001 on the test, p <= 0.007 on the selection window, both horizons).

Wholesale calibration: the index feeds one wholesale yard into an item as if wholesale change = retail change (beta=1).  On Gujarat
districts, Jan-Oct 2025, that gave 24 pp RMSE for the four vegetables against 16 pp for the trailing mean and 8.8 pp for the calibrated
fusion (scripts/yard_calibration.py: pooled b0 estimated on OTHER states, precision weights from stated variances, nothing fitted on the
test months).  Items whose wholesale has no signal (wheat, moong) get a near-zero b0 and so fall back on the seasonal prior by themselves.

Pure functions only; tables are built by scripts/build_seasonal_tables.py from data/official/mospi_cpi2012_gujarat_urban_items.csv.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TABLE_FILE = "data/official/seasonal_tables.csv"
CAL_FILE = "data/official/wholesale_calibration.csv"


def seasonal_table(dlog: pd.Series, min_years: int = 3) -> pd.DataFrame:
    """dlog: monthly log changes indexed by a monthly PeriodIndex (NaN where unavailable).
    Returns a 12-row frame (index = calendar month) with `clim` (mean of all changes, same value in every row), `seas` (EB-shrunk calendar-month deviation
    from the year's own mean change) and `n` (years behind each month)."""
    s = dlog.dropna()
    df = pd.DataFrame({"d": s.values, "m": [p.month for p in s.index], "y": [p.year for p in s.index]})
    clim = float(df.d.mean()) if len(df) else 0.0
    out = pd.DataFrame({"clim": clim, "seas": 0.0, "n": 0}, index=range(1, 13))
    if len(df) < 36:
        return out
    df["dev"] = df.d - df.groupby("y").d.transform("mean")
    g = df.groupby("m").dev.agg(["mean", "count", "var"])
    tau2 = max(float(g["mean"].var(ddof=1)) - float((g["var"] / g["count"]).mean()), 1e-8) if len(g) > 3 else 1e-8
    for m, r in g.iterrows():
        out.loc[m, "n"] = int(r["count"])
        if r["count"] >= min_years and r["var"] == r["var"]:
            out.loc[m, "seas"] = float(tau2 / (tau2 + r["var"] / r["count"]) * r["mean"])
    return out


def load_tables(root) -> dict[str, tuple[float, np.ndarray]]:
    """item_id -> (clim, seas[0..11] indexed by calendar month-1)."""
    p = Path(root) / TABLE_FILE
    if not p.exists():
        return {}
    t = pd.read_csv(p)
    res = {}
    for it, g in t.groupby("item_id"):
        g = g.sort_values("month")
        if len(g) == 12:
            res[it] = (float(g.clim.iloc[0]), g.seas.to_numpy(float))
    return res


def prior(tables: dict, item: str, period: pd.Period) -> float | None:
    if item not in tables:
        return None
    clim, seas = tables[item]
    return clim + float(seas[period.month - 1])


def load_calibration(root) -> dict[str, dict]:
    p = Path(root) / CAL_FILE
    if not p.exists():
        return {}
    return {r["item_id"]: {k: float(r[k]) for k in ("b0", "sigma_wb", "sigma_prior")} for _, r in pd.read_csv(p).iterrows()}


def fuse(prior_change: float, wholesale_change: float, b0: float, sigma_wb: float, sigma_prior: float) -> float:
    """Precision-weighted mean of the seasonal prior and the pooled-calibrated wholesale change b0*dw."""
    wp, ww = 1.0 / sigma_prior ** 2, 1.0 / sigma_wb ** 2
    return (wp * prior_change + ww * b0 * wholesale_change) / (wp + ww)


def calibrate_wholesale(rel: pd.DataFrame, n: pd.DataFrame, cutoffs: dict, cal: dict, tables: dict, clip: float | None = None) -> tuple[pd.DataFrame, list]:
    """Replace an item's observed wholesale relative by the fused estimate, for months AFTER the item's first independent month (the splice
    month has no relative).  Returns (new_rel, log of (item, period, raw, fused))."""
    out = rel.copy(); log = []
    for it, c in cal.items():
        if it not in out.columns or it not in cutoffs:
            continue
        for per in out.index:
            if str(per) <= cutoffs[it] or pd.isna(out.loc[per, it]) or n.loc[per, it] < 1:
                continue
            pr = prior(tables, it, per)
            if pr is None:
                continue
            raw = float(out.loc[per, it]); f = fuse(pr, raw, c["b0"], c["sigma_wb"], c["sigma_prior"])
            out.loc[per, it] = f; log.append((it, str(per), raw, f))
    return out, log
