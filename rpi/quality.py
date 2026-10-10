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
        "retail quotes (DoCA Rajkot centre reports + Rajkot web shops; gated vs official)": round(float(ind.loc[_is_retail, "weight"].sum()) / tot * 100, 1),
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


def freshness_report(conn, settings: dict, today: dt.date | None = None) -> tuple[pd.DataFrame, dict]:
    """Per-ITEM freshness of the EVIDENCE, weighted: which heavy items are carried by fill rules and for how long.

    Two ages per item, because they catch different failures:

    * age_obs  - days since the item's newest quote. Answers "is the feed alive".
    * age_change - days since the newest quote that was DIFFERENT from that SKU's previous quote ("no change yet"
      is not evidence a price is current). A register or a fixed-fee item can be observed daily and still be
      unchanged for months; the monthly relative is then carried by the last step, and nothing else flags it.
      Typical case: an administered tariff register such as R003 (LPG cylinder), quoted every day but unchanged
      for ~100 days at the time of writing (Oct 2026).

    Thresholds: settings [health] item_stale_days (default 90) on age_change; item_stale_obs_days (default 30) on
    age_obs. Returns (frame sorted by weight, summary); summary['stale_weight_pct'] is the basket-weight share with
    age_change over the threshold - the number a publication gate should look at.
    """
    today = today or dt.date.today()
    limit = int(settings.get("health", {}).get("item_stale_days", 90))
    limit_obs = int(settings.get("health", {}).get("item_stale_obs_days", 30))
    df = pd.read_sql_query(
        """SELECT i.item_id, i.division, i.tier, w.weight,
                  MAX(o.obs_date) AS last_obs, COUNT(*) AS n_obs
           FROM items i JOIN weights w ON w.item_id=i.item_id
           LEFT JOIN products p ON p.item_id=i.item_id
           LEFT JOIN observations o ON o.sku_id=p.sku_id
           GROUP BY i.item_id""", conn)
    obs = pd.read_sql_query(
        """SELECT p.item_id, o.sku_id, o.obs_date, o.unit_price FROM observations o
           JOIN products p ON p.sku_id=o.sku_id ORDER BY o.sku_id, o.obs_date""", conn)
    last_change = {}
    if len(obs):
        obs = obs.dropna(subset=["unit_price"])
        obs["prev"] = obs.groupby("sku_id")["unit_price"].shift()
        ch = obs[(obs.prev.isna()) | (obs.unit_price != obs.prev)]
        last_change = ch.groupby("item_id")["obs_date"].max().to_dict()
    df["last_change"] = df.item_id.map(last_change)
    df["age_obs"] = [None if not r.last_obs else (today - dt.date.fromisoformat(r.last_obs)).days for r in df.itertuples()]
    df["age_change"] = [None if not isinstance(r.last_change, str) else (today - dt.date.fromisoformat(r.last_change)).days
                        for r in df.itertuples()]
    df["stale"] = [bool(a is not None and a > limit) for a in df.age_change]
    df["stale_feed"] = [bool(a is not None and a > limit_obs) for a in df.age_obs]
    df = df.sort_values(["stale", "weight"], ascending=[False, False]).reset_index(drop=True)
    tot = float(df.weight.sum()) or 1.0
    summ = {"stale_change_days_threshold": limit, "stale_obs_days_threshold": limit_obs, "n_items": int(len(df)),
            "n_stale": int(df.stale.sum()), "n_stale_feed": int(df.stale_feed.sum()),
            "stale_weight_pct": round(100.0 * float(df.loc[df.stale, "weight"].sum()) / tot, 2),
            "stale_feed_weight_pct": round(100.0 * float(df.loc[df.stale_feed, "weight"].sum()) / tot, 2),
            "heaviest_stale": df.loc[df.stale, ["item_id", "weight", "age_change", "last_change"]].head(5).to_dict("records")}
    return df[["item_id", "division", "tier", "weight", "last_change", "age_change", "last_obs", "age_obs", "stale", "stale_feed"]], summ


def freshness_gate(conn, settings: dict, today: dt.date | None = None) -> tuple[bool, str]:
    """Publication gate on stale evidence, OFF unless configured.

    `[gates] max_stale_weight_pct` in settings.toml = the largest share of basket weight allowed to have no price
    change for longer than `[health] item_stale_days`. Absent -> no enforcement (v1 ships as a report only, so the
    daily bot cannot start failing on a warning it never saw).
    """
    lim = settings.get("gates", {}).get("max_stale_weight_pct")
    _, summ = freshness_report(conn, settings, today=today)
    if lim is None:
        return True, f"freshness gate off (report only): stale weight {summ['stale_weight_pct']}%"
    ok = summ["stale_weight_pct"] <= float(lim)
    return ok, (f"stale weight {summ['stale_weight_pct']}% vs limit {lim}% "
                f"(no price change for >{summ['stale_change_days_threshold']} days; heaviest: {summ['heaviest_stale'][:3]})")
