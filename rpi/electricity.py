"""Residential electricity (R002): effective monthly bill for a fixed 200 kWh household, built from two small curated
registers instead of any aggregator's 'current rate':

  data/electricity_base_tariff.csv   GERC energy slabs + fixed charge + duty
  data/fppas_schedule.csv            fuel surcharge (FPPAS/FPPPA) steps, each with source + status

Aggregators disagree wildly (Rs2.70 / Rs3.30 / Rs0.19-0.28 for the same month); only steps backed by a government release
or >=2 independent news outlets are in the schedule. The model is applied to every row whose status is usable.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

UNITS = 200.0
USABLE = {"verified", "corroborated", "derived"}


def monthly_bill(base: pd.Series, fppas: float, variable_pct: float, units: float = UNITS) -> float:
    s1, s2, s3 = float(base.slab1_upto), float(base.slab2_upto), float(base.slab3_upto)
    r1, r2, r3, r4 = (float(base[c]) / 100 for c in ("slab1_paise", "slab2_paise", "slab3_paise", "slab4_paise"))
    e = min(units, s1) * r1 + max(0.0, min(units, s2) - s1) * r2 + max(0.0, min(units, s3) - s2) * r3 + max(0.0, units - s3) * r4
    pre = e + float(base.fixed_rs_2to4kw) + fppas * units
    pre += variable_pct / 100.0 * pre                       # variable FPPAS applies to energy + base FPPAS + fixed
    return round(pre * (1 + float(base.duty_pct) / 100.0), 2)


def build_events(base_csv, sched_csv) -> pd.DataFrame:
    base = pd.read_csv(base_csv).sort_values("effective_from")
    sch = pd.read_csv(sched_csv)
    sch = sch[sch.status.str.lower().isin(USABLE)].sort_values("effective_from")
    base_dates = list(base.effective_from)
    dates = sorted(set(base_dates) | set(sch.effective_from))
    rows = []
    for d in dates:
        if d < base_dates[0]:
            continue
        b = base[base.effective_from <= d].iloc[-1]
        s = sch[sch.effective_from <= d]
        if s.empty:
            continue
        s = s.iloc[-1]
        price = monthly_bill(b, float(s.fppas_base_rs_per_unit), float(s.variable_pct))
        status = "corroborated" if "corroborated" in (s.status, b.status) else ("derived" if b.status == "derived" else "verified")
        rows.append(dict(item_id="R002", effective_from=d, price=price, status=status,
                         source_class="primary release + press" if status == "verified" else "press (2+ outlets)",
                         source_url=s.source_url, retrieved=dt.date.today().isoformat(),
                         note=f"FPPAS model: 200 kWh bill; slabs from {b.effective_from}, FPPAS {s.fppas_base_rs_per_unit}"
                              f" + {s.variable_pct}% variable, duty {b.duty_pct}%"))
    return pd.DataFrame(rows)


def update_events_file(events_csv, base_csv, sched_csv) -> str:
    ev = pd.read_csv(events_csv)
    new = build_events(base_csv, sched_csv)
    keep = ev[~((ev.item_id == "R002") & ev.note.fillna("").str.startswith("FPPAS model"))]
    out = pd.concat([keep, new], ignore_index=True)
    changed = len(out) != len(ev) or not out.drop(columns=["retrieved"]).equals(ev.drop(columns=["retrieved"]))
    if changed:
        out.to_csv(events_csv, index=False)
    return f"R002: {len(new)} bill-model event(s), latest {new.price.iloc[-1]} from {new.effective_from.iloc[-1]}" if len(new) else "R002: no events"
