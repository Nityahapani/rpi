"""Hathway broadband: one fixed home plan, Surat tariff page (K003 'Broadband plan') - a PROXY source, not Rajkot.

Why this exists.  K003 (0.90% of the basket) was priced by the official MoSPI Gujarat-urban item index only (`official_link`).
hathway.com publishes its residential plans per city in static HTML (no login, no JavaScript): each card carries the plan name,
the speed and the monthly 'effective' price.  robots.txt for hathway.com allows `/*` for generic bots (checked 2026-10-10), and
the site's Terms say packages and prices may change (they do not forbid reading the page).

Honest limits (read before using the series):
  * This is SURAT, not Rajkot. Hathway's own city list (2026-10-10) has no Rajkot page; Rajkot's cable-broadband operator is GTPL.
    The series is therefore a Gujarat proxy: PROXY bucket, labelled as such everywhere.
  * The price is Hathway's 'Effective Monthly Pricing' as printed. The card advertises 'Pay for 11 months and get 12th month FREE'
    and 3/6/12-month options, so the printed figure is a promotional effective rate, not the list price. The series is recorded
    exactly as printed; a change in the promotion moves it.
  * FIXED plan: data/hathway_broadband/pool.csv (75 Mbps 'Beginners Plan'). If Hathway drops or renames this plan, accrual reports
    'not on page' and the chain stops. A replacement plan needs its own pool row and a chain splice, decided by hand. No hedonic
    replacement is modelled here.

Design (same rules as the other shadow candidates):
  * one request per run to the Surat page with the project's honest User-Agent (PoliteClient, robots.txt respected);
  * the price is taken from the card whose speed AND plan name match the pool row; a missing card, conflicting duplicate
    prices (the page repeats the card carousel) or a price outside the band is skipped and reported, never carried forward;
  * accrues forward only (data/hathway_broadband_prices.csv, top level so the daily bot commits it); same-day rerun replaces today;
  * SHADOW until K003 is switched to primary_source = hathway_broadband in data/source_plan.csv AND [index.switches] in
    config/settings.toml. Nothing reaches the index before that. The screen (rpi/shadow.py) compares the chain with the official item
    index (proxy_check.judge: >= 6 overlapping months, corr >= 0.5, drift <= 0.10).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from .base import Observation

SOURCE_ID = "hathway_broadband"
PAGE = "https://www.hathway.com/Broadband/HomeBroadband/Surat"
POOL = "data/hathway_broadband/pool.csv"
LIVE = "data/hathway_broadband_prices.csv"
COLS = ["date", "plan_name", "speed", "item_id", "price", "currency", "url"]
PRICE_BAND = (200.0, 3_000.0)                # INR per month; outside this is a parsing error, not a price
# One plan card: plan name, speed, then the first planPrice after it (the card markup is fixed on the page).
_CARD = re.compile(
    r'class="head">\s*(?P<name>[^<]+?)\s*</div>\s*<div class="planSpeed">\s*<h3>\s*(?P<speed>\d+)\s*Mbps\s*</h3>'
    r'.*?<div class="planPrice">\s*\u20b9\s*(?P<price>[0-9][0-9,]*(?:\.[0-9]+)?)',
    re.S,
)


def parse_price(html: str, plan_name: str, speed: str) -> float | None:
    """Monthly price the page prints for one plan, or None (absent, conflicting, or outside the band)."""
    prices = set()
    for m in _CARD.finditer(html):
        if m.group("name").strip() == plan_name and m.group("speed") == str(speed):
            prices.add(float(m.group("price").replace(",", "")))
    if len(prices) != 1:                     # absent, or the same plan printed at two prices
        return None
    p = prices.pop()
    return p if PRICE_BAND[0] <= p <= PRICE_BAND[1] else None


def load_pool(root: Path) -> pd.DataFrame:
    return pd.read_csv(Path(root) / POOL, dtype=str, keep_default_na=False)


def accrue(client, root: Path, today: dt.date | None = None) -> tuple[int, str]:
    """One page fetch; one row per pool plan that the page prices today."""
    today = today or dt.date.today()
    root = Path(root)
    pool = load_pool(root)
    r = client.get(PAGE)
    if r.status_code != 200:
        return 0, f"hathway.com HTTP {r.status_code}"
    html = r.text
    rows, miss = [], []
    for p in pool.itertuples():
        price = parse_price(html, p.plan_name, p.speed.replace(" Mbps", "").strip())
        if price is None:
            miss.append(f"{p.speed} {p.plan_name}")
            continue
        rows.append({"date": today.isoformat(), "plan_name": p.plan_name, "speed": p.speed, "item_id": p.item_id,
                     "price": price, "currency": "INR", "url": PAGE})
    path = root / LIVE
    old = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=COLS)
    old = old[old.date != today.isoformat()]                       # same-day rerun replaces today's rows
    new = pd.DataFrame(rows, columns=COLS)
    parts = [x for x in (old, new) if len(x)]
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)
    out.to_csv(path, index=False)
    msg = "ok" if not miss else f"not on page today: {miss}"
    return len(rows), msg


def live_frame(root: Path) -> pd.DataFrame:
    """The accrued quotes in the shared shadow schema (date, item_id, sku, unit_price, price, regular_price, qty_base, base_unit, title, store)."""
    path = Path(root) / LIVE
    cols = ["date", "item_id", "sku", "unit_price", "price", "regular_price", "qty_base", "base_unit", "title", "store"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["price"] = d.price.astype(float)
    d["sku"] = "hathway:" + d.speed.str.replace(" ", "") + ":" + d.plan_name.str.replace(" ", "")
    d["unit_price"] = d.price
    d["regular_price"] = d.price
    d["qty_base"] = 1.0
    d["base_unit"] = "pc"
    d["title"] = "Hathway Surat " + d.speed + " " + d.plan_name + " (effective monthly)"
    d["store"] = "hathway"
    return d[d.price > 0][cols]


def switched_items(root: Path, source_id: str = SOURCE_ID) -> list[str]:
    plan = pd.read_csv(Path(root) / "data/source_plan.csv", dtype=str, keep_default_na=False)
    return plan.loc[plan.primary_source == source_id, "item_id"].tolist()


class HathwayBroadbandCollector:
    """Emits the accrued quotes of SWITCHED items only (primary_source = hathway_broadband); in shadow mode it emits nothing."""
    source_id = SOURCE_ID
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.root = Path(root)

    def collect(self, on_date):
        items = set(switched_items(self.root))
        if not items:
            return
        d = live_frame(self.root)
        for r in d[d.item_id.isin(items)].itertuples():
            y, m, dd = (int(x) for x in r.date.split("-"))
            yield Observation(dt.date(y, m, dd), SOURCE_ID, r.sku, r.title, r.item_id, "IN-GJ", float(r.price),
                              regular_price=float(r.regular_price), qty_base=float(r.qty_base), base_unit=str(r.base_unit))
