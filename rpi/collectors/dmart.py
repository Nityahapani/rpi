"""DMart Ready (Ahmedabad store) SHELF prices of a fixed SKU pool: the first retail-shelf source for packaged goods.

What it is: digital.dmart.in is the JSON API behind dmart.in's category pages.  For store 10681 (the store DMart Ready uses for Ahmedabad
pincodes such as 380001 - checked via /v1/pincodes/search/380001) every SKU carries its MRP (priceMRP) and DMart's shelf price (priceSALE).
Rajkot pincodes (360001-360023) are NOT served by DMart Ready, so this is an AHMEDABAD price: a Gujarat big-city proxy, reported in the
PROXY bucket, never as a Rajkot price (same status as NECC Ahmedabad eggs).

Design (fixed before any history existed; see scripts/build_dmart_pool.py):
  * a fixed pool of SKUs per basket item (data/dmart/pool.csv, 2-5 mainstream SKUs of the spec pack size); the item index is the matched-model
    Jevons mean of the SKU unit prices, so pack size, brand mix and DMart's own discounting enter only as changes of the SAME SKU's price;
  * price = priceSALE (what a shopper pays), regular_price = priceMRP (the engine's `regular_price` variant is the promo-free check);
  * out-of-stock SKUs are skipped, not carried forward; a delisted SKU just stops reporting;
  * category listing pages (/v3/plp/{categoryId}), 4 s between requests (about 25 requests per run), no retries, and the run STOPS on the
    first non-200 reply - the endpoint sits behind a rate-limiting WAF (a burst of ~40 search requests in a minute got HTTP 403 on 2026-10-02),
    and this project never evades bot protection.  Honest User-Agent.
  * accrues forward only (no archive exists): the item's official stand-in is used for earlier months and the splice month is imputed
    (rpi/collectors/official_link.py BACKFILL_SOURCES).  Gated against the official item index like every proxy once 6 months overlap
    (rpi/proxy_check.py, multi-SKU series = matched-model Jevons).

Reachability: the sandbox reaches the API; GitHub-hosted runners were refused (HTTP 403, probe 2026-10-02), so the daily workflow skips this
source and it is refreshed whenever the pipeline is run from a machine that can reach it.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from .base import Collector, Observation
from ..units import parse_quantity

SOURCE_ID = "dmart_ahmedabad"
STORE_ID = 10681
API = "https://digital.dmart.in/api/v3/plp"
POOL = "data/dmart/pool.csv"
PAGE_SIZE = 40
MAX_PAGES = 4
HEADERS = {"Accept": "application/json", "Origin": "https://www.dmart.in", "Referer": "https://www.dmart.in/"}


class DmartBlocked(RuntimeError):
    pass


def parse_plp(payload: dict) -> list[dict]:
    """PLP JSON -> flat SKU rows {sku, name, brand, mrp, sale, in_stock, buyable, pack}.  Pure."""
    out = []
    for p in payload.get("products") or []:
        for s in p.get("sKUs") or []:
            try:
                mrp, sale = float(s.get("priceMRP") or 0), float(s.get("priceSALE") or 0)
            except ValueError:
                continue
            out.append(dict(sku=int(s["skuUniqueID"]), name=s.get("name", ""), brand=p.get("manufacturer", ""), mrp=mrp, sale=sale,
                            in_stock=str(s.get("invStatus", "0")) != "0", buyable=str(s.get("buyable", "")).lower() == "true",
                            pack=s.get("variantTextValue") or ""))
    return out


def pack_qty(name: str, pack: str):
    """(qty_base, base_unit) from the SKU title tail ('870 g', '4x100 g', '1 Unit'); falls back to the variant text.
    The title tail comes first because the variant text drops the multiplier ('100 g x 4 U')."""
    q = parse_quantity(name.rsplit(" : ", 1)[1]) if " : " in name else None
    if q is None and pack:
        q = parse_quantity(pack)
    return q if q else (None, None)


class DmartCollector(Collector):
    source_id = SOURCE_ID

    def __init__(self, client, store=None, pool_csv: str | Path = POOL, root: Path | None = None):
        self.client, self.store = client, store
        root = Path(root) if root else Path(__file__).resolve().parents[2]
        self.pool = pd.read_csv(root / pool_csv)
        self.client.session.headers.update(HEADERS)
        self.missing: list[int] = []

    def _page(self, cat: int, page: int) -> dict:
        r = self.client.get(f"{API}/{cat}", params=dict(page=page, size=PAGE_SIZE, channel="web", storeId=STORE_ID))
        if r.status_code != 200:
            raise DmartBlocked(f"HTTP {r.status_code} from digital.dmart.in for category {cat} (rate-limit/WAF or unreachable from this network); DMart skipped")
        if self.store is not None:
            self.store.save(SOURCE_ID, r.url, {"cat": cat, "page": page}, r.content, r.status_code)
        return json.loads(r.text)

    def collect(self, on_date: dt.date):
        self.missing = []
        for cat, g in self.pool.groupby("cat"):
            want = {int(s): row for s, row in zip(g.sku, g.itertuples())}
            seen: dict[int, dict] = {}
            for page in range(1, MAX_PAGES + 1):
                j = self._page(int(cat), page)
                rows = parse_plp(j)
                seen.update({r["sku"]: r for r in rows if r["sku"] in want})
                if len(seen) == len(want) or len(j.get("products") or []) < PAGE_SIZE or page * PAGE_SIZE >= int(j.get("totalRecords", 0)):
                    break
            for sku, row in want.items():
                r = seen.get(sku)
                if r is None:
                    self.missing.append(sku)
                    continue
                if not (r["in_stock"] and r["buyable"]) or r["sale"] <= 0:
                    continue
                reg = r["mrp"] if r["mrp"] >= r["sale"] else r["sale"]
                qty, unit = pack_qty(r["name"], r["pack"])
                yield Observation(on_date, SOURCE_ID, str(sku), r["name"], row.item_id, "AHM", r["sale"], regular_price=reg,
                                  qty_base=qty, base_unit=unit)
