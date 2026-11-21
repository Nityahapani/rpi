"""Swiggy Instamart - RETAIL shelf prices from a RAJKOT dark store (headless Chromium).

Why.  Every packaged good in the basket was previously priced outside Rajkot: DMart Ready serves no Rajkot pincode
(checked 2026-11-21: /api/v1/pincodes/search/360001 -> 0 stores) and Vishal is a national e-store.  Instamart DOES
serve Rajkot: with the browser geolocated to 22.3039/70.8022 and the page's own "Use current location" action, the
site resolves "Sadar, Rajkot, Gujarat 360001" and switches to pod/store 1395731, whose home + category payloads carry
per-SKU prices (`price.mrp`, `price.offerPrice`), pack size (`quantityDescription`, `weightInGrams`) and stock.

Access.  This module drives a headless Chromium, as a user's browser would, and reads the JSON the page itself fetches
(/api/instamart/home/v2).  If the site refuses - e.g. HTTP 202 "We'll be back shortly" once Swiggy rate-limits the
egress IP after repeated sessions - it raises InstamartBlocked and the refresh records the skip instead of writing a
partial series.

Accrual and replay are separate on purpose: `accrue()` needs the browser, `InstamartCollector` only replays
data/instamart_prices.csv, so a runner that cannot open a browser still indexes whatever this machine collected.

Data model (same rules as the DMart pool, fixed before any history existed):
  * a fixed SKU pool per basket item (data/instamart/pool.csv), built from what the Rajkot store actually stocks;
  * price = offerPrice (what a shopper pays), regular_price = mrp (the promo-free variant);
  * unit price from the pack label, re-read every day, so a shrunk pack shows up as a unit-price rise;
  * unavailable SKUs are skipped, never carried forward;
  * accrues forward only (no archive), so earlier months keep the official stand-in via BACKFILL_SOURCES;
  * wired for the packaged-goods items from 2026-12 (config [index.switches]); 2026-11 accrual is the link month.

    PYTHONPATH=. python3 scripts/build_instamart_pool.py      # build the pool from the live Rajkot store
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .base import Observation

SOURCE_ID = "instamart_rajkot"
LAT, LON = 22.3039, 70.8022
STORE_ID = "1395731"          # Sadar, Rajkot 360001 (pod id; also carries the store pincode)
STORE_PINCODE = "360001"
POOL = "data/instamart/pool.csv"
LIVE = "data/instamart_prices.csv"
LIVE_COLS = ["date", "sku_id", "item_id", "name", "pack", "price", "regular_price", "qty_base", "base_unit", "unit_price"]
HOME_API = "/api/instamart/home/v2?offset={o}&layoutId=4987&storeId={s}&primaryStoreId={s}&secondaryStoreId=&clientId=INSTAMART-APP"
MAX_OFFSET = 10

# basket item -> title regex.  Deliberately narrow: one mainstream SKU family per item, so the matched-model
# Jevons chain sees the same product month after month.  Anything ambiguous is left for the pool builder to reject.
ITEM_RULES = {
    "F014": r"^(Tata Tea Gold|Brooke Bond Red Label|Tata Tea Premium)\b",
    "F017": r"^(Parle-G|Britannia Good Day|Britannia Marie Gold|Sunfeast Marie Light)\b",
    "P001": r"^(Dettol Original Soap|Lifebuoy|Santoor|Cinthol|Lux)\b",
    "P002": r"^(Clinic Plus|Sunsilk|Head & Shoulders|Dove|Tresemme)\b",
    "P003": r"^(Colgate Strong Teeth|Colgate MaxFresh|Pepsodent|Dabur Red)\b",
    "H001": r"^(Surf Excel|Ariel|Tide|Ghadi|Nirma)\b",
    "H002": r"^(Vim|Pril)\b",
    "F018": r"^(Maggi|Yippee)\b",
    "F012": r"^(Amul|Sagar|Nestle|Mother Dairy).*Ghee",
    "F010": r"^(Amul|Mother Dairy).*(Curd|Dahi|Yogurt)",
    "F019": r"^(Britannia|Modern).*Bread",
    "F015": r"^(Tata Salt|Sundar|Naayak)",
    "F013": r"^(Madhur|Uttam|Parrys).*Sugar",
    "H003": r"\b(LED|Bulb)\b",
    "H004": r"\b(Pressure Cooker|Cooker)\b",
    "E003": r"\b(Notebook|Register|Long Book)\b",
    "M002": r"(Dettol Antiseptic|Savlon)",
    "F001": r"(Aashirvaad|Pillsbury|Lokwan).*(Atta|Wheat Flour)",
    "F002": r"(India Gate|Daawat).*Basmati",
    "F003": r"^(Tata Sampann|Rajdhani).*(Toor|Arhar)",
    "F004": r"^(Tata Sampann|Rajdhani).*Moong",
    "F005": r"^(Tata Sampann|Rajdhani).*Chana",
    "F008": r"(Fortune|Sweekar|Saffola).*(Sunflower)",
    "F007": r"(Fortune|Rasoi).*Cottonseed",
    "F006": r"(Fortune|Dhara).*Groundnut",
}


class InstamartBlocked(RuntimeError):
    pass


# ----------------------------------------------------------------------------------------------------------- pure parsing
def _rupees(money) -> float | None:
    """{'currencyCode':'INR','units':'31','nanos':0} -> 31.0"""
    if not isinstance(money, dict):
        return None
    try:
        g = float(money.get("units") or 0) + float(money.get("nanos") or 0) / 1e9
    except (TypeError, ValueError):
        return None
    return g if g > 0 else None


def parse_items(payload: dict) -> list[dict]:
    """Home/category payload -> one row per purchasable variation.

    Walks the gandalf card tree for `ItemCollectionCard.items[].variations[]`.  Pure, so it is unit-tested on a saved
    payload and can be re-run over archived raw snapshots.
    """
    out: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            if "items" in node and isinstance(node["items"], list) and "variations" in (node["items"][0] if node["items"] else {}):
                for it in node["items"]:
                    for v in it.get("variations") or []:
                        price = v.get("price") or {}
                        offer, mrp = _rupees(price.get("offerPrice")), _rupees(price.get("mrp"))
                        sku = v.get("skuId")
                        if not sku or not offer:
                            continue
                        out[sku] = dict(sku_id=sku, name=it.get("displayName") or v.get("displayName") or "",
                                        brand=it.get("brand") or v.get("brandName") or "",
                                        pack=v.get("quantityDescription") or "",
                                        price=offer, regular_price=mrp,
                                        in_stock=bool((v.get("inventory") or {}).get("inStock", v.get("inStock", True))),
                                        weight_g=v.get("weightInGrams"))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return list(out.values())


def assign_item(name: str, brand: str) -> str | None:
    """Basket item for a listing, or None.

    Patterns are written against the PRODUCT NAME ("Tata Tea Gold 1 kg"), which is how a shelf tile reads, so the name
    is tried first.  A pattern that starts with a brand family ("^(Amul|Sagar)...Ghee") also matches the combined
    'brand name' string, which is the only place that brand appears on some tiles - the leading anchor is dropped for
    that second attempt, never the specific words.
    """
    import re
    name = (name or "").strip()
    both = f"{brand or ''} {name}".strip()
    for item, pat in ITEM_RULES.items():
        if re.search(pat, name, re.I):
            return item
        if re.search(pat.lstrip("^"), both, re.I):
            return item
    return None


# ----------------------------------------------------------------------------------------------------------- browser
async def _select_rajkot(pg, wait_first: int = 3000) -> str:
    """Make the page report a Rajkot store.  Returns the address line shown, or raises InstamartBlocked.

    Two paths, because the site renders differently on a cold vs a warm session:
      * a location is already stored -> the header shows it and there is no modal to open;
      * otherwise the "Add your location" widget opens a modal whose "Use current location" action resolves the
        browser's geolocation (22.3039/70.8022) to the Rajkot store.
    """
    await pg.wait_for_timeout(wait_first)
    for _ in range(3):
        body = await pg.inner_text("body")
        if "Rajkot" in body:
            for line in body.splitlines():
                if "Rajkot" in line:
                    return line.strip()[:80]
        if "be back shortly" in body or "temporary glitch" in body:
            await pg.wait_for_timeout(8000)          # transient front-end back-off, not a block
            continue
        try:
            title = pg.locator('[data-testid="DEFAULT_ADDRESS_TITLE"]')
            if await title.count():
                await title.first.click(force=True, timeout=8000)
                await pg.wait_for_timeout(2000)
            use = pg.get_by_text("Use current location", exact=False)
            if await use.count():
                await use.first.click(force=True, timeout=15000)
                await pg.wait_for_timeout(5000)
                continue
        except Exception:  # noqa: BLE001 - the loop retries the whole sequence
            await pg.wait_for_timeout(2000)
    body = await pg.inner_text("body")
    raise InstamartBlocked(f"no Rajkot store resolved; page says {body[:140]!r}")


async def _harvest(offsets=MAX_OFFSET, headed: bool = False) -> list[dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--no-sandbox"])
        ctx = await b.new_context(
            locale="en-IN", timezone_id="Asia/Kolkata", viewport={"width": 1366, "height": 900},
            geolocation={"latitude": LAT, "longitude": LON}, permissions=["geolocation"],
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        )
        pg = await ctx.new_page()
        try:
            await pg.goto("https://www.swiggy.com/instamart", wait_until="domcontentloaded", timeout=60_000)
            addr = await _select_rajkot(pg)
            rows: dict[str, dict] = {}
            for o in range(1, offsets + 1):
                payload = await pg.evaluate(
                    """async (u) => { const r = await fetch(u, {headers:{'Accept':'application/json'}, credentials:'include'});
                                       return r.status === 200 ? await r.text() : ''; }""",
                    HOME_API.format(o=o, s=STORE_ID))
                if not payload:
                    continue
                for r in parse_items(json.loads(payload)):
                    rows[r["sku_id"]] = r
            if not rows:
                raise InstamartBlocked("Rajkot store loaded but returned no priced items")
            return list(rows.values())
        finally:
            await b.close()


def harvest() -> list[dict]:
    try:
        import playwright.async_api  # noqa: F401
    except ModuleNotFoundError as e:   # the daily runner indexes the accrued CSV without a browser; accrual is optional there
        raise InstamartBlocked("playwright is not installed on this machine; accrual skipped") from e
    return asyncio.run(_harvest())


# ----------------------------------------------------------------------------------------------------------- accrual
def build_pool(rows: list[dict], today: dt.date) -> pd.DataFrame:
    """Keep the largest mainstream pack (>= the item's usual retail size) per item, one variant per SKU."""
    from rpi.units import parse_quantity
    out = []
    for r in rows:
        if not r["in_stock"]:
            continue
        item = assign_item(r["name"], r["brand"])
        if item is None:
            continue
        qty, unit = parse_quantity(r["pack"])
        if qty is None:
            continue
        out.append(dict(r, item_id=item, qty_base=qty, base_unit=unit, selected_on=today.isoformat()))
    df = pd.DataFrame(out)
    return df.drop_duplicates("sku_id") if len(df) else df


def accrue(path: Path, pool_csv: Path, rows: list[dict] | None = None, today: dt.date | None = None) -> tuple[int, str]:
    """Append today's pooled quotes to the live file (idempotent per day)."""
    from rpi.units import parse_quantity, unit_price
    today = today or dt.date.today()
    pool = pd.read_csv(pool_csv, dtype=str)
    rows = rows if rows is not None else harvest()
    by_sku = {r["sku_id"]: r for r in rows}
    got = []
    for _, p in pool.iterrows():
        r = by_sku.get(p.sku_id)
        if not r or not r["in_stock"]:
            continue
        qty, unit = parse_quantity(r["pack"]) or (float(p.qty_base), p.base_unit)
        up = unit_price(float(r["price"]), float(qty), unit)
        got.append(dict(date=today.isoformat(), sku_id=p.sku_id, item_id=p.item_id, name=r["name"][:80],
                        pack=r["pack"], price=float(r["price"]), regular_price=r["regular_price"],
                        qty_base=float(qty), base_unit=unit, unit_price=up))
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=LIVE_COLS)
    new = pd.concat([old[old.date != today.isoformat()], pd.DataFrame(got, columns=LIVE_COLS)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False)
    return len(got), f"{len(got)}/{len(pool)} pool SKUs priced at Rajkot store {STORE_ID}"


# ----------------------------------------------------------------------------------------------------------- collector contract
def switched_items(root: Path) -> list[str]:
    """Items whose primary_source is this feed (data/source_plan.csv)."""
    plan = pd.read_csv(Path(root) / "data/source_plan.csv", dtype=str, keep_default_na=False)
    return plan.loc[plan.primary_source == SOURCE_ID, "item_id"].tolist()


class InstamartCollector:
    """Replays the accrued Rajkot shelf quotes into the index.

    Accrual is separated from replay on purpose: `accrue()` needs a browser and a live network, while ingestion must
    also work on a machine that cannot reach Swiggy (the daily runner) using the rows already in
    data/instamart_prices.csv.  Emitting only items that the plan routes to this source keeps it a shadow feed until a
    recorded switch, exactly like rajkot_shops.
    """
    source_id = SOURCE_ID
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.root = Path(root)

    def collect(self, on_date):
        items = set(switched_items(self.root))
        live = Path(self.root) / LIVE
        if not items or not live.is_file():
            return
        d = pd.read_csv(live, dtype={"sku_id": str})
        for r in d[d.item_id.isin(items)].itertuples():
            y, m, dd = (int(x) for x in str(r.date).split("-"))
            yield Observation(dt.date(y, m, dd), SOURCE_ID, str(r.sku_id), f"{r.name} @ Instamart Rajkot",
                              r.item_id, STORE_PINCODE, float(r.price),
                              regular_price=(None if pd.isna(r.regular_price) else float(r.regular_price)),
                              qty_base=float(r.qty_base), base_unit=str(r.base_unit))
