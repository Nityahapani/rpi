"""Brand-store MRP diary: fixed-SKU list prices read from a manufacturer's own public Shopify feed, one row per SKU per day.

Scope today: H003 'LED bulb 9W' -> Crompton Dynaray 9 W and Bajaj Ivora Plus 9 W; H004 'pressure cooker 3L' -> Bajaj 3 L cookers.  Crompton lists a single MRP-type price
(no compare_at, no discount ladder), so unlike Jockey / Paragon the number is not a sale price.  It is an ACCRUING DIAGNOSTIC and is
NOT an index input: the Jan-2025 baseline is unverified (the Wayback captures of Feb and Jul 2025 are JS shells with no price; the Aug-2025
and Oct-2025 captures show Rs 150), and a series that never moves cannot pass the correlation gate (rpi.proxy_check.judge).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

import re

STORE = "https://www.crompton.co.in"
ITEM = "H003"
HANDLES = ("9w-b22-dynaray-led-bulb", "9w-e27-dynaray-led-bulb", "9w-e27-dynaray-led-bulb-1", "9w-e27-dynaray-led-bulb-2")
# (brand, store, item, product handles, regex a variant title must match (None = all variants)).  Bajaj Electricals' Shopify feed carries
# list prices only (0 of 718 products has a compare_at), 3 L pressure cookers (H004, "fixed model") and the 9 W Ivora Plus LED lamp.
BAJAJ = "https://www.bajajelectricals.com"
SERIES = (
    ("Crompton", STORE, "H003", HANDLES, None),
    ("Bajaj", BAJAJ, "H003", ("ivora-plus-hb-led-lamp-9w-cdl",), None),
    ("Bajaj", BAJAJ, "H004", ("inner-lid-aluminium-pressure-cooker", "outer-lid-aluminium-pressure-cooker", "inner-lid-handi-shaped-aluminium-pressure-cooker",
                              "inner-lid-stainless-steel-pressure-cooker", "outer-lid-stainless-steel-pressure-cooker",
                              "nutrihealth-outer-lid-stainless-steel-pressure-cooker"), r"^\s*3\s?L"),
)
COLS = ["date", "item_id", "brand", "handle", "sku", "variant", "price", "compare_at", "provenance"]
# Verified archived observations (web.archive.org/web/<ts>id_/<page>; variant JSON read from the stored HTML), SKU LED9WNDFWB2SCDL / ...1SWW.
ARCHIVE = [("2025-08-16", "20250816024909", 150.0), ("2025-10-08", "20251008074207", 150.0)]


def parse_product(text: str) -> list[dict]:
    p = json.loads(text)["product"]
    return [dict(handle=p["handle"], sku=v.get("sku") or "", variant=v.get("title", ""), price=float(v["price"]),
                 compare_at=float(v["compare_at_price"]) if v.get("compare_at_price") else None) for v in p["variants"]]


def seed_archive(path: Path) -> int:
    if path.exists():
        return 0
    rows = []
    for d, ts, price in ARCHIVE:
        for sku, var in (("LED9WNDFWB2SCDL", "Cool Day Light"), ("LED9WNDFWB1SWW", "Warm White")):
            rows.append(dict(date=d, item_id=ITEM, brand="Crompton", handle=HANDLES[0], sku=sku, variant=var, price=price, compare_at=None,
                             provenance=f"wayback:{ts}"))
    pd.DataFrame(rows, columns=COLS).to_csv(path, index=False)
    return len(rows)


def accrue(path: Path, client, today: dt.date | None = None) -> tuple[int, str]:
    today = today or dt.date.today()
    seed_archive(path)
    df = pd.read_csv(path, dtype={"sku": str})
    new = []
    for brand, store, item, handles, vre in SERIES:
        for h in handles:
            r = client.get(f"{store}/products/{h}.json")
            if r.status_code != 200:
                raise RuntimeError(f"{brand} {h}: HTTP {r.status_code}")
            for v in parse_product(r.text):
                if v["price"] <= 0 or (vre and not re.search(vre, v["variant"])):
                    continue
                new.append(dict(date=today.isoformat(), item_id=item, brand=brand, **v, provenance="live"))
    df = pd.concat([df, pd.DataFrame(new, columns=COLS)]).drop_duplicates(["date", "handle", "sku", "variant"], keep="last")
    df.sort_values(["date", "handle", "sku"]).to_csv(path, index=False)
    return len(new), summarise(df)


def summarise(df: pd.DataFrame) -> str:
    d = df.copy()
    d["m"] = d["date"].str[:7]
    changed = int((d.sort_values("date").groupby(["sku", "variant"])["price"].apply(lambda s: (s.diff().abs() > 0).sum())).sum())
    per = "; ".join(f"{i}: {g['sku'].nunique()} SKUs, {g['m'].nunique()} month(s) since {g['m'].min()}, median Rs {g[g['date'] == g['date'].max()]['price'].median():.0f}"
                    for i, g in d.groupby("item_id"))
    return f"{per}; {changed} price change(s) seen; diagnostic only (no verified Jan-2025 baseline; flat series cannot pass the gate)"
