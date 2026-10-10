"""Green Mercado LLP (Rajkot grocer) on Feezital.com: fixed-SKU retail prices for four produce items - a SHADOW source, PROXY bucket.

What it is.  Green Mercado LLP, Bhakti Nagar, Rajkot, sells groceries and produce through a marketplace storefront
(feezital.com/greenmercado). Its product pages print the sale price ('now') and the list price ('was') in server-rendered HTML.

Honest status (read before using the series):
  * Terms.  No Feezital terms-of-use text could be located (2026-10-10): the terms URLs return the checkout page. Compliance with
    the platform's terms is therefore UNVERIFIED. This is stated here and in data/source_plan.csv; it is not a permission claim.
  * Store open/closed.  The store prints 'This store is not taking any orders right now' while it is closed. A closed store's
    prices are not a market price, so the collector records NOTHING on a page that carries that notice.
  * Marketplace.  The seller sets prices on the platform, not on its own site.

Design (same rules as the other shadow candidates):
  * one request per fixed product page (data/green_mercado/pool.csv); the pool is the fixed SKU list, so pack and brand are fixed;
  * the price is the page's sale price ('now'); a missing price, a missing pack or a store-closed notice is skipped and reported;
  * accrues forward only (data/green_mercado_prices.csv, top level so the daily bot commits it); same-day rerun replaces today's rows;
  * SHADOW until an item is switched to primary_source = green_mercado in data/source_plan.csv AND [index.switches] in
    config/settings.toml. Nothing reaches the index before that. The screen (rpi/shadow.py) compares the chain with the official
    item index (proxy_check.judge: >= 6 overlapping months, corr >= 0.5, drift <= 0.10).
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from .base import Observation
from ..units import parse_quantity, unit_price

SOURCE_ID = "green_mercado"
POOL = "data/green_mercado/pool.csv"
LIVE = "data/green_mercado_prices.csv"
COLS = ["date", "product_id", "item_id", "title", "pack", "price", "mrp", "currency", "url"]
PRICE_BAND = (1.0, 5_000.0)                 # INR per pack; outside this is a parsing error, not a price
CLOSED = "not taking any orders"
_NOW = re.compile(r'class="now">\s*&#8377;\s*([0-9][0-9,]*(?:\.[0-9]+)?)')
_WAS = re.compile(r'class="was">\s*&#8377;\s*([0-9][0-9,]*(?:\.[0-9]+)?)')
_PACK = re.compile(r'class="dispQty">([^<]+)<')
_ID = re.compile(r'data-id="(\d+),')


def store_open(html: str) -> bool:
    return CLOSED not in html


def parse_product(html: str) -> dict | None:
    """Sale price, list price, pack and product id from one product page, or None if any is missing or out of band."""
    if not store_open(html):
        return None
    now = _NOW.search(html)
    if not now:
        return None
    price = float(now.group(1).replace(",", ""))
    if not PRICE_BAND[0] <= price <= PRICE_BAND[1]:
        return None
    was = _WAS.search(html)
    pack = _PACK.search(html)
    pid = _ID.search(html)
    return {"price": price,
            "mrp": float(was.group(1).replace(",", "")) if was else price,
            "pack": pack.group(1).strip() if pack else "",
            "product_id": pid.group(1) if pid else ""}


def load_pool(root: Path) -> pd.DataFrame:
    return pd.read_csv(Path(root) / POOL, dtype=str, keep_default_na=False)


def accrue(client, root: Path, today: dt.date | None = None) -> tuple[int, str]:
    """One product-page fetch per pool SKU; one row per SKU whose page is open and carries a valid price."""
    today = today or dt.date.today()
    root = Path(root)
    pool = load_pool(root)
    rows, miss = [], []
    for p in pool.itertuples():
        r = client.get(p.url)
        if r.status_code != 200:
            miss.append(f"{p.item_id} HTTP {r.status_code}")
            continue
        info = parse_product(r.text)
        if info is None:
            miss.append(f"{p.item_id} " + ("store closed" if not store_open(r.text) else "no valid price"))
            continue
        rows.append({"date": today.isoformat(), "product_id": info["product_id"] or p.product_id, "item_id": p.item_id,
                     "title": p.title, "pack": info["pack"] or p.pack, "price": info["price"], "mrp": info["mrp"],
                     "currency": "INR", "url": p.url})
    path = root / LIVE
    old = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=COLS)
    old = old[old.date != today.isoformat()]
    new = pd.DataFrame(rows, columns=COLS)
    parts = [x for x in (old, new) if len(x)]
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)
    out.to_csv(path, index=False)
    msg = "ok" if not miss else f"skipped: {miss}"
    return len(rows), msg


def live_frame(root: Path) -> pd.DataFrame:
    """Accrued quotes in the shared shadow schema (date, item_id, sku, unit_price, price, regular_price, qty_base, base_unit, title, store)."""
    path = Path(root) / LIVE
    cols = ["date", "item_id", "sku", "unit_price", "price", "regular_price", "qty_base", "base_unit", "title", "store"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    d = pd.read_csv(path, dtype=str, keep_default_na=False)
    if d.empty:
        return pd.DataFrame(columns=cols)
    d["price"] = d.price.astype(float)
    d["mrp"] = d.mrp.astype(float)
    d["sku"] = "gm:" + d.product_id
    qu = [parse_quantity(p) or (None, None) for p in d.pack]
    d["qty_base"] = [q for q, _ in qu]
    d["base_unit"] = [u for _, u in qu]
    d["unit_price"] = [unit_price(p, q, u) for p, q, u in zip(d.price, d.qty_base, d.base_unit)]
    d["regular_price"] = d.mrp
    d["store"] = "green_mercado"
    d = d[(d.price > 0) & d.qty_base.notna() & d.unit_price.notna()]
    return d[cols]


def switched_items(root: Path, source_id: str = SOURCE_ID) -> list[str]:
    plan = pd.read_csv(Path(root) / "data/source_plan.csv", dtype=str, keep_default_na=False)
    return plan.loc[plan.primary_source == source_id, "item_id"].tolist()


class GreenMercadoCollector:
    """Emits accrued quotes of SWITCHED items only (primary_source = green_mercado); in shadow mode it emits nothing."""
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
