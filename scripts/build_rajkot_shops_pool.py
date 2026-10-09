"""Select the fixed SKU pool for the Rajkot web-shop source (rpi/collectors/rajkot_shops.py) -> data/rajkot_shops/pool.csv.

Run once, before any history exists (2026-10-10); rerunning overwrites the pool and therefore breaks the matched-model chain, so only do
it to ADD items, never to replace SKUs that are already accruing.  Selection rule per basket item: the store's mainstream product(s) for the
item's spec, every listed pack within the item's usual sizes, priced and in stock on the selection day.  The rules are explicit below so
the choice is auditable.

    PYTHONPATH=. python3 scripts/build_rajkot_shops_pool.py
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rpi.collectors.base import PoliteClient          # noqa: E402
from rpi.collectors.rajkot_shops import POOL, fetch_catalogue, pack_of   # noqa: E402
from rpi.config import load_settings                   # noqa: E402

G, ML = "g", "ml"
# item, store, product-title regex, allowed pack sizes (base units), why
RULES = [
    ("F016", "hathi_masala", r"^Super Turmeric Powder \(Haldi Powder\)$", {(200, G), (500, G), (1000, G)}, "Rajkot spice maker, two mainstream turmeric lines"),
    ("F016", "hathi_masala", r"^Rajapuri Turmeric Powder", {(200, G), (500, G), (1000, G)}, ""),
    ("F008", "rani_oil", r"^Refined Sunflower Oil (1-Ltr Pouch|1-Ltr Bottle|5-Ltr Jar|15-Ltr Tin)$", None, "Rajkot oil brand; pouch, bottle, jar and the 15 L tin households buy"),
    ("F007", "rani_oil", r"^Refined Cottonseed Oil (1-Ltr Pouch|1-Ltr Bottle|5-Ltr Jar|15-Kg Tin)$", None, ""),
    ("F006", "rani_oil", r"^Double Filtered Groundnut Oil (1-Ltr Pouch|1-Ltr Bottle|5 Ltr Jar|15-Kg Tin)$", None, "second Rajkot source next to DoCA Rajkot"),
    ("F002", "green_force", r"^Basmati Rice \(", {(1000, G), (2000, G), (5000, G)}, "Rajkot staples store (marketing yard, Morbi Road)"),
    ("F002", "green_force", r"^Premium Basmati Rice", {(1000, G), (2000, G), (5000, G)}, ""),
    ("F003", "green_force", r"^Toor Dal (Oil )?\(", {(500, G), (1000, G)}, "oiled and unoiled tur dal"),
    ("F005", "green_force", r"^Chana Dal \(", {(500, G), (1000, G)}, ""),
    ("F004", "green_force", r"^Moong Dal \(", {(500, G), (1000, G)}, "replaces a wholesale APMC proxy with a retail price"),
    ("F001", "green_force", r"^Wheat Flour / Gehu Atta", {(1000, G), (5000, G)}, "replaces a wholesale APMC proxy with a retail price"),
    ("F013", "green_force", r"^Sugar \(", {(1000, G), (2000, G), (5000, G)}, "second Rajkot source next to DoCA Rajkot"),
    ("F026", "green_force", r"^Parasmani Jaggery", {(1000, G)}, "second Rajkot source next to DoCA Rajkot"),
]


def select(catalogues: dict[str, list[dict]], today: dt.date) -> pd.DataFrame:
    rows = []
    for item, store, pat, sizes, why in RULES:
        for r in catalogues.get(store, []):
            if not re.search(pat, r["product_title"]) or not r["available"] or r["price"] <= 0:
                continue
            qty, unit = pack_of(r["product_title"], r["variant_title"])
            if qty is None or (sizes is not None and (round(qty), unit) not in sizes):
                continue
            rows.append(dict(item_id=item, store=store, product_id=r["product_id"], variant_id=r["variant_id"],
                             product_title=r["product_title"], variant_title=r["variant_title"], qty_base=qty, base_unit=unit,
                             price_at_selection=r["price"], regular_at_selection=r["regular_price"], selected_on=today.isoformat(), why=why))
    return pd.DataFrame(rows).drop_duplicates(["store", "variant_id"])


def main():
    s = load_settings()
    client = PoliteClient(s["collectors"]["user_agent"], min_delay=4.0, retries=1)
    cats = {st: fetch_catalogue(client, st) for st in sorted({r[1] for r in RULES})}
    pool = select(cats, dt.date.today())
    out = ROOT / POOL
    out.parent.mkdir(parents=True, exist_ok=True)
    pool.to_csv(out, index=False)
    print(pool.groupby(["item_id", "store"]).size().to_string())
    print(f"{len(pool)} SKUs for {pool.item_id.nunique()} items -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
