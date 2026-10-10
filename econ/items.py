"""Bottom-up item panel: rpi item indices matched to the official CPI2024 Gujarat-urban item indices.

Read-only. Returns month-on-month log changes (in %) for every (item, month) where both the rpi item
and its mapped official item exist, with the match quality and the basket weight.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

from econ.data import DB, ROOT

OFFICIAL_CSV = ROOT / "data" / "official" / "mospi_cpi2024_gujarat_urban.csv"
MAP_CSV = ROOT / "data" / "basket_official_map.csv"
WEIGHTS_CSV = ROOT / "data" / "weights_cpi2024_gujarat_urban.csv"
VARIANT = "geks_jevons"   # the variant behind the published index


@dataclass
class ItemPanel:
    long: pd.DataFrame        # columns: period, item_id, quality, x (rpi MoM %), y (official MoM %), w (weight)
    matched: pd.DataFrame     # one row per matched item: item_id, official_code, quality, weight
    unmatched_weight: float   # share of basket weight with no official counterpart


def _rpi_item_mom() -> pd.DataFrame:
    """rpi item month-on-month log change (%), all months, columns = item_id."""
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rpi = pd.read_sql(
            "select period, key as item_id, value from index_results where variant=? and level='item' "
            "and run_id=(select run_id from index_runs order by built_at desc limit 1)",
            con, params=(VARIANT,))
    finally:
        con.close()
    lvl = rpi.pivot(index="period", columns="item_id", values="value").sort_index()
    return np.log(lvl).diff() * 100.0


def load_items() -> ItemPanel:
    m = pd.read_csv(MAP_CSV, dtype=str)
    w = pd.read_csv(WEIGHTS_CSV, dtype={"item_id": str}).set_index("item_id")["weight"].astype(float)
    m = m[m.match_quality.isin(["exact", "proxy", "blend"])].copy()
    m["weight"] = m.item_id.map(w)

    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        rpi = pd.read_sql(
            "select period, key as item_id, value from index_results where variant=? and level='item' "
            "and run_id=(select run_id from index_runs order by built_at desc limit 1)",
            con, params=(VARIANT,))
    finally:
        con.close()
    rpi_lvl = rpi.pivot(index="period", columns="item_id", values="value").sort_index()

    off = pd.read_csv(OFFICIAL_CSV, dtype={"code": str, "period": str}, usecols=["period", "level", "code", "index_value"])
    off = off[off.level == "item"]
    off_lvl = off.pivot_table(index="period", columns="code", values="index_value", aggfunc="first").sort_index()

    keep = m[m.official_item_code.isin(off_lvl.columns) & m.item_id.isin(rpi_lvl.columns)]
    x = np.log(rpi_lvl[keep.item_id]).diff() * 100.0
    y = np.log(off_lvl[keep.official_item_code]).diff() * 100.0
    y.columns = keep.item_id.values

    xl = x.rename_axis("period").reset_index().melt(id_vars="period", var_name="item_id", value_name="x")
    yl = y.rename_axis("period").reset_index().melt(id_vars="period", var_name="item_id", value_name="y")
    long = xl.merge(yl, on=["period", "item_id"]).dropna()
    long["quality"] = long.item_id.map(keep.set_index("item_id").match_quality)
    long["w"] = long.item_id.map(keep.set_index("item_id").weight)
    long = long.reset_index(drop=True)

    matched_w = keep.weight.sum()
    total_w = w.sum()
    return ItemPanel(long=long, matched=keep[["item_id", "official_item_code", "match_quality", "weight"]].reset_index(drop=True),
                     unmatched_weight=float(1.0 - matched_w / total_w))
