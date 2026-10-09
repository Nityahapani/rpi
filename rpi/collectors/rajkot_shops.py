"""Rajkot web shops: shelf prices from Rajkot retailers' OWN online stores (Shopify / WooCommerce feeds) - a SHADOW source.

Why this exists.  About a quarter of the basket weight is priced outside Rajkot: DMart Ready's Ahmedabad store (15.4%, Rajkot pincodes are
not served) and the DoCA all-India panel (9.1%).  The obvious fix - quick-commerce apps with Rajkot dark stores (Blinkit 7, Instamart 4,
Zepto 2 per quickcommercemap.com, July 2026) - is not open to this project.  Probed 2026-10-10 with the project's honest User-Agent:
blinkit.com answers HTTP 403 from Cloudflare (even for robots.txt), jiomart.com an Akamai 'Access Denied', zepto.com and
swiggy.com/instamart an AWS-WAF JavaScript challenge (HTTP 202, empty body) - including Zepto's server-rendered /city/Rajkot/ pages.
Getting past those would be bot-protection evasion, which this project never does (collectors/base.py PoliteClient).

What is used instead: Rajkot businesses that sell online through standard storefront platforms whose product feeds are public and
allowed by robots.txt (checked 2026-10-10):

    store         feed                                   who / what
    green_force   greenforcefood.com/products.json       Green Force Food, New Marketing Yard, Bedi, Morbi Road, Rajkot - staples
    hathi_masala  hathimasala.com/products.json          Gandhi Spices Pvt Ltd (Hathi Masala), Rajkot - spices
    rani_oil      ranioil.com/wp-json/wc/store/v1        Rani Oil, Gondal Road, Rajkot (delivers in Rajkot and Ahmedabad) - edible oils

Design (same rules as the DMart pool, fixed before any history existed):
  * a fixed SKU pool per basket item (data/rajkot_shops/pool.csv, written by scripts/build_rajkot_shops_pool.py on 2026-10-10); the item
    series is the matched-model Jevons chain of the SKUs' unit prices, so brand mix and pack size never move it;
  * price = what a shopper pays (Shopify `price`, WooCommerce `prices.price`); regular_price = compare-at / regular price;
  * unavailable or zero-priced SKUs are skipped, not carried forward; the pack is re-read from the label every day, so a shrunk pack shows
    up as a unit-price increase;
  * at most a few requests per store per run (whole catalogue per request), 4 s apart, and a store is skipped on its first non-200 reply;
  * accrues forward only: the Wayback Machine holds only the stores' home pages, never a product feed.

SHADOW.  Nothing here reaches the index until an item is switched in data/source_plan.csv (primary_source = rajkot_shops): the collector
emits observations for switched items only.  The screen (rpi/shadow.py, refresh step screen:shadow_sources) compares each item's chain
with the official Gujarat-urban item index (proxy_check.judge: >= 6 overlapping months, corr >= 0.5, drift <= 0.10) and with the item's
current source.  Switching is a recorded decision, never automatic.

Caveats, stated: these are single-seller list prices (for oil and spices the seller is the manufacturer), so a store's price list can be
sticky; a Rajkot store's price is still the right population, which an Ahmedabad shelf or an all-India average is not.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .base import Observation
from ..units import parse_quantity, unit_price

SOURCE_ID = "rajkot_shops"
POOL = "data/rajkot_shops/pool.csv"
# Top-level data/*.csv ON PURPOSE: the daily workflow commits only data/rpi.sqlite, data/*.csv, data/official, data/mrp and docs,
# so an accrual file in a sub-folder would be lost on every bot run.  (The pool is static and may live in a sub-folder.)
LIVE = "data/rajkot_shops_prices.csv"
LIVE_COLS = ["date", "store", "item_id", "variant_id", "pack", "price", "regular_price", "qty_base", "base_unit", "unit_price"]

STORES = {
    "green_force": dict(platform="shopify", base="https://greenforcefood.com", pincode="360003",
                        name="Green Force Food, New Marketing Yard, Bedi, Morbi Road, Rajkot"),
    "hathi_masala": dict(platform="shopify", base="https://hathimasala.com", pincode="360004",
                         name="Hathi Masala (Gandhi Spices Pvt Ltd), Rajkot"),
    "rani_oil": dict(platform="woocommerce", base="https://www.ranioil.com", pincode="360004",
                     name="Rani Oil, Gondal Road, Rajkot"),
}
SHOPIFY_PAGE, WOO_PAGE, MAX_PAGES = 250, 100, 6


class ShopBlocked(RuntimeError):
    pass


def parse_shopify(payload: dict) -> list[dict]:
    """Shopify /products.json -> one row per variant.  Pure."""
    out = []
    for p in payload.get("products") or []:
        for v in p.get("variants") or []:
            try:
                price = float(v.get("price") or 0)
                reg = float(v.get("compare_at_price") or 0) or None
            except (TypeError, ValueError):
                continue
            out.append(dict(product_id=str(p.get("id")), variant_id=str(v.get("id")), product_title=p.get("title", ""),
                            variant_title=v.get("title", ""), price=price, regular_price=reg, available=bool(v.get("available"))))
    return out


def parse_woo(payload: list) -> list[dict]:
    """WooCommerce Store API /products -> one row per SIMPLE product (variable products need one call per variation; skipped).  Pure."""
    out = []
    for p in payload or []:
        if p.get("type") not in (None, "simple"):
            continue
        pr = p.get("prices") or {}
        mu = int(pr.get("currency_minor_unit", 2) or 0)
        try:
            price = int(pr.get("price") or 0) / 10 ** mu
            reg = int(pr.get("regular_price") or 0) / 10 ** mu or None
        except (TypeError, ValueError):
            continue
        out.append(dict(product_id=str(p.get("id")), variant_id=str(p.get("id")), product_title=p.get("name", ""), variant_title="",
                        price=price, regular_price=reg,
                        available=bool(p.get("is_in_stock", True)) and bool(p.get("is_purchasable", True))))
    return out


def pack_of(product_title: str, variant_title: str):
    """(qty_base, base_unit) from the variant label ('1 Kg', '500 Gm'), else from the product title ('... 15-Ltr Tin')."""
    q = parse_quantity(variant_title) if variant_title and variant_title.lower() != "default title" else None
    return q or parse_quantity(product_title) or (None, None)


def fetch_catalogue(client, store: str) -> list[dict]:
    """Whole catalogue of one store (a handful of requests).  Raises ShopBlocked on the first non-200."""
    cfg = STORES[store]
    rows: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        if cfg["platform"] == "shopify":
            r = client.get(f"{cfg['base']}/products.json", params={"limit": SHOPIFY_PAGE, "page": page})
        else:
            r = client.get(f"{cfg['base']}/wp-json/wc/store/v1/products", params={"per_page": WOO_PAGE, "page": page})
        if r.status_code != 200:
            raise ShopBlocked(f"HTTP {r.status_code} from {cfg['base']} (page {page}); store skipped this run")
        if cfg["platform"] == "shopify":
            got = parse_shopify(r.json())
            n_raw = len(r.json().get("products") or [])
            rows += got
            if n_raw < SHOPIFY_PAGE:
                break
        else:
            data = r.json()
            rows += parse_woo(data)
            total_pages = int(r.headers.get("X-WP-TotalPages", "1") or 1)
            if page >= total_pages or len(data) < WOO_PAGE:
                break
    return rows


def accrue(client, root: Path, today: dt.date | None = None) -> tuple[int, str]:
    """Price every pool SKU once; today's rows replace any earlier rows of the same day for the stores that answered."""
    today = today or dt.date.today()
    root = Path(root)
    pool = pd.read_csv(root / POOL, dtype={"product_id": str, "variant_id": str})
    rows, msgs, ok_stores = [], [], []
    for store, g in pool.groupby("store"):
        try:
            cat = {r["variant_id"]: r for r in fetch_catalogue(client, store)}
        except ShopBlocked as e:
            msgs.append(f"{store}: {e}")
            continue
        except Exception as e:  # noqa: BLE001 - one store failing must not stop the others
            msgs.append(f"{store}: {type(e).__name__}: {str(e)[:80]}")
            continue
        ok_stores.append(store)
        priced = missing = 0
        for p in g.itertuples():
            r = cat.get(str(p.variant_id))
            if r is None:
                missing += 1
                continue
            if not r["available"] or r["price"] <= 0:
                continue
            qty, unit = pack_of(r["product_title"], r["variant_title"])
            if qty is None:                                     # unreadable label today: keep the pack recorded at selection
                qty, unit = float(p.qty_base), str(p.base_unit)
            reg = r["regular_price"] if (r["regular_price"] or 0) >= r["price"] else r["price"]
            rows.append(dict(date=today.isoformat(), store=store, item_id=p.item_id, variant_id=str(p.variant_id),
                             pack=r["variant_title"] or r["product_title"][-24:], price=r["price"], regular_price=reg,
                             qty_base=qty, base_unit=unit, unit_price=round(unit_price(r["price"], qty, unit), 4)))
            priced += 1
        msgs.append(f"{store} {priced}/{len(g)} priced" + (f", {missing} no longer listed" if missing else ""))
    path = root / LIVE
    old = pd.read_csv(path, dtype={"variant_id": str}) if path.exists() else pd.DataFrame(columns=LIVE_COLS)
    keep = old[~((old.date == today.isoformat()) & old.store.isin(ok_stores))]
    new = pd.concat([x for x in (keep, pd.DataFrame(rows, columns=LIVE_COLS)) if len(x)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    (new if len(new) else pd.DataFrame(columns=LIVE_COLS)).to_csv(path, index=False)
    return len(rows), "; ".join(msgs)


def live_frame(root: Path) -> pd.DataFrame:
    """The accrued quotes in the shared shadow schema (date, item_id, sku, unit_price, price, regular_price, qty_base, base_unit, title)."""
    root = Path(root)
    path = root / LIVE
    if not path.exists():
        return pd.DataFrame(columns=["date", "item_id", "sku", "unit_price", "price", "regular_price", "qty_base", "base_unit", "title", "store"])
    d = pd.read_csv(path, dtype={"variant_id": str})
    pool = pd.read_csv(root / POOL, dtype={"variant_id": str})[["store", "variant_id", "product_title", "variant_title"]]
    d = d.merge(pool, on=["store", "variant_id"], how="left")
    d["sku"] = d.store + ":" + d.variant_id
    d["title"] = (d.product_title.fillna("") + " " + d.variant_title.fillna("")).str.strip()
    return d[d.price > 0]


def switched_items(root: Path, source_id: str = SOURCE_ID) -> list[str]:
    plan = pd.read_csv(Path(root) / "data/source_plan.csv", dtype=str, keep_default_na=False)
    return plan.loc[plan.primary_source == source_id, "item_id"].tolist()


class RajkotShopsCollector:
    """Emits the live quotes of SWITCHED items only (primary_source = rajkot_shops); in shadow mode it emits nothing."""
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
            yield Observation(dt.date(y, m, dd), SOURCE_ID, r.sku, r.title, r.item_id, STORES[r.store]["pincode"], float(r.price),
                              regular_price=float(r.regular_price), qty_base=float(r.qty_base), base_unit=str(r.base_unit))
