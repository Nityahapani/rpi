"""Rajkot field price diary: shelf prices recorded IN Rajkot stores by a person - a SHADOW source, MoSPI-style collection.

Why.  After the Rajkot web shops (rajkot_shops.py) about 14% of the basket weight is still priced outside Rajkot - branded FMCG (tea,
soap, detergent, toothpaste, shampoo, biscuits, antiseptic), dairy (ghee, curd, butter), banana and eggs - and no Rajkot seller of
those publishes an open product feed (the quick-commerce apps that do sell them in Rajkot block automated clients; see rajkot_shops.py).
Official CPIs solve exactly this with price collectors who visit fixed outlets every month.  This module is that, at project scale:
about 15 items x 2-3 stores x 1-2 products, one visit a month, roughly an hour.

Protocol (the matched-model rule, so the series measures price CHANGE, not shopping choices):
  * the same store, the same product, the same pack every month (a product that disappears is replaced by recording the new one as a
    NEW row from that month; the chain picks it up at its second month);
  * record the price the shopper pays (shelf / bill), the printed MRP if there is one, and note promotions;
  * loose produce (banana, eggs): the vendor's price for a fixed unit (dozen, tray of 30), same vendor every month.

File: data/field_diary/prices.csv, one row per quote:
    date        YYYY-MM-DD of the visit
    store       short outlet code, fixed over time (e.g. smart_nana_mava, vishal_kalawad_rd, golden_university_rd, fruit_vendor_raiya)
    item_id     basket item id (see data/field_diary/sheet.csv for the target list and specs)
    brand, product, pack     as printed ('Tata Tea Premium', '', '250 g'; 'Robusta banana', '', '1 dozen')
    price       rupees paid;  mrp  printed MRP (optional);  recorded_by  initials;  note  promotions etc. (optional)
SKU identity = store | brand | product | pack.  validate() lists every row it rejects and why; nothing is silently dropped.

SHADOW: the diary is screened like the web shops (rpi/shadow.py) and feeds the index only for items switched to primary_source =
field_diary in data/source_plan.csv.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

from .base import Observation
from ..units import parse_quantity, unit_price

SOURCE_ID = "field_diary"
PRICES = "data/field_diary/prices.csv"
SHEET = "data/field_diary/sheet.csv"
COLS = ["date", "store", "item_id", "brand", "product", "pack", "price", "mrp", "recorded_by", "note"]
OUTLIER_FACTOR = 4.0
# items whose current input is priced outside Rajkot (or a national e-store) - the diary's target list unless a web shop covers them
OUT_OF_CITY_SOURCES = ("dmart_ahmedabad", "doca_national", "vishal_diary")


def _slug(*parts) -> str:
    return re.sub(r"[^a-z0-9]+", "-", "|".join(str(p or "").strip().lower() for p in parts)).strip("-")[:90]


def validate(df: pd.DataFrame, known_items: set[str], today: dt.date | None = None) -> tuple[pd.DataFrame, list[str]]:
    """-> (accepted rows with qty/unit/unit_price/sku added, list of problems).  Pure."""
    today = today or dt.date.today()
    problems: list[str] = []
    miss = [c for c in ("date", "store", "item_id", "pack", "price") if c not in df.columns]
    if miss:
        return pd.DataFrame(), [f"missing column(s): {miss}"]
    keep = []
    for i, r in df.iterrows():
        tag = f"row {i + 2}"                                   # +2: header line and 1-based numbering, as in a spreadsheet
        try:
            d = dt.date.fromisoformat(str(r.date).strip())
        except ValueError:
            problems.append(f"{tag}: date {r.date!r} is not YYYY-MM-DD"); continue
        if d > today:
            problems.append(f"{tag}: date {d} is in the future"); continue
        if str(r.item_id).strip() not in known_items:
            problems.append(f"{tag}: unknown item_id {r.item_id!r}"); continue
        if not str(r.store).strip():
            problems.append(f"{tag}: store is empty"); continue
        try:
            price = float(r.price)
        except (TypeError, ValueError):
            problems.append(f"{tag}: price {r.price!r} is not a number"); continue
        if price <= 0:
            problems.append(f"{tag}: price must be > 0"); continue
        q = parse_quantity(str(r.pack))
        if q is None:
            problems.append(f"{tag}: pack {r.pack!r} has no readable size (write e.g. '500 g', '1 L', '1 dozen', '30 pcs')"); continue
        mrp = pd.to_numeric(r.get("mrp"), errors="coerce")
        keep.append(dict(date=d.isoformat(), store=str(r.store).strip(), item_id=str(r.item_id).strip(), price=price,
                         regular_price=float(mrp) if mrp == mrp and mrp >= price else price, qty_base=q[0], base_unit=q[1],
                         unit_price=unit_price(price, q[0], q[1]),
                         sku=_slug(r.store, r.get("brand", ""), r.get("product", ""), r.pack),
                         title=" ".join(str(x) for x in (r.get("brand", ""), r.get("product", ""), r.pack) if str(x) not in ("", "nan"))))
    out = pd.DataFrame(keep)
    if len(out):
        med = out.groupby("item_id").unit_price.transform("median")
        bad = (out.unit_price > OUTLIER_FACTOR * med) | (out.unit_price < med / OUTLIER_FACTOR)
        for r in out[bad].itertuples():
            problems.append(f"{r.date} {r.store} {r.item_id}: unit price {r.unit_price:.2f} is more than {OUTLIER_FACTOR:g}x away from the "
                            f"item median - check the pack or the price (row excluded)")
        out = out[~bad]
        dup = out.duplicated(["date", "sku"], keep="last")
        if dup.any():
            problems.append(f"{int(dup.sum())} duplicate (date, store, product) row(s): the last one is kept")
            out = out[~dup]
    return out.reset_index(drop=True), problems


def load(root: Path) -> pd.DataFrame:
    p = Path(root) / PRICES
    return pd.read_csv(p, dtype=str, keep_default_na=False) if p.exists() else pd.DataFrame(columns=COLS)


def quote_frame(root: Path) -> pd.DataFrame:
    root = Path(root)
    raw = load(root)
    if raw.empty:
        return pd.DataFrame()
    items = set(pd.read_csv(root / "registry/items.csv", dtype=str, usecols=["item_id"]).item_id)
    ok, _ = validate(raw, items)
    return ok


def target_items(root: Path) -> pd.DataFrame:
    """Items priced outside Rajkot that no Rajkot web-shop SKU covers: the diary's collection list."""
    root = Path(root)
    reg = pd.read_csv(root / "registry/items.csv", dtype=str, keep_default_na=False)
    shops = set(pd.read_csv(root / "data/rajkot_shops/pool.csv", dtype=str).item_id) if (root / "data/rajkot_shops/pool.csv").exists() else set()
    t = reg[reg.primary_source.isin(OUT_OF_CITY_SOURCES) & ~reg.item_id.isin(shops)].copy()
    w = pd.to_numeric(reg.weight, errors="coerce")
    t["weight_pct"] = (pd.to_numeric(t.weight, errors="coerce") / w.sum() * 100).round(2)
    return t.sort_values("weight_pct", ascending=False)


def write_sheet(root: Path) -> Path:
    """data/field_diary/sheet.csv: the collection list with spec and the products already tracked elsewhere, so the diary prices the
    same brands (from the DMart pool where one exists)."""
    root = Path(root)
    t = target_items(root)
    dm = pd.read_csv(root / "data/dmart/pool.csv", dtype=str) if (root / "data/dmart/pool.csv").exists() else pd.DataFrame(columns=["item_id", "name"])
    hint = dm.groupby("item_id").name.apply(lambda s: " / ".join(s.head(3).str.replace(r"\s*:\s*", " ", regex=True)))
    sheet = pd.DataFrame({"item_id": t.item_id, "name": t.name, "weight_pct": t.weight_pct, "spec": t.spec, "unit": t.base_unit,
                          "now_priced_from": t.primary_source, "suggested_products": t.item_id.map(hint).fillna(""),
                          "how": "same 2-3 Rajkot stores and same products every month; record price paid, pack and MRP"})
    out = root / SHEET
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.to_csv(out, index=False)
    p = root / PRICES
    if not p.exists():
        pd.DataFrame(columns=COLS).to_csv(p, index=False)
    return out


class FieldDiaryCollector:
    """Emits diary quotes of SWITCHED items only (primary_source = field_diary); in shadow mode it emits nothing."""
    source_id = SOURCE_ID
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.root = Path(root)

    def collect(self, on_date):
        from .rajkot_shops import switched_items
        items = set(switched_items(self.root, SOURCE_ID))
        if not items:
            return
        d = quote_frame(self.root)
        if d.empty:
            return
        for r in d[d.item_id.isin(items)].itertuples():
            y, m, dd = (int(x) for x in r.date.split("-"))
            yield Observation(dt.date(y, m, dd), SOURCE_ID, "FD:" + r.sku, r.title, r.item_id, "RAJKOT", float(r.price),
                              regular_price=float(r.regular_price), qty_base=float(r.qty_base), base_unit=str(r.base_unit))
