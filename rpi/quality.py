"""Collector health monitoring: stale sources, failures, coverage."""
from __future__ import annotations
import datetime as dt
import pandas as pd


def health_report(conn, settings: dict, today: dt.date | None = None) -> pd.DataFrame:
    today = today or dt.date.today()
    stale = settings.get("health", {}).get("stale_days", {})
    obs = pd.read_sql_query(
        """SELECT p.source_id, MAX(o.obs_date) AS last_obs, COUNT(DISTINCT p.sku_id) AS n_skus,
                  COUNT(*) AS n_obs, MIN(i.tier) AS tier
           FROM observations o JOIN products p ON p.sku_id=o.sku_id JOIN items i ON i.item_id=p.item_id
           GROUP BY p.source_id""", conn)
    runs = pd.read_sql_query(
        """SELECT source_id, status AS last_status, message AS last_message, MAX(finished_at) AS last_run
           FROM collector_runs GROUP BY source_id""", conn)
    df = obs.merge(runs, on="source_id", how="outer")
    def flag(r):
        if pd.isna(r.get("last_obs")):
            return "NO DATA"
        age = (today - dt.date.fromisoformat(r["last_obs"])).days
        limit = stale.get(r.get("tier") or "A", 3)
        if r.get("last_status") == "error":
            return "FAILING"
        return "STALE" if age > limit else "ok"
    df["health"] = df.apply(flag, axis=1)
    return df[["source_id", "tier", "n_skus", "n_obs", "last_obs", "last_status", "health", "last_message"]]


def coverage_split(conn, plan_csv) -> dict:
    """How much of the basket weight is independent vs official-linked vs missing - by PLAN and by actual observations.

    ref_period    = latest month that has official-linked observations (the last official month)
    latest_period = latest month with any observation (months after ref_period are nowcast from independent items)
    """
    plan = pd.read_csv(plan_csv, dtype=str, keep_default_na=False)
    w = pd.read_sql_query("SELECT item_id, weight FROM weights", conn).merge(plan[["item_id", "class", "primary_source"]], on="item_id")
    tot = float(w["weight"].sum())
    by_plan = {k: round(float(v) / tot * 100, 1) for k, v in w.groupby("class")["weight"].sum().items()}
    obs = pd.read_sql_query(
        """SELECT p.item_id, p.source_id, substr(o.obs_date,1,7) AS period
           FROM observations o JOIN products p ON p.sku_id=o.sku_id GROUP BY 1,2,3""", conn)
    out = {"plan_weight_pct": by_plan}
    from .proxy_check import MODELLED_SOURCES, PROXY_ITEMS, PROXY_SOURCES, RETAIL_SOURCES
    ind = w[w["class"] == "independent"]
    _is_proxy = ind.primary_source.isin(PROXY_SOURCES) | ind.item_id.isin(PROXY_ITEMS)
    _is_retail = ind.primary_source.isin(RETAIL_SOURCES)
    _is_model = ind.primary_source.isin(MODELLED_SOURCES)
    out["independent_split_pct"] = {
        "direct (administered tariff / spot / PNG)": round(float(ind.loc[~_is_proxy & ~_is_retail & ~_is_model, "weight"].sum()) / tot * 100, 1),
        "retail quotes (DoCA Rajkot centre reports; gated vs official)": round(float(ind.loc[_is_retail, "weight"].sum()) / tot * 100, 1),
        "modelled (R001 rent: Labour Bureau housing-group model, trend-gated vs official; not an observed price)": round(float(ind.loc[_is_model, "weight"].sum()) / tot * 100, 1),
        "proxy (wholesale mandi / NECC / DoCA national / DMart Ahmedabad shelf / regulated ceiling; see proxy_validation)": round(float(ind.loc[_is_proxy, "weight"].sum()) / tot * 100, 1)}
    if obs.empty:
        return out | {"ref_period": None, "latest_period": None}
    ref = obs.loc[obs.source_id == "official_link", "period"].max()
    latest = obs["period"].max()
    wt = w.set_index("item_id")["weight"]

    def share(period, indep_only=False):
        o = obs[obs.period == period]
        if indep_only:
            o = o[o.source_id != "official_link"]
        return round(float(wt.reindex(o.item_id.unique()).dropna().sum()) / tot * 100, 1)

    out.update({"ref_period": ref if isinstance(ref, str) else None, "latest_period": latest,
                "observed_weight_pct_ref": share(ref) if isinstance(ref, str) else None,
                "independent_weight_pct_ref": share(ref, True) if isinstance(ref, str) else None,
                "independent_weight_pct_latest": share(latest, True)})
    return out
