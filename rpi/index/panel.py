"""Turn raw observations into a monthly quote panel (quote = SKU x pincode)."""
from __future__ import annotations
from ..superseded import sql_clause
import numpy as np
import pandas as pd

_FIELDS = {"unit_price", "regular_unit_price"}


def load_quotes(conn, price_field: str = "unit_price", min_days: int = 1, min_days_by_source: dict | None = None) -> pd.DataFrame:
    """Monthly geometric-mean price per quote. Returns item_id, quote_id, period, lp, n_days, source_id.
    min_days_by_source: daily-polled, volatile feeds (mandi, eggs, spot metals) need several days before a month counts, so a
    1-2 day partial month cannot masquerade as a monthly mean (it is imputed from peers instead)."""
    if price_field not in _FIELDS:
        raise ValueError(f"price_field must be one of {_FIELDS}")
    q = f"""SELECT o.obs_date, o.sku_id, o.pincode, o.{price_field} AS p, p.item_id, p.source_id
            FROM observations o JOIN products p ON p.sku_id = o.sku_id
            WHERE o.in_stock = 1 AND o.{price_field} > 0 AND {sql_clause('p')}"""
    df = pd.read_sql_query(q, conn, parse_dates=["obs_date"])
    if df.empty:
        return pd.DataFrame(columns=["item_id", "quote_id", "period", "lp", "n_days", "source_id"])
    df["quote_id"] = df["sku_id"] + "|" + df["pincode"]
    df["period"] = df["obs_date"].dt.to_period("M")
    df["lp"] = np.log(df["p"])
    g = df.groupby(["item_id", "quote_id", "period"], as_index=False).agg(
        lp=("lp", "mean"), n_days=("lp", "size"), source_id=("source_id", "first"))
    need = g["source_id"].map(lambda s_: (min_days_by_source or {}).get(s_, min_days))
    return g[g["n_days"] >= need].reset_index(drop=True)


def quotes_to_arrays(quotes: pd.DataFrame, periods: pd.PeriodIndex) -> dict[str, np.ndarray]:
    """item_id -> (T x Q) array of log prices (NaN where quote not observed)."""
    out = {}
    for item, g in quotes.groupby("item_id"):
        w = g.pivot(index="period", columns="quote_id", values="lp").reindex(periods)
        out[item] = w.to_numpy(dtype=float)
    return out
