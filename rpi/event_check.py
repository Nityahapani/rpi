"""Regulatory / company shock checks on official-linked series.

A handful of price shocks are known exactly from primary announcements (GST-driven MRP cuts by Amul, the NPPA's mandated
medicine price cut). Whenever the official item index we use as a stand-in barely moves on such a date we learn something
about the stand-in: an official-linked item is only as good as the official index's coverage of the product that actually
changed. These comparisons are DIAGNOSTIC: they never adjust the index. Rows live in data/official/event_checks.csv.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

EVENTS_CSV = "data/official/event_checks.csv"


def check_events(root: Path) -> list[dict]:
    root = Path(root)
    p = root / EVENTS_CSV
    if not p.exists():
        return []
    ev = pd.read_csv(p)
    off = pd.read_csv(root / "data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    mp = pd.read_csv(root / "data/basket_official_map.csv", dtype=str, keep_default_na=False).set_index("item_id")
    out = []
    for r in ev.itertuples():
        if r.status not in ("verified", "corroborated"):
            continue
        code = mp.loc[r.item_id, "official_item_code"] if r.item_id in mp.index else ""
        if code not in off.columns:
            continue
        d = pd.Timestamp(r.effective_from)
        # the effective month is partial: compare the last full month before with the first full month after
        em = d.to_period("M")
        pre, post = str(em - 1), str(em if d.day == 1 else em + 1)
        s = off[code]
        if pre not in s.index or post not in s.index:
            out.append(dict(item_id=r.item_id, event=r.event, verdict="official_not_yet_published", pre=pre, post=post))
            continue
        obs = (s[post] / s[pre] - 1) * 100
        ratio = obs / r.expected_pct if r.expected_pct else float("nan")
        verdict = "aligned" if 0.5 <= ratio <= 1.5 else ("official_muted" if ratio < 0.5 else "official_overshoots")
        out.append(dict(item_id=r.item_id, event=r.event, effective_from=r.effective_from, expected_pct=round(float(r.expected_pct), 2),
                        official_pct=round(float(obs), 2), pass_through_ratio=round(float(ratio), 2), pre=pre, post=post,
                        official_item=mp.loc[r.item_id, "official_item_name"], match=mp.loc[r.item_id, "match_quality"], verdict=verdict))
    return out
