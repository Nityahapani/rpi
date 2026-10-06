"""OFFICIAL-LINKED stand-in series: for basket items with no independent price source yet, feed the official MoSPI
Gujarat-urban ITEM index (via the mapping in data/basket_official_map.csv) as the item's price relative.

This is NOT independent data. It is a flagged placeholder so the basket is complete; it is replaced item-by-item as
independent collectors come online (see data/source_plan.csv). It lags ~12 days after month end; months beyond the last
official month are NOWCAST from the independently observed items (engine imputes unobserved items from division peers).
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from .base import Collector, Observation
from ..superseded import sql_clause

SOURCE_ID = "official_link"


# Sources whose own history is short (they only started collecting recently). For those items the official item index
# BACK-FILLS the months before the independent feed begins, as a separate SKU; the independent SKU takes over afterwards
# (the one splice month is imputed from division peers by the engine and disclosed as lower coverage).
BACKFILL_SOURCES = ("gr_metals", "mandi_gondal", "necc_ahmedabad", "mandi_rajkot_apmc", "mandi_rajkot_veg", "yard_rajkot_board", "doca_rajkot", "doca_national", "doca_gujarat", "dmart_ahmedabad", "vishal_diary", "frc_rajkot", "district_cinema", "fresha_salon", "rent_signal")


def linked_items(plan: pd.DataFrame) -> list[str]:
    return plan.loc[plan["primary_source"].isin(("official_link",) + BACKFILL_SOURCES), "item_id"].tolist()


class OfficialLinkCollector(Collector):
    source_id = SOURCE_ID

    def __init__(self, official_csv, mapping_csv, plan_csv, cutoff: dict[str, str] | None = None):
        # cutoff: item -> first 'YYYY-MM' with an INDEPENDENT observation. Official stand-in months from that month on are
        # not emitted, so an item never carries an official quote and an independent quote for the same month.
        self.cutoff = cutoff or {}
        self.off = pd.read_csv(official_csv, dtype={"code": str})
        self.map = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")
        self.plan = pd.read_csv(plan_csv, dtype=str, keep_default_na=False)

    def collect(self, on_date: dt.date):
        items = self.off[self.off.level == "item"]
        mat = items.pivot_table(index="period", columns="code", values="index_value", aggfunc="first").sort_index()
        for it in linked_items(self.plan):
            code = self.map.loc[it, "official_item_code"]
            if not code or code not in mat.columns:
                continue
            for period, v in mat[code].dropna().items():
                if it in self.cutoff and period >= self.cutoff[it]:
                    continue
                y, m = int(period[:4]), int(period[5:7])
                yield Observation(dt.date(y, m, 1), self.source_id, f"MOSPI:{code}", f"MoSPI Gujarat-urban item index {code}",
                                  it, "GJ-URBAN", float(v), qty_base=1.0, base_unit="pc")


def independent_cutoffs(conn) -> dict[str, str]:
    """item -> first month that any non-official source has an observation for it."""
    rows = conn.execute("""SELECT p.item_id, MIN(substr(o.obs_date,1,7)) FROM observations o JOIN products p ON p.sku_id=o.sku_id
                           WHERE p.source_id NOT IN ('official_link','tariff','synthetic') AND """ + sql_clause('p') + " GROUP BY p.item_id").fetchall()
    return {i: m for i, m in rows}


def trim_official_overlap(conn, plan: pd.DataFrame) -> str:
    """Delete official stand-in observations dated at/after the item's first independent month (idempotent)."""
    cut = {i: m for i, m in independent_cutoffs(conn).items() if i in set(linked_items(plan))}
    n = 0
    for it, m in cut.items():
        for (sku,) in conn.execute("SELECT sku_id FROM products WHERE source_id='official_link' AND item_id=?", (it,)).fetchall():
            n += conn.execute("DELETE FROM observations WHERE sku_id=? AND substr(obs_date,1,7)>=?", (sku, m)).rowcount
    conn.commit()
    return f"trimmed {n} official stand-in obs overlapping independent months" if n else "no official/independent overlap"
