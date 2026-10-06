"""E001 (private school fee) from the Gujarat Fee Regulatory Committee's APPROVED fees for Rajkot-city schools (data/frc/rajkot_fees.csv,
scripts/frc_rajkot_fees.py).  Regulator-published, Rajkot-specific, school x standard x academic-year.

Rules (fixed before the gate was run):
  * panel      = school x medium x standard 1..8 with an approved fee > 0 in BOTH consecutive academic years (matched model);
  * AY change  = equal-weight mean log change of the matched panel (Jevons);  AY 2020-21 / 2021-22 are the Covid fee cut and rebound and are kept
                 in the data but flagged (they are outside the gate window);
  * timing     = approved fees apply from the academic year (June), but MoSPI's school-fee index drifts in through the year.  The change of
                 year Y (AY Y-Y+1 over AY Y-1-Y) is therefore spread over calendar year Y with the month profile of the official Gujarat-urban school-fee
                 index in 2014-2019 (the years BEFORE the FRC data and before the gate window): profile_m = mean m/m log change / sum over months.
Limits: only schools above the statutory fee cap are in the database (Gujarat Self-Financed Schools Act 2017), so this is the upper-fee segment;
approved fee is a ceiling, not a paid price (the audited statement in the Supreme Court order of 2018 lets the FRC fix it, and charging more is illegal).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CPI2012_LINE = "Tuition and Other Fees (school, College, Etc.)"


def ay_changes(fees: pd.DataFrame, std_min: int = 1, std_max: int = 8) -> pd.DataFrame:
    d = fees.copy()
    d["std"] = pd.to_numeric(d["standard"], errors="coerce")
    d = d[d["std"].between(std_min, std_max)]
    p = d.groupby(["school_id", "medium", "standard", "ay"]).fee.first().unstack("ay")
    rows = []
    cols = sorted(p.columns)
    for a, b in zip(cols[:-1], cols[1:]):
        m = p[[a, b]].dropna()
        m = m[(m > 0).all(axis=1)]
        if len(m) >= 20:
            rows.append(dict(ay=b, year=int(b[:4]), n=len(m), dlog=float(np.log(m[b] / m[a]).mean())))
    return pd.DataFrame(rows)


def month_profile(cpi2012_items: pd.DataFrame, first="2014-02", last="2019-12") -> pd.Series:
    y = cpi2012_items[cpi2012_items["item"] == CPI2012_LINE].set_index("period")["index_value"].sort_index()
    y.index = pd.PeriodIndex(y.index, freq="M")
    r = np.log(y).diff().dropna()
    r = r[(r.index >= pd.Period(first, "M")) & (r.index <= pd.Period(last, "M"))]
    prof = r.groupby(r.index.month).mean()
    prof = prof.clip(lower=0)
    return prof / prof.sum()


def monthly_level(changes: pd.DataFrame, profile: pd.Series, start="2019-12", end="2026-12", base=100.0) -> pd.Series:
    by_year = changes.set_index("year")["dlog"]
    idx = pd.period_range(start, end, freq="M")
    lvl, cur = {}, base
    for p in idx:
        lvl[p] = cur
        if p.year in by_year.index:
            cur = cur * np.exp(by_year[p.year] * profile[p.month])
    # level at month p = fee level at the START of p; shift so the level includes month p's change
    s = pd.Series(lvl)
    return s.shift(-1).ffill()
