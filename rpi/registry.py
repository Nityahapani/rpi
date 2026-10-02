"""Staleness alarm for curated (human-confirmed) administered-price registers.

Some prices (electricity surcharge, milk, LPG slabs...) are announced irregularly and in no machine-readable place, so they
live in small CSV registers. A register that quietly stops being updated is a silent accuracy bug, so every refresh
reports how old the newest entry is per item and warns when it exceeds the item's normal revision cycle.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

# item -> (max days since last recorded change before we ask a human to re-check, where to look)
REVIEW = {
    "R002": (150, "GUVNL/DISCOM FPPAS circulars; Gujarat energy dept releases; add a row to data/fppas_schedule.csv"),
    "F009": (400, "GCMMF/Amul price-revision press release; run scripts/add_milk_events.py pattern"),
    "R003": (120, "LPG monthly revision (auto-checked from goodreturns)"),
    # Flat-by-design registers: a dated row means 'price re-confirmed on this date', so the alarm asks for a fresh confirmation.
    "R004": (400, "RMC annual budget (Feb-Mar): residential water charge; add a re-confirmation row via scripts/add_admin_registers.py"),
    "K001": (150, "Jio/Airtel prepaid plan pages + telecom press; operators revise irregularly (a FY27 hike is widely expected)"),
    "R005": (400, "Gujarat Gas domestic PNG tariff SMS/press; add a row to data/png_events.csv (prices tax-inclusive Rs/SCM); overlay retires itself once goodreturns shows the new price"),
    "M001": (400, "NPPA annual WPI revision of DPCO ceiling prices (S.O. in March, effective 1 April) and any GST change on drugs; add a row via scripts/add_nppa_register.py"),
    "T004": (900, "Gujarat Ports & Transport Dept auto-rickshaw fare notification (revised ~every 1-4 years; fuel/CNG spikes trigger union demands); add a row via scripts/add_autorickshaw_register.py"),
    "S002": (250, "JioHotstar / Amazon Prime India price pages and press"),
}


def review(events_csv, today: dt.date | None = None, extra: dict | None = None) -> list[str]:
    """extra: item_id -> separate events CSV (columns effective_from, status) for registers living outside tariff_events.csv."""
    today = today or dt.date.today()
    ev = pd.read_csv(events_csv)
    ev["d"] = pd.to_datetime(ev.effective_from).dt.date
    out = []
    for item, (max_age, where) in REVIEW.items():
        if item in (extra or {}):
            try:
                x = pd.read_csv(extra[item])
            except FileNotFoundError:
                x = pd.DataFrame(columns=["effective_from"])
            g = pd.DataFrame({"d": pd.to_datetime(x.effective_from).dt.date})
        elif item == "R005":
            continue  # R005 is only reviewed when its own register is supplied
        else:
            g = ev[ev.item_id == item]
        if g.empty:
            out.append(f"{item}: NO events recorded - {where}")
            continue
        age = (today - g.d.max()).days
        if age > max_age:
            out.append(f"{item}: last change {g.d.max()} ({age} d ago, review cycle {max_age} d) - {where}")
    return out
