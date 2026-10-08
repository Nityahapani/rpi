"""Vishal Mega Mart men's clothing and footwear price diary (C001 shirts, C002 jeans/bottomwear, C003 sandals/slippers): live accrual + gate.

Source: public product pages of vishalmegamart.com carry schema.org Product JSON-LD (SKU, price, availability; availability is store-specific, so it reads OutOfStock without a pincode and is ignored); robots.txt allows the pages (it disallows /api and
account paths).  Prices are national e-store prices of a value retailer that has stores in Gujarat: a PROXY, not a Rajkot price.
A fixed pool (data/vishal/pool.csv, built by scripts/build_vishal_pool.py on its selection date) is read each refresh at 2 s spacing and appended to
data/vishal/live_prices.csv.  Archived captures of the same product URLs (data/vishal/prices.csv, Internet Archive) are merged into the monthly panel where they exist.
Status (2026-10-08): WIRED, by explicit user decision on 2026-10-06, as the primary source for C001/C002/C003 (data/source_plan.csv: class=independent,
proxy bucket, gate pending).  The archive-only history was far too sparse to gate on its own (3-5 overlapping months; inventory section AC), so the plan
note flags it for review/demotion if the unchanged gate fails once ~6 months of live history accumulate (~Apr 2027).  It can be demoted by an explicit
decision once the gate (>= 6 overlapping months, corr >= 0.5, drift <= 0.10) passes - flat or promotion-driven series are exactly what the gate is there to catch."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

GROUPS = {"C001": "03.1.2.1.1.01", "C002": "03.1.2.1.1.02", "C003": "03.2.1.1.1.01"}
COLS = ["date", "item_id", "url", "price", "in_stock"]


def parse_product(html: str) -> tuple[float, bool] | None:
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        for p in (j if isinstance(j, list) else [j]):
            if isinstance(p, dict) and p.get("@type") == "Product" and isinstance(p.get("offers"), dict):
                try:
                    v = float(p["offers"]["price"])
                except Exception:
                    continue
                if v > 0:
                    return v, "InStock" in str(p["offers"].get("availability", ""))
    return None


def parse_itemlist(html: str) -> list[str]:
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        if isinstance(j, dict) and j.get("@type") == "ItemList":
            return [x["url"] for x in j["itemListElement"] if isinstance(x, dict) and x.get("url")]
    return []


def accrue(path: Path, pool_csv: Path, client, today: dt.date | None = None) -> tuple[int, str]:
    today = today or dt.date.today()
    pool = pd.read_csv(pool_csv, dtype=str)
    rows, bad = [], 0
    for _, r in pool.iterrows():
        resp = client.get(r.url)
        got = parse_product(resp.text) if resp.status_code == 200 else None
        if got is None:
            bad += 1
            continue
        rows.append({"date": today.isoformat(), "item_id": r.item_id, "url": r.url, "price": got[0], "in_stock": int(got[1])})
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLS)
    new = pd.concat([x for x in (old[old.date != today.isoformat()], pd.DataFrame(rows, columns=COLS)) if len(x)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False)
    return len(rows), f"{len(rows)}/{len(pool)} pool products priced" + (f"; {bad} unreadable" if bad else "")


class VishalCollector:
    """Wires the live diary (data/vishal/live_prices.csv) into the index as a PENDING-GATE proxy for C001-C003.

    Only LIVE diary quotes are emitted (fixed pool, one SKU per product URL).  The sparse Internet-Archive history is NOT used: it has 3-5 usable
    months and different URLs.  Earlier months stay on the official stand-in (BACKFILL_SOURCES); the item index is the matched-model Jevons chain.
    The gate (>= 6 overlapping months) cannot be judged before about Apr 2027, so these items are reported as `pending`, not validated.
    """
    source_id = "vishal_diary"
    last_snapshot_id = None

    def __init__(self, root: Path):
        self.live = Path(root) / "data/vishal/live_prices.csv"

    def collect(self, on_date):
        from .base import Observation
        if not self.live.exists():
            return
        d = pd.read_csv(self.live)
        d = d[(d.price > 0) & d.item_id.isin(GROUPS)]
        for r in d.itertuples():
            y, m, dd = (int(x) for x in r.date.split("-"))
            yield Observation(dt.date(y, m, dd), self.source_id, "VISHAL:" + r.url.rstrip("/").rsplit("/", 1)[-1][:80],
                              r.url, r.item_id, "IN-ESTORE", float(r.price), qty_base=1.0, base_unit="pc")


def monthly_panel(archive_csv: Path, live_csv: Path, pool_csv: Path, item: str) -> pd.DataFrame:
    """months x URL: median archive price per month for pool URLs; a live quote for the same URL and month replaces the archive value."""
    pool = pd.read_csv(pool_csv, dtype=str)
    urls = set(pool[pool.item_id == item].url)
    parts = []
    if archive_csv.exists():
        a = pd.read_csv(archive_csv, dtype={"ts": str})
        a = a[a.url.isin(urls)].copy(); a["m"] = a.ts.str[:4] + "-" + a.ts.str[4:6]
        parts.append(a.groupby(["url", "m"]).price.median().rename("price").reset_index().assign(live=0))
    if live_csv.exists():
        lv = pd.read_csv(live_csv)
        lv = lv[(lv.item_id == item) & (lv.price > 0)].copy(); lv["m"] = lv.date.str[:7]
        parts.append(lv.groupby(["url", "m"]).price.median().rename("price").reset_index().assign(live=1))
    parts = [x for x in parts if len(x)]
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts).sort_values("live").groupby(["url", "m"]).tail(1)
    return d.pivot(index="m", columns="url", values="price").sort_index()


def gate(archive_csv: Path, live_csv: Path, pool_csv: Path, official_csv: Path) -> list[dict]:
    from ..proxy_check import chain_series, judge
    off = pd.read_csv(official_csv, dtype={"code": str})
    out = []
    for item, code in GROUPS.items():
        piv = monthly_panel(archive_csv, live_csv, pool_csv, item)
        o = off[(off.level == "item") & (off.code == code)].set_index("period").index_value
        if piv.empty:
            out.append(dict(item_id=item, verdict="pending", n_overlap=0, corr=None, drift=None, n_skus=0))
            continue
        piv = piv[piv.index <= o.index.max()]
        j = judge(chain_series(piv), o) if len(piv) else dict(verdict="pending", n_overlap=0, corr=None, drift=None)
        j.update(item_id=item, n_skus=int(piv.notna().any().sum()))
        out.append(j)
    return out
