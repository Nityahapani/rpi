"""Proxy validation gate.

Wholesale mandi / NECC series are PROXIES for retail items. A proxy is only as good as its co-movement with the official
Gujarat-urban item index, so every proxy item is tested against it once enough months overlap:

    overlap months   months present in BOTH the proxy (monthly mean of daily prices) and the official item index
    corr             Pearson correlation of month-on-month log changes
    drift            |cumulative log change(proxy) - cumulative log change(official)| over the overlap

    n_overlap < MIN_OVERLAP            -> "pending"   (cannot be judged yet; still counted, but reported as unvalidated)
    corr >= MIN_CORR and drift <= MAX_DRIFT -> "pass"
    otherwise                          -> "fail"      (surfaced as a refresh error; item should be reviewed/demoted)

Thresholds are deliberately loose: the official state item indices are thin-sample and provisional.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# doca_national = all-India balanced panel of DoCA retail quotes (rpi/collectors/doca.py): observed retail prices, but not Rajkot -> proxy bucket.
from .superseded import sql_clause
PROXY_SOURCES = ("mandi_gondal", "mandi_rajkot_apmc", "mandi_rajkot_veg", "yard_rajkot_board", "mandi_rajkot_district", "necc_ahmedabad", "doca_national", "doca_gujarat", "dmart_ahmedabad")
# Multi-SKU pools: the monthly level is the matched-model Jevons chain of the SKUs, not the mean of price levels (a SKU going out of stock must not move it).
MULTI_SKU_SOURCES = ("dmart_ahmedabad",)
# Retail quotes reported by DoCA for the Rajkot centre (rpi/collectors/doca.py): a genuine retail price of a standard local variety,
# gated against the official item index like a proxy, but reported in its own bucket (it is not wholesale).
RETAIL_SOURCES = ("doca_rajkot",)
GATED_SOURCES = PROXY_SOURCES + RETAIL_SOURCES
# Items fed by a regulated CEILING (a cap, not an observed shelf price) are counted in the proxy share even though they use the
# tariff machinery; M001 = NPPA ceiling for paracetamol 500 mg; T004 = statutory maximum auto-rickshaw fare; D002 = Rajkot tea-hotel association rate card (not an observed paid price).
PROXY_ITEMS = ("M001", "T004", "D002")
MIN_OVERLAP, MIN_CORR, MAX_DRIFT = 6, 0.5, 0.10


def judge(proxy: pd.Series, official: pd.Series) -> dict:
    """Pure: two monthly level series (index = 'YYYY-MM') -> verdict dict."""
    both = pd.concat([proxy.rename("p"), official.rename("o")], axis=1).dropna().sort_index()
    n = len(both)
    out = {"n_overlap": int(n), "corr": None, "drift": None, "verdict": "pending"}
    if n < MIN_OVERLAP:
        return out
    lg = np.log(both.astype(float))
    d = lg.diff().dropna()
    corr = float(d["p"].corr(d["o"])) if d["p"].std() > 0 and d["o"].std() > 0 else float("nan")
    drift = float(abs((lg["p"].iloc[-1] - lg["p"].iloc[0]) - (lg["o"].iloc[-1] - lg["o"].iloc[0])))
    out.update(corr=round(corr, 2) if corr == corr else None, drift=round(drift, 3))
    out["verdict"] = "pass" if (corr == corr and corr >= MIN_CORR and drift <= MAX_DRIFT) else "fail"
    return out


def chain_series(piv: pd.DataFrame) -> pd.Series:
    """months x SKUs unit-price table -> matched-model Jevons level series (first month = 100)."""
    lg = np.log(piv.astype(float).where(piv > 0))
    step = lg.diff().mean(axis=1, skipna=True)
    lvl = 100.0 * np.exp(step.fillna(0.0).cumsum())
    lvl[step.isna() & (lvl.index != lvl.index[0])] = np.nan
    return lvl


def validate_proxies(conn, official_csv, mapping_csv, plan_csv) -> list[dict]:
    plan = pd.read_csv(plan_csv, dtype=str, keep_default_na=False)
    mp = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")
    off = pd.read_csv(official_csv, dtype={"code": str})
    off = off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    items = plan.loc[plan.primary_source.isin(GATED_SOURCES), "item_id"].tolist()
    res = []
    for it in items:
        code = mp.loc[it, "official_item_code"] if it in mp.index else ""
        q = pd.read_sql_query(
            """SELECT substr(o.obs_date,1,7) AS m, AVG(o.unit_price) AS v FROM observations o JOIN products p ON p.sku_id=o.sku_id
               WHERE p.item_id=? AND p.source_id IN ({}) AND {} GROUP BY 1""".format(",".join("?" * len(GATED_SOURCES)), sql_clause("p")),
            conn, params=[it, *GATED_SOURCES])
        proxy = q.set_index("m")["v"] if len(q) else pd.Series(dtype=float)
        if plan.set_index("item_id").loc[it, "primary_source"] in MULTI_SKU_SOURCES:
            sk = pd.read_sql_query(
                """SELECT o.sku_id AS sku, substr(o.obs_date,1,7) AS m, AVG(o.unit_price) AS v FROM observations o JOIN products p ON p.sku_id=o.sku_id
                   WHERE p.item_id=? AND p.source_id IN ({})  GROUP BY 1,2""".format(",".join("?" * len(MULTI_SKU_SOURCES))),
                conn, params=[it, *MULTI_SKU_SOURCES])
            proxy = chain_series(sk.pivot(index="m", columns="sku", values="v").sort_index()) if len(sk) else pd.Series(dtype=float)
        o = off[code].dropna() if code in off.columns else pd.Series(dtype=float)
        res.append({"item_id": it, **judge(proxy, o), "proxy_months": int(len(proxy)),
                    "official_months_after_proxy_start": int(sum(1 for m in o.index if len(proxy) and m >= proxy.index.min()))})
    return res
