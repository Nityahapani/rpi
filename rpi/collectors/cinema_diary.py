"""S001 cinema ticket: Rajkot theatre pages on district.in (District by Zomato), live diary + gate.

Source: each district.in theatre page carries one schema.org ScreeningEvent JSON-LD block per show of the displayed day, with the lowest seat price
(`offers.price`) and `videoFormat`.  robots.txt for `User-agent: *` disallows only query-string URLs, order/checkout and account paths; plain theatre pages
are allowed and are read at 2 s spacing.  Pool: the eight Rajkot theatres listed on /movies/cinemas-in-rajkot (data/cinema/pool.csv).
Price concept (one number per theatre-day): the CHEAPEST seat price among 2D shows starting 18:00-22:59, on Monday-Thursday show days only (weekend and
holiday pricing excluded); at least 3 qualifying shows are required.  Film-mix effects remain (a new release can lift the cheapest evening seat), so this
is a PROXY with noise, not a same-film same-slot price.  Index: monthly median per theatre, matched-model Jevons across theatres
(rpi/proxy_check.chain_series).  PENDING-GATE proxy for S001: there is no archived history (the site is not in the Wayback Machine); the unchanged gate
(>= 6 overlapping months, corr >= 0.5, drift <= 0.10) decides.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

ITEM, CODE = "S001", "09.6.1.0.2.01"
COLS = ["date", "key", "price", "n_shows"]
EVENING = (18, 23)
MIN_SHOWS = 3


def parse_events(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        for p in (j if isinstance(j, list) else [j]):
            if not (isinstance(p, dict) and p.get("@type") == "ScreeningEvent"):
                continue
            of = p.get("offers")
            of = of[0] if isinstance(of, list) and of else of
            try:
                price = float(of["price"])
                start = dt.datetime.fromisoformat(p["startDate"])
            except Exception:
                continue
            out.append(dict(start=start, fmt=str(p.get("videoFormat", "")), price=price))
    return out


def day_price(events: list[dict]):
    """(show_date, cheapest weekday-evening 2D seat price, n_shows) or None."""
    if not events:
        return None
    day = pd.Series([e["start"].date() for e in events]).mode().iloc[0]
    if day.weekday() > 3:
        return None
    q = [e for e in events if e["start"].date() == day and e["fmt"] == "2D" and e["price"] > 0 and EVENING[0] <= e["start"].hour < EVENING[1]]
    return None if len(q) < MIN_SHOWS else (day, min(e["price"] for e in q), len(q))


def accrue(path: Path, pool_csv: Path, client, today: dt.date | None = None) -> tuple[int, str]:
    pool = pd.read_csv(pool_csv, dtype=str)
    rows, skipped = [], 0
    for r in pool.itertuples():
        resp = client.get(r.url)
        got = day_price(parse_events(resp.text)) if resp.status_code == 200 else None
        if got is None:
            skipped += 1
            continue
        rows.append(dict(date=got[0].isoformat(), key=r.key, price=got[1], n_shows=got[2]))
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLS)
    if rows:
        new_keys = {(x["date"], x["key"]) for x in rows}
        old = old[[(a, b) not in new_keys for a, b in zip(old.date, old.key)]]
        old = pd.concat([old, pd.DataFrame(rows, columns=COLS)], ignore_index=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        old.sort_values(["date", "key"]).to_csv(path, index=False)
    return len(rows), f"{len(rows)}/{len(pool)} theatres priced ({skipped} skipped: weekend page, <{MIN_SHOWS} evening 2D shows, or unreadable)"


class CinemaCollector:
    """Wires the live diary (data/cinema/live_prices.csv) into the index as a PENDING-GATE proxy for S001 (one SKU per theatre)."""
    source_id = "district_cinema"
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.live = Path(root) / "data/cinema/live_prices.csv"

    def collect(self, on_date):
        from .base import Observation
        if not self.live.exists():
            return
        d = pd.read_csv(self.live)
        d = d[d.price > 0]
        for r in d.itertuples():
            y, m, dd = (int(x) for x in r.date.split("-"))
            yield Observation(dt.date(y, m, dd), self.source_id, "CINEMA:" + r.key, "Cheapest weekday-evening 2D seat, Rajkot theatre " + r.key + " (district.in)",
                              ITEM, "RAJKOT", float(r.price), qty_base=1.0, base_unit="pc")


def monthly_panel(live_csv: Path) -> pd.DataFrame:
    if not live_csv.exists():
        return pd.DataFrame()
    lv = pd.read_csv(live_csv)
    lv = lv[lv.price > 0].copy()
    lv["m"] = lv.date.str[:7]
    return lv.groupby(["key", "m"]).price.median().reset_index().pivot(index="m", columns="key", values="price").sort_index()


def gate(live_csv: Path, official_csv: Path) -> dict:
    from ..proxy_check import chain_series, judge
    off = pd.read_csv(official_csv, dtype={"code": str})
    o = off[(off.level == "item") & (off.code == CODE)].set_index("period").index_value
    piv = monthly_panel(live_csv)
    if piv.empty:
        return dict(item_id=ITEM, verdict="pending", n_overlap=0, corr=None, drift=None, n_skus=0)
    piv = piv[piv.index <= o.index.max()]
    j = judge(chain_series(piv), o) if len(piv) else dict(verdict="pending", n_overlap=0, corr=None, drift=None)
    j.update(item_id=ITEM, n_skus=int(piv.notna().any().sum()))
    return j
