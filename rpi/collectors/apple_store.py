"""Apple India store: the SIM-free iPhone 16 128 GB Black shelf price (K002 'Smartphone (fixed model)') - a SHADOW source.

Why this exists.  K002 (0.59% of the basket) is priced by the official MoSPI Gujarat-urban item index only (`official_link`), because no
Rajkot or Indian online source had a fixed-model price.  apple.com/in publishes the price of each SKU in its product page (schema.org
JSON-LD plus an embedded per-part-number `fullPrice`); robots.txt for apple.com disallows only overlay/payment fragments, not the product page.
Probed 2026-10-10 with the project's honest User-Agent.  Not a Rajkot price (Apple India is one national price): PROXY bucket.

Design (same rules as the other shadow candidates):
  * one fixed SKU (data/apple_store/pool.csv: part number MYE73HN/A, iPhone 16 128 GB Black, as listed on the page);
  * one request per run to the product page; the price is the first `fullPrice` after the part number's own entry in the page data;
    a price outside a sane band or a missing part number is skipped and reported, never carried forward;
  * accrues forward only (data/apple_store_prices.csv, top level so the daily bot commits it); a same-day rerun replaces that day's rows;
  * the model is a FIXED SKU: if Apple discontinues it, the part number disappears, accrual reports 'not on page' and the chain stops -
    a new model then needs its own pool row and a chain splice, decided by hand.  Hedonic replacement is NOT modelled here.

SHADOW.  Nothing reaches the index until K002 is switched to primary_source = apple_store in data/source_plan.csv.  The screen
(rpi/shadow.py) compares the chain with the official item index (proxy_check.judge: >= 6 overlapping months, corr >= 0.5, drift <= 0.10).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from .base import Observation

SOURCE_ID = "apple_store"
PAGE = "https://www.apple.com/in/shop/buy-iphone/iphone-16"
POOL = "data/apple_store/pool.csv"
LIVE = "data/apple_store_prices.csv"
COLS = ["date", "part_number", "item_id", "price", "currency", "url"]
PRICE_BAND = (20_000.0, 300_000.0)          # INR; a phone outside this band is a parsing error, not a price
WINDOW = 1500                                # characters after the part number's entry searched for its price
_PRICE = re.compile(r'"fullPrice"\s*:\s*([0-9]+(?:\.[0-9]+)?)')


def parse_price(html: str, part_number: str) -> float | None:
    """Price the page shows for one part number, or None (absent, or outside the sane band)."""
    key = f'"partNumber":"{part_number}"'
    i = html.find(key)
    if i < 0:
        return None
    m = _PRICE.search(html, i, i + WINDOW)
    if not m:
        return None
    p = float(m.group(1))
    return p if PRICE_BAND[0] <= p <= PRICE_BAND[1] else None


def load_pool(root: Path) -> pd.DataFrame:
    return pd.read_csv(Path(root) / POOL, dtype=str, keep_default_na=False)


def accrue(client, root: Path, today: dt.date | None = None) -> tuple[int, str]:
    """One page fetch; one row per pool part number that the page prices today."""
    today = today or dt.date.today()
    root = Path(root)
    pool = load_pool(root)
    r = client.get(PAGE)
    if r.status_code != 200:
        return 0, f"apple.com HTTP {r.status_code}"
    html = r.text
    rows, miss = [], []
    for p in pool.itertuples():
        price = parse_price(html, p.part_number)
        if price is None:
            miss.append(p.part_number)
            continue
        rows.append({"date": today.isoformat(), "part_number": p.part_number, "item_id": p.item_id, "price": price,
                     "currency": "INR", "url": PAGE})
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
    """The accrued quotes in the shared shadow schema (date, item_id, sku, unit_price, price, regular_price, qty_base, base_unit, title)."""
    path = Path(root) / LIVE
    cols = ["date", "item_id", "sku", "unit_price", "price", "regular_price", "qty_base", "base_unit", "title", "store"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["price"] = d.price.astype(float)
    d["sku"] = "apple:" + d.part_number
    d["unit_price"] = d.price
    d["regular_price"] = d.price
    d["qty_base"] = 1.0
    d["base_unit"] = "pc"
    d["title"] = "iPhone 16 128 GB Black (" + d.part_number + ")"
    d["store"] = "apple"
    return d[d.price > 0][cols]


def switched_items(root: Path, source_id: str = SOURCE_ID) -> list[str]:
    plan = pd.read_csv(Path(root) / "data/source_plan.csv", dtype=str, keep_default_na=False)
    return plan.loc[plan.primary_source == source_id, "item_id"].tolist()


class AppleStoreCollector:
    """Emits the accrued quotes of SWITCHED items only (primary_source = apple_store); in shadow mode it emits nothing."""
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
            yield Observation(dt.date(y, m, dd), SOURCE_ID, r.sku, r.title, r.item_id, "IN-NATIONAL", float(r.price),
                              regular_price=float(r.regular_price), qty_base=float(r.qty_base), base_unit=str(r.base_unit))
