"""1mg online pharmacy: fixed-SKU MRP of a paracetamol 500 mg strip (M001 'Paracetamol 500mg strip', per tablet).

What it prices.  One fixed product in data/onemg/pool.csv: Calpol 500 + Tablet (GSK), a strip of 15 tablets, product page
https://www.1mg.com/drugs/calpol-500-tablet-878516 (in stock when probed 2026-10-12, MRP inclusive of taxes).
The price is the pack price on the page divided by the tablets in the pack, so the quote is per tablet, the same unit as
the NPPA ceiling it replaces (M001 tariff rows are per tablet: Rs0.9765 incl. GST, S.O. 1575(E) 25.03.2026).

Rules (same as the other fixed-SKU feeds):
  * one plain HTTP GET per run through the project's PoliteClient (robots.txt respected, honest User-Agent);
  * a page that shows the product as unavailable ('unavailable_view' or 'Sold out') yields NO quote; a sold-out MRP is
    not a transaction price and is never carried forward;
  * the price must be the first ``"price":"Rs"`` in the best-offer block and inside a sane band for one strip;
  * accrues forward only (data/onemg_prices.csv, top level so the daily bot commits it); a same-day rerun replaces that day's rows.

SWITCHED, not shadow: M001 is switched to this source from 2026-11 in config/settings.toml [index.switches], and the switch is
recorded in data/source_plan.csv (primary_source = onemg_medicine). The M001 tariff rows stay as history before the switch.
Note: this is a single brand's MRP, not the NPPA ceiling; the ceiling is the regulated cap every brand must respect.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from .base import Observation

SOURCE_ID = "onemg_medicine"
POOL = "data/onemg/pool.csv"
LIVE = "data/onemg_prices.csv"
COLS = ["date", "item_id", "product_id", "pack_units", "pack_price", "unit_price", "url"]
PRICE_BAND = (1.0, 2_000.0)                     # INR for one strip; outside this is a parsing error
UNAVAILABLE = ("unavailable_view", "Sold out")
_PRICE = re.compile(r'"price":"\D{0,4}?([0-9]+(?:\.[0-9]+)?)"')     # any currency prefix: the page's charset can arrive mis-decoded
_BEST = '"type":"best_offer_default_view"'


def parse_pack_price(html: str) -> float | None:
    """Pack price of the in-stock product, or None (unavailable, missing, or outside the band)."""
    if any(u in html for u in UNAVAILABLE):
        return None
    i = html.find(_BEST)
    if i < 0:
        return None
    m = _PRICE.search(html, i)
    if not m:
        return None
    p = float(m.group(1))
    return p if PRICE_BAND[0] <= p <= PRICE_BAND[1] else None


def load_pool(root: Path) -> pd.DataFrame:
    return pd.read_csv(Path(root) / POOL, dtype=str, keep_default_na=False)


def accrue(client, root: Path, today: dt.date | None = None) -> tuple[int, str]:
    """One page fetch per pool row; one row per product the page prices today."""
    today = today or dt.date.today()
    root = Path(root)
    pool = load_pool(root)
    rows, miss = [], []
    for p in pool.itertuples():
        r = client.get(p.url)
        if r.status_code != 200:
            miss.append(f"{p.product_id}: HTTP {r.status_code}")
            continue
        raw = getattr(r, "content", None)
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else r.text
        pack = parse_pack_price(text)
        units = float(p.pack_units)
        if pack is None or units <= 0:
            miss.append(f"{p.product_id}: unavailable or no price")
            continue
        rows.append({"date": today.isoformat(), "item_id": p.item_id, "product_id": p.product_id,
                     "pack_units": int(units), "pack_price": pack, "unit_price": round(pack / units, 6), "url": p.url})
    path = root / LIVE
    old = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=COLS)
    old = old[old.date != today.isoformat()]                    # same-day rerun replaces today's rows
    new = pd.DataFrame(rows, columns=COLS)
    parts = [x for x in (old, new) if len(x)]
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)
    out.to_csv(path, index=False)
    msg = "ok" if not miss else f"not priced today: {miss}"
    return len(rows), msg


def live_frame(root: Path) -> pd.DataFrame:
    """Accrued quotes in the shared shadow schema (date, item_id, sku, unit_price, price, regular_price, qty_base, base_unit, title, store)."""
    cols = ["date", "item_id", "sku", "unit_price", "price", "regular_price", "qty_base", "base_unit", "title", "store"]
    path = Path(root) / LIVE
    if not path.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["unit_price"] = d.unit_price.astype(float)
    d["sku"] = "1mg:" + d.product_id
    d["price"] = d.unit_price
    d["regular_price"] = d.unit_price
    d["qty_base"] = 1.0
    d["base_unit"] = "pc"
    d["title"] = "Calpol 500 mg, strip of " + d.pack_units + " tablets (1mg)"
    d["store"] = "1mg"
    return d[d.unit_price > 0][cols]


def switched_items(root: Path, source_id: str = SOURCE_ID) -> list[str]:
    plan = pd.read_csv(Path(root) / "data/source_plan.csv", dtype=str, keep_default_na=False)
    return plan.loc[plan.primary_source == source_id, "item_id"].tolist()


class OneMgMedicineCollector:
    """Emits the accrued per-tablet quotes of SWITCHED items only."""
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
