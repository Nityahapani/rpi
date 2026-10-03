"""CEAT two-wheeler tyre e-store prices (T006 candidate): live accrual + gate against the official 'Tyres and tubes' item index.

Source: ceat.com product-listing pages carry schema.org Product JSON-LD (SKU, tax-inclusive e-store price).  robots.txt allows crawling.
History before today comes from Internet Archive captures (scripts/ceat_cdx.py, ceat_fetch.py -> data/ceat/sku_prices.csv, Sep 2025 on); every refresh adds
today's quote for the fixed 47-SKU pool (data/ceat/pool.csv, 12 pages, 2 s apart) to data/ceat/live_prices.csv.
It is a SCREEN, not an index input: the Wayback-only history failed the gate by a near miss (corr 0.46, drift 0.011; inventory section Y).  A month with live
quotes replaces the archive quote for that month, so the sparse-capture weakness shrinks as live months accrue.  It would be a national e-store price
(proxy bucket, not a Rajkot price) if it ever passes and is wired by an explicit decision."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

CODE = "07.2.1.1.1.01"
COLS = ["date", "sku", "price"]


def parse_products(html: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        for p in (j if isinstance(j, list) else [j]):
            if isinstance(p, dict) and p.get("@type") == "Product":
                try:
                    out[str(p["sku"])] = float(p["offers"]["price"])
                except Exception:
                    pass
    return out


def accrue(path: Path, pool_csv: Path, client, today: dt.date | None = None) -> tuple[int, str]:
    today = today or dt.date.today()
    pool = pd.read_csv(pool_csv, dtype=str)
    rows, bad = [], 0
    for page in pool.page.unique():
        r = client.get(page)
        if r.status_code != 200:
            bad += 1
            continue
        got = parse_products(r.text)
        for s in pool[pool.page == page].sku:
            if s in got:
                rows.append({"date": today.isoformat(), "sku": s, "price": got[s]})
    old = pd.read_csv(path, dtype={"sku": str}) if path.exists() else pd.DataFrame(columns=COLS)
    new = pd.concat([old[old.date != today.isoformat()], pd.DataFrame(rows, columns=COLS)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    new.to_csv(path, index=False)
    return len(rows), f"{len(rows)}/{len(pool)} pool SKUs quoted" + (f"; {bad} page(s) failed" if bad else "")


def monthly_panel(archive_csv: Path, live_csv: Path, pool_csv: Path | None = None) -> pd.DataFrame:
    """months x SKU: median archive quote per month, replaced by the median live quote where the month has live quotes."""
    a = pd.read_csv(archive_csv, dtype={"ts": str, "sku": str})
    a = a[a.price > 0].copy(); a["m"] = a.ts.str[:4] + "-" + a.ts.str[4:6]
    piv = a.groupby(["sku", "m"]).price.median().unstack(0)
    if live_csv.exists():
        lv = pd.read_csv(live_csv, dtype={"sku": str})
        lv = lv[lv.price > 0].copy(); lv["m"] = lv.date.str[:7]
        lp = lv.groupby(["sku", "m"]).price.median().unstack(0)
        piv = piv.reindex(piv.index.union(lp.index)).sort_index()
        for c in lp.columns:
            if c not in piv.columns:
                piv[c] = float("nan")
        piv.loc[lp.index, lp.columns] = lp.where(lp.notna(), piv.loc[lp.index, lp.columns])
    return piv.sort_index()


def gate(archive_csv: Path, live_csv: Path, official_csv: Path) -> dict:
    from ..proxy_check import chain_series, judge
    piv = monthly_panel(archive_csv, live_csv)
    off = pd.read_csv(official_csv, dtype={"code": str})
    o = off[(off.level == "item") & (off.code == CODE)].set_index("period").index_value
    piv = piv[piv.index <= o.index.max()]
    j = judge(chain_series(piv), o)
    j.update(item_id="T006", n_skus=int(piv.notna().any().sum()), months=int(len(piv)))
    return j
