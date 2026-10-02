"""Local official benchmark: Labour Bureau CPI-IW (2016=100) for Rajkot and the other Gujarat centres.

CPI-IW is a *different* index (industrial-worker households, 2016 weights, more food/fuel, house rent revised half-yearly),
so levels and even growth rates legitimately differ from the RPI. It is the only official statistic published for the CITY of
Rajkot, which makes it the right external yardstick for direction and timing. It never feeds the index; the comparison is
published in status.json so a reader can see how the RPI behaves against it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

CENTRES_CSV = "data/official/cpi_iw_gujarat_centres.csv"


def load_centres(root: Path) -> pd.DataFrame:
    p = Path(root) / CENTRES_CSV
    if not p.exists():
        return pd.DataFrame()
    return pd.read_csv(p).pivot(index="period", columns="centre", values="value").sort_index()


def merge_centres(root: Path, new: dict[tuple[str, str], float], url: str, retrieved: str) -> int:
    """Upsert {(period, centre): value} into the centres CSV; returns the number of rows added or changed."""
    p = Path(root) / CENTRES_CSV
    cur = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=["period", "centre", "value", "source_url", "source_class", "retrieved"])
    have = {(r.period, r.centre): r.value for r in cur.itertuples()}
    changed = [(k, v) for k, v in new.items() if have.get(k) != v]
    if not changed:
        return 0
    add = pd.DataFrame([dict(period=k[0], centre=k[1], value=v, source_url=url,
                             source_class="official (Labour Bureau CPI-IW 2016=100, home-page centre table)", retrieved=retrieved)
                        for k, v in changed])
    keep = cur[~cur.set_index(["period", "centre"]).index.isin(add.set_index(["period", "centre"]).index)]
    pd.concat([keep.astype(add.dtypes.to_dict()), add]).sort_values(["period", "centre"]).to_csv(p, index=False)
    return len(changed)


def _runs(periods: list[str]) -> list[list[str]]:
    """Split a sorted list of YYYY-MM into runs of consecutive months."""
    out, cur = [], []
    for p in periods:
        if cur and (pd.Period(p, "M") - pd.Period(cur[-1], "M")).n != 1:
            out.append(cur)
            cur = []
        cur.append(p)
    if cur:
        out.append(cur)
    return out


def compare(root: Path, rpi: pd.Series, gu_general: pd.Series, last_official: str | None) -> dict:
    """rpi / gu_general: level series indexed 'YYYY-MM' (strings). Only months <= last_official are compared."""
    c = load_centres(root)
    if c.empty or "Rajkot" not in c:
        return {"status": "no_data"}
    raj = c["Rajkot"].dropna()
    rpi = rpi.copy()
    rpi.index = rpi.index.astype(str)
    gu = gu_general.copy()
    gu.index = gu.index.astype(str)
    cap = last_official or max(raj.index)
    raj = raj[raj.index <= cap]
    both = pd.concat([raj.rename("cpi_iw_rajkot"), rpi.rename("rpi"), gu.rename("mospi_gu_general")], axis=1).dropna()
    if len(both) < 4:
        return {"status": "too_few_months", "n": int(len(both))}
    pairs = []
    for run in _runs(list(both.index)):
        lg = np.log(both.loc[run]).diff().dropna()
        pairs.append(lg)
    d = pd.concat(pairs) if pairs else pd.DataFrame()
    out = {"status": "ok", "n_months": int(len(both)), "n_mom_pairs": int(len(d)), "window": [both.index[0], both.index[-1]]}
    if len(d) >= 4:
        out["mom_corr_rpi_vs_cpi_iw_rajkot"] = round(float(d["rpi"].corr(d["cpi_iw_rajkot"])), 2)
        out["mom_corr_mospi_gu_vs_cpi_iw_rajkot"] = round(float(d["mospi_gu_general"].corr(d["cpi_iw_rajkot"])), 2)
        out["mean_abs_mom_gap_pp_rpi_vs_cpi_iw"] = round(float((d["rpi"] - d["cpi_iw_rajkot"]).abs().mean()) * 100, 2)
    run = max(_runs(list(both.index)), key=len)
    if len(run) >= 3:
        out["longest_run"] = [run[0], run[-1]]
        out["cum_pct_over_longest_run"] = {k: round((both.loc[run[-1], k] / both.loc[run[0], k] - 1) * 100, 2) for k in both.columns}
    # year-on-year at the last common month, if 12 months back exists in all three
    last = both.index[-1]
    prev = str(pd.Period(last, "M") - 12)
    yo = {}
    for name, ser in (("cpi_iw_rajkot", raj), ("rpi", rpi), ("mospi_gu_general", gu)):
        if last in ser.index and prev in ser.index:
            yo[name] = round((ser[last] / ser[prev] - 1) * 100, 2)
    if yo:
        out["yoy_pct_at"] = {"period": last, **yo}
    # is Rajkot special inside Gujarat? (centre YoY, same months)
    others = [k for k in c.columns if k != "Rajkot"]
    if last in c.index and prev in c.index and others:
        out["gujarat_centres_yoy_pct"] = {k: round((c.loc[last, k] / c.loc[prev, k] - 1) * 100, 2) for k in c.columns
                                          if pd.notna(c.loc[last, k]) and pd.notna(c.loc[prev, k])}
    return out
