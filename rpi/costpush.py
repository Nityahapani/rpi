"""D003 street-snack plate and D001 veg thali: pre-registered cost-push model (a MODELLED proxy, not an observed price).

What it is.  A restaurant or street-stall menu price is a mark-up on three cost blocks: (i) ingredients, (ii) cooking fuel, (iii) everything else (labour, rent,
margin).  Blocks (i) and (ii) are observed here from sources that are independent of MoSPI (DoCA retail quotes, the Gujarat tariff register); block (iii) is
anchored to the Labour Bureau CPI-IW for Rajkot (an official index, but a different agency, a different basket and a different method from the MoSPI CPI
this model is later gated against).  The target price follows the log-linear cost aggregate and the menu price adjusts to it slowly (Calvo/partial
adjustment: stalls re-price in steps), which is how real menu prices behave.

Pre-registration (the discipline that makes the gate meaningful).  The cost shares, the input series and the adjustment speed below were fixed from
industry cost structure BEFORE the model was compared with the official D001/D003 indices; there is NOTHING fitted to the official series.  Because the
parameters are not estimated on it, the whole overlap with the official index is an out-of-sample test.  The unchanged proxy gate (>= 6 overlapping months,
corr of monthly log changes >= 0.5, |drift| <= 0.10) decides whether the series is allowed to count.  Alternative specifications are reported only as
robustness diagnostics (`sensitivity`); they never replace the pre-registered one.

  target_t  = sum_k s_k * ln(input_k,t / input_k,0)                (shares sum to 1)
  ln P_t    = ln P_{t-1} + LAMBDA * (target_t - ln P_{t-1})         (partial adjustment, P_0 = 1)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LAMBDA = 0.35          # share of the gap to the cost-implied price closed per month (menu prices re-set roughly every 3 months)
# (item_id -> {input name: (share, source item id, source id or None for the Rajkot CPI-IW anchor)}); shares sum to 1
SPEC = {
    "D003": {   # street snack plate: fried / griddle snacks (vada pav, samosa, kachori, pav bhaji)
        "frying oil (sunflower)":   (0.10, "F008", "doca_national"),
        "frying oil (groundnut)":   (0.10, "F006", "doca_rajkot"),
        "besan / pulses (chana)":   (0.12, "F005", "doca_national"),
        "potato":                   (0.14, "F021", "doca_gujarat"),
        "sugar":                    (0.04, "F013", "doca_rajkot"),
        "milk / butter":            (0.05, "F009", "tariff"),
        "cooking gas (LPG)":        (0.08, "R003", "tariff"),
        "labour, rent, margin":     (0.37, None, "cpi_iw_rajkot"),
    },
    "D001": {   # veg thali: rice, dal, roti, sabzi, curd
        "rice":                     (0.10, "F002", "doca_national"),
        "tur dal":                  (0.08, "F003", "doca_national"),
        "chana dal":                (0.02, "F005", "doca_national"),
        "cooking oil (groundnut)":  (0.08, "F006", "doca_rajkot"),
        "potato (vegetable proxy)": (0.10, "F021", "doca_gujarat"),
        "milk / butter":            (0.08, "F009", "tariff"),
        "sugar":                    (0.03, "F013", "doca_rajkot"),
        "cooking gas (LPG)":        (0.07, "R003", "tariff"),
        "labour, rent, margin":     (0.44, None, "cpi_iw_rajkot"),
    },
}
OFFICIAL = {"D003": "11.1.1.2.1.01", "D001": "11.1.1.1.1.01"}
assert all(abs(sum(v[0] for v in s.values()) - 1) < 1e-9 for s in SPEC.values())


def input_level(conn, item_id: str, source_id: str) -> pd.Series:
    """Monthly level (first month = 1) of an independent input: matched-model Jevons over the SKUs of (item, source)."""
    from .proxy_check import chain_series
    from .superseded import sql_clause
    q = pd.read_sql_query(
        "SELECT o.sku_id AS sku, substr(o.obs_date,1,7) AS m, AVG(o.unit_price) AS v FROM observations o JOIN products p ON p.sku_id=o.sku_id "
        "WHERE p.item_id=? AND p.source_id=? AND " + sql_clause("p") + " GROUP BY 1,2", conn, params=[item_id, source_id])
    if q.empty:
        return pd.Series(dtype=float)
    lv = chain_series(q.pivot(index="m", columns="sku", values="v").sort_index())
    return lv / lv.dropna().iloc[0]


def cpi_iw_rajkot(root) -> pd.Series:
    """Labour Bureau CPI-IW Rajkot (2016=100) as a monthly level; months before the first published one are held at it (disclosed)."""
    d = pd.read_csv(f"{root}/data/official/cpi_iw_gujarat_centres.csv")
    s = d[d.centre == "Rajkot"].drop_duplicates("period").set_index("period").value.sort_index()
    full = pd.period_range(s.index[0], s.index[-1], freq="M").strftime("%Y-%m")
    s = s.reindex(full).interpolate()           # one missing month in the PDF series is interpolated
    return s / s.iloc[0]


def model(conn, root, item_id: str, months: list[str], spec: dict | None = None, lam: float = LAMBDA) -> pd.Series:
    spec = spec or SPEC[item_id]
    months = sorted(months)
    cols = {}
    for name, (sh, it, src) in spec.items():
        lv = cpi_iw_rajkot(root) if src == "cpi_iw_rajkot" else input_level(conn, it, src)
        lv = lv.reindex(months)
        first = lv.first_valid_index()
        if first is None:
            raise ValueError(f"no data for input {name}")
        lv = lv.bfill() if src == "cpi_iw_rajkot" else lv        # CPI-IW starts 2025-05: earlier months held flat (disclosed)
        cols[name] = np.log(lv / lv.dropna().iloc[0]) * sh
    tgt = pd.DataFrame(cols).sum(axis=1, min_count=len(cols))
    lp, prev, out = [], 0.0, {}
    for m in months:
        t = tgt.get(m)
        if t is None or t != t:
            continue
        prev = prev + lam * (t - prev)
        out[m] = 100.0 * float(np.exp(prev))
    return pd.Series(out)


def screen(conn, root, official_csv) -> list[dict]:
    """Run the pre-registered model for D003 and D001 through the unchanged gate; add robustness rows (never adopted) for context."""
    from .proxy_check import judge
    off = pd.read_csv(official_csv, dtype={"code": str})
    off = off[off.level == "item"]
    rows = []
    for it in SPEC:
        o = off[off.code == OFFICIAL[it]].set_index("period").index_value
        o = o.sort_index()
        months = list(o.index)
        for tag, lam in (("pre-registered", LAMBDA), ("robustness lam=0.15", 0.15), ("robustness lam=0.60", 0.60), ("robustness lam=1.00", 1.0)):
            p = model(conn, root, it, months, lam=lam)
            j = judge(p, o)
            lo, lp = np.log(o), np.log(p.reindex(months))
            rows.append(dict(item_id=it, spec=tag, lam=lam, n_overlap=j["n_overlap"], corr_mom=j["corr"], drift=j["drift"], verdict=j["verdict"],
                             corr_3m=round(float(lp.diff(3).corr(lo.diff(3))), 2), level_corr=round(float(lp.corr(lo)), 2),
                             counted="YES" if (tag == "pre-registered" and j["verdict"] == "pass") else "no"))
    return rows
