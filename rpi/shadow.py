"""Shadow screen: candidate sources that ACCRUE but do not feed the index, compared with what does.

A candidate becomes an input only by a recorded switch of `primary_source` in data/source_plan.csv, after it has passed the same gate as
every proxy (rpi/proxy_check.judge against the official Gujarat-urban item index: >= 6 overlapping months, corr >= 0.5, drift <= 0.10).
This module only measures:

    per (candidate source, item)
      months / SKUs observed, last quote date          is the feed alive and deep enough
      gate vs official                                 the switch criterion (pending until 6 overlapping months)
      vs current input: overlap, corr of m/m changes,  does the local price move like the input it would replace
        cumulative gap (pp)
      judgeable_from                                   first month the gate can be judged if accrual continues

Candidate sources (each provides a quote frame with date, item_id, sku, unit_price):
    rajkot_shops   Rajkot retailers' own web shops (rpi/collectors/rajkot_shops.py)
    apple_store    apple.com/in fixed-SKU shelf price, iPhone 16 128 GB (rpi/collectors/apple_store.py)
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .proxy_check import MIN_OVERLAP, MULTI_SKU_SOURCES, chain_series, judge

OFFICIAL_CSV = "data/official/mospi_cpi2024_gujarat_urban.csv"
MAP_CSV = "data/basket_official_map.csv"
PLAN_CSV = "data/source_plan.csv"
OUT_JSON = "data/official/shadow_sources.json"


def monthly_panel(quotes: pd.DataFrame, item: str) -> pd.DataFrame:
    """months x SKU table of median unit prices for one item (the input of proxy_check.chain_series)."""
    q = quotes[(quotes.item_id == item) & (quotes.unit_price > 0)]
    if q.empty:
        return pd.DataFrame()
    q = q.assign(m=q.date.astype(str).str[:7])
    return q.groupby(["m", "sku"]).unit_price.median().unstack("sku").sort_index()


def official_series(root: Path, item: str, _cache: dict = {}) -> pd.Series:   # noqa: B006 - deliberate per-process cache
    key = str(root)
    if key not in _cache:
        off = pd.read_csv(Path(root) / OFFICIAL_CSV, dtype={"code": str})
        off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
        mp = pd.read_csv(Path(root) / MAP_CSV, dtype=str, keep_default_na=False).set_index("item_id")["official_item_code"]
        _cache[key] = (off, mp)
    off, mp = _cache[key]
    code = mp.get(item, "")
    return off[code].dropna() if code in off.columns else pd.Series(dtype=float)


def current_series(conn, item: str, source: str) -> pd.Series:
    """Monthly level of the item's CURRENT input (matched-model chain for multi-SKU pools, mean unit price otherwise)."""
    if conn is None or not source:
        return pd.Series(dtype=float)
    q = pd.read_sql_query(
        """SELECT o.sku_id AS sku, substr(o.obs_date,1,7) AS m, AVG(o.unit_price) AS v
           FROM observations o JOIN products p ON p.sku_id=o.sku_id
           WHERE p.item_id=? AND p.source_id=? AND o.unit_price > 0 GROUP BY 1, 2""", conn, params=(item, source))
    if q.empty:
        return pd.Series(dtype=float)
    if source in MULTI_SKU_SOURCES or q.sku.nunique() > 1:
        return chain_series(q.pivot(index="m", columns="sku", values="v").sort_index())
    return q.groupby("m").v.mean().sort_index()


def compare(cand: pd.Series, other: pd.Series) -> dict:
    """Overlap, correlation of month-on-month log changes and cumulative gap (percentage points) between two level series."""
    both = pd.concat([cand.rename("c"), other.rename("o")], axis=1).dropna().sort_index()
    out = {"n_overlap": int(len(both)), "corr_mom": None, "cum_gap_pp": None}
    if len(both) >= 2:
        lg = np.log(both.astype(float))
        out["cum_gap_pp"] = round(100 * float((lg.c.iloc[-1] - lg.c.iloc[0]) - (lg.o.iloc[-1] - lg.o.iloc[0])), 2)
    if len(both) >= 4:
        d = np.log(both.astype(float)).diff().dropna()
        if d.c.std() > 0 and d.o.std() > 0:
            out["corr_mom"] = round(float(d.c.corr(d.o)), 2)
    return out


def assess(item: str, panel: pd.DataFrame, official: pd.Series, current: pd.Series, meta: dict) -> dict:
    chain = chain_series(panel) if len(panel) else pd.Series(dtype=float)
    gate = judge(chain, official)
    months = list(panel.index) if len(panel) else []
    first = months[0] if months else None
    judgeable = (pd.Period(first, "M") + MIN_OVERLAP).strftime("%Y-%m") if first else None   # 6th month + about one month of MoSPI lag
    status = ("no quotes yet" if not months else
              {"pending": f"accruing ({gate['n_overlap']}/{MIN_OVERLAP} months overlap the official index; judgeable from about {judgeable})",
               "pass": "passes the gate: can be PROPOSED for a switch (recorded decision)",
               "fail": "fails the gate against the official index: keep the current input"}[gate["verdict"]])
    return {"item_id": item, **meta, "months": len(months), "first_month": first, "last_month": months[-1] if months else None,
            "n_skus": int(panel.notna().any().sum()) if len(panel) else 0,
            "gate_vs_official": gate, "vs_current_input": compare(chain, current), "judgeable_from": judgeable, "status": status}


def candidate_frames(root: Path) -> dict[str, pd.DataFrame]:
    from .collectors import apple_store, rajkot_shops
    out = {"rajkot_shops": rajkot_shops.live_frame(root)}
    ap = apple_store.live_frame(root)
    if len(ap):
        out["apple_store"] = ap
    return out


def screen(root: Path, conn=None, write: bool = True) -> dict:
    root = Path(root)
    plan = pd.read_csv(root / PLAN_CSV, dtype=str, keep_default_na=False).set_index("item_id")
    items = pd.read_csv(root / "registry/items.csv", dtype=str, keep_default_na=False).set_index("item_id")
    w = pd.to_numeric(items.weight, errors="coerce")
    wpct = (w / w.sum() * 100).round(2)
    res = {"generated": dt.date.today().isoformat(), "rule": "shadow only: a candidate feeds the index after a recorded switch of "
           "primary_source in data/source_plan.csv, once it passes proxy_check.judge against the official item index", "candidates": {}}
    for src, quotes in candidate_frames(root).items():
        rows = []
        for item in sorted(set(quotes.item_id)):
            cur = plan.primary_source.get(item, "")
            meta = {"name": items.name.get(item, ""), "weight_pct": float(wpct.get(item, 0.0)), "current_source": cur,
                    "already_switched": cur == src}
            rows.append(assess(item, monthly_panel(quotes, item), official_series(root, item), current_series(conn, item, cur), meta))
        last = str(quotes.date.max()) if len(quotes) else None
        res["candidates"][src] = {"last_quote": last, "n_quotes": int(len(quotes)), "items": rows,
                                  "weight_pct_covered": round(sum(r["weight_pct"] for r in rows), 2)}
    if write:
        (root / OUT_JSON).write_text(json.dumps(res, indent=1, default=str))
    return res


def summary_lines(res: dict) -> list[str]:
    lines = []
    for src, c in res["candidates"].items():
        lines.append(f"{src}: {len(c['items'])} items, {c['weight_pct_covered']}% of basket weight, {c['n_quotes']} quotes, last {c['last_quote']}")
        for r in sorted(c["items"], key=lambda r: -r["weight_pct"]):
            v = r["vs_current_input"]
            lines.append(f"  {r['item_id']} {r['name'][:26]:26s} {r['weight_pct']:5.2f}%  now {r['current_source']:18s} "
                         f"{r['months']}m {r['n_skus']:2d} SKUs  vs official: {r['gate_vs_official']['verdict']:7s} "
                         f"vs current: n={v['n_overlap']} corr={v['corr_mom']} "
                         f"gap={'n/a' if v['cum_gap_pp'] is None else str(v['cum_gap_pp']) + 'pp'}  -> {r['status']}")
    return lines
