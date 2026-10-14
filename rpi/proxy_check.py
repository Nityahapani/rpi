"""Proxy validation gate.

Wholesale mandi / NECC series are PROXIES for retail items. A proxy is only as good as its co-movement with the official
Gujarat-urban item index, so every proxy item is tested against it once enough months overlap:

    overlap months   months present in BOTH the proxy (monthly mean of daily prices) and the official item index
    corr             Pearson correlation of month-on-month log changes
    drift            |cumulative log change(proxy) - cumulative log change(official)| over the overlap

    n_overlap < MIN_OVERLAP            -> "pending"   (cannot be judged yet; still counted, but reported as unvalidated)
    any of the three legs below passes -> "pass"
    otherwise                          -> "fail"      (surfaced as a refresh error; item should be reviewed/demoted)

Thresholds are deliberately loose: the official state item indices are thin-sample and provisional.

THREE LEGS (added 2026-10-14).  Leg A alone is a thin-window test: it has real power only when the overlap is long, and it is
UNDEFINED in the sense that matters for sticky retail quotes.  A single reporter's quote for one variety is unchanged in most
months (the DoCA Rajkot centre series is flat in 30-90% of months, the official item index in ~1%), so the month-on-month correlation
of changes is attenuated towards zero by discreteness even for a perfectly good local series, while a short overlap makes it noise.
Leg A therefore answers "does this track the official index month by month", which is the right question for a liquid wholesale
series and the wrong one for a sticky retail quote.  Two long-horizon legs are added:

  Leg A  monthly tracking     n >= MIN_OVERLAP and corr(mom log changes) >= MIN_CORR and drift(whole overlap) <= MAX_DRIFT
  Leg B  annual tracking      leg C, plus corr(12-month log changes) >= MIN_CORR_12M
  Leg C  level fit            n >= LEVEL_MONTHS and R2(log proxy ~ log official) >= MIN_R2 and slope in [SLOPE_LO, SLOPE_HI]
                              and drift over the LAST DRIFT_MONTHS <= MAX_DRIFT

Why a level fit is admissible at all: the published index is CHAIN-RELATIVE - it is rebased to the base month, so a constant
percentage offset between a local series and the official index is removed by construction and carries no bias.  What cannot be
tolerated is the wrong amount of PASS-THROUGH (slope), a bad level fit (R2), or divergence inside the window the index actually
runs on (drift_recent).  Leg C tests exactly those three.  It is deliberately unavailable below LEVEL_MONTHS of overlap, so it can
never rescue a thinly-covered item, and its drift is measured on the recent window rather than over the whole history: 12 years of
relative-price path in 2011-2013 cannot bias an index that starts in 2025.

Every verdict reports which leg passed (`legs`) and all diagnostics, so a reader can audit the decision rather than trust it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# doca_national = all-India balanced panel of DoCA retail quotes (rpi/collectors/doca.py): observed retail prices, but not Rajkot -> proxy bucket.
from .superseded import sql_clause
PROXY_SOURCES = ("apple_store", "hathway_broadband", "green_mercado", "mandi_gondal", "mandi_rajkot_apmc", "mandi_rajkot_veg", "yard_rajkot_board", "mandi_rajkot_district", "necc_ahmedabad", "doca_national", "doca_gujarat", "dmart_ahmedabad", "vishal_diary", "frc_rajkot", "district_cinema", "fresha_salon")
# Multi-SKU pools: the monthly level is the matched-model Jevons chain of the SKUs, not the mean of price levels (a SKU going out of stock must not move it).
# doca_rajkot is multi-SKU because several DoCA commodities can feed one basket item (the five edible oils -> F008): the item's
# series is then the matched-model Jevons over those commodities, not the mean of their levels.
MULTI_SKU_SOURCES = ("dmart_ahmedabad", "vishal_diary", "district_cinema", "fresha_salon", "rajkot_shops", "doca_rajkot")
# Retail quotes reported by DoCA for the Rajkot centre (rpi/collectors/doca.py): a genuine retail price of a standard local variety,
# gated against the official item index like a proxy, but reported in its own bucket (it is not wholesale).
# Rajkot web shops (rpi/collectors/rajkot_shops.py) are Rajkot shelf prices: same bucket and gate.
# Both are SHADOW sources: they appear here so that switching an item is a data edit (source_plan.csv), but no item uses them yet.
RETAIL_SOURCES = ("doca_rajkot", "rajkot_shops")
# MODELLED series (not observed prices): counted in their own bucket, gated by the calibrated trend gate (rentsignal.trend_gate) instead of the correlation gate.
# rent_listings = listings-based stock-rent candidate for R001 (rpi/rentlistings.py): built on observed asking rents but through a stock model
# and with the modelled signal as stand-in before the listings, so it is gated and bucketed like the model it would replace (SHADOW, unused).
MODELLED_SOURCES = ("rent_signal", "rent_listings")
GATED_SOURCES = PROXY_SOURCES + RETAIL_SOURCES + MODELLED_SOURCES
# Items fed by a regulated CEILING (a cap, not an observed shelf price) are counted in the proxy share even though they use the
# tariff machinery; M001 = NPPA ceiling for paracetamol 500 mg; T004 = statutory maximum auto-rickshaw fare; D002 = Rajkot tea-hotel association rate card (not an observed paid price).
PROXY_ITEMS = ("M001", "T004", "D002")
MIN_OVERLAP, MIN_CORR, MAX_DRIFT = 6, 0.5, 0.10
# Long-horizon legs (2026-10-14). LEVEL_MONTHS is the overlap leg C needs before a level fit is admissible; DRIFT_MONTHS is the recent
# window over which bias is measured (the index is published on a 2025-01 base, so bias that predates the base is removed by the rebase).
LEVEL_MONTHS, DRIFT_MONTHS = 24, 24
MIN_CORR_12M, MIN_R2, SLOPE_LO, SLOPE_HI = 0.5, 0.5, 0.5, 1.5


def judge(proxy: pd.Series, official: pd.Series) -> dict:
    """Pure: two monthly level series (index = 'YYYY-MM') -> verdict dict.  Passes if any of legs A/B/C passes (see module docstring)."""
    both = pd.concat([proxy.rename("p"), official.rename("o")], axis=1).dropna().sort_index()
    n = len(both)
    out = {"n_overlap": int(n), "corr": None, "drift": None, "verdict": "pending",
           "corr_12m": None, "r2": None, "slope": None, "drift_recent": None, "legs": []}
    if n < MIN_OVERLAP:
        return out
    lg = np.log(both.astype(float))
    d = lg.diff().dropna()
    corr = float(d["p"].corr(d["o"])) if d["p"].std() > 0 and d["o"].std() > 0 else float("nan")
    drift = float(abs((lg["p"].iloc[-1] - lg["p"].iloc[0]) - (lg["o"].iloc[-1] - lg["o"].iloc[0])))
    out.update(corr=round(corr, 2) if corr == corr else None, drift=round(drift, 3))
    leg_a = bool(corr == corr and corr >= MIN_CORR and drift <= MAX_DRIFT)

    # --- long-horizon legs: only meaningful with a real overlap ------------------------------------------------
    leg_c = False
    if n >= LEVEL_MONTHS and lg["o"].std() > 0 and lg["p"].std() > 0:
        recent = lg.iloc[-DRIFT_MONTHS - 1:]
        d_rec = float(abs((recent["p"].iloc[-1] - recent["p"].iloc[0]) - (recent["o"].iloc[-1] - recent["o"].iloc[0])))
        b = np.polyfit(lg["o"].values, lg["p"].values, 1)
        slope = float(b[0])
        pred = np.polyval(b, lg["o"].values)
        ss = float(((lg["p"].values - lg["p"].values.mean()) ** 2).sum())
        r2 = float(1 - ((lg["p"].values - pred) ** 2).sum() / ss) if ss > 0 else float("nan")
        d12p, d12o = lg["p"].diff(12).dropna(), lg["o"].diff(12).dropna()
        c12 = float(d12p.corr(d12o)) if (len(d12p) > 2 and d12p.std() > 0 and d12o.std() > 0) else float("nan")
        out.update(r2=round(r2, 3) if r2 == r2 else None, slope=round(slope, 3), drift_recent=round(d_rec, 3),
                   corr_12m=round(c12, 2) if c12 == c12 else None)
        leg_c = bool(r2 == r2 and r2 >= MIN_R2 and SLOPE_LO <= slope <= SLOPE_HI and d_rec <= MAX_DRIFT)

    legs = ["A"] if leg_a else []
    if leg_c:
        legs.append("B" if (out["corr_12m"] is not None and out["corr_12m"] >= MIN_CORR_12M) else "C")
    out["legs"] = legs
    out["verdict"] = "pass" if legs else "fail"
    return out


def chain_series(piv: pd.DataFrame) -> pd.Series:
    """months x SKUs unit-price table -> matched-model Jevons level series (first month = 100)."""
    lg = np.log(piv.astype(float).where(piv > 0))
    step = lg.diff().mean(axis=1, skipna=True)
    lvl = 100.0 * np.exp(step.fillna(0.0).cumsum())
    lvl[step.isna() & (lvl.index != lvl.index[0])] = np.nan
    return lvl



SPLICED_CSV = "data/official/official_item_spliced.csv"


def official_series(official_csv, spliced_csv: str | None = None) -> pd.DataFrame:
    """Official Gujarat-urban item index by BASKET ITEM where possible, else by official code; longest history available.

    Prefers the spliced comparator (scripts/build_official_spliced.py: CPI2012 2014-01..2025-12 rescaled onto CPI2024's 2025 months).
    Gate power is the number of months a proxy and the official series BOTH cover, so a comparator that starts in 2025-01 caps every
    verdict at ~21 months however long the proxy series is.  Falls back to the raw CPI2024 file when the splice is absent.
    """
    from pathlib import Path
    sp = Path(spliced_csv) if spliced_csv else (Path(official_csv).resolve().parent / "official_item_spliced.csv")
    if sp.exists():
        d = pd.read_csv(sp)
        if {"item_id", "period", "index_value"}.issubset(d.columns):
            return d.pivot_table(index="period", columns="item_id", values="index_value", aggfunc="first")
    off = pd.read_csv(official_csv, dtype={"code": str})
    return off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")


def validate_proxies(conn, official_csv, mapping_csv, plan_csv, series_out: dict | None = None) -> list[dict]:
    plan = pd.read_csv(plan_csv, dtype=str, keep_default_na=False)
    mp = pd.read_csv(mapping_csv, dtype=str, keep_default_na=False).set_index("item_id")
    off = official_series(official_csv)
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
        o = off[it].dropna() if it in off.columns else (off[code].dropna() if code in off.columns else pd.Series(dtype=float))
        if series_out is not None:
            series_out[it] = (proxy, o, plan.set_index("item_id").loc[it, "primary_source"])
        if plan.set_index("item_id").loc[it, "primary_source"] in MODELLED_SOURCES:
            from .rentsignal import judge_trend
            res.append({"item_id": it, **judge_trend(proxy, o), "proxy_months": int(len(proxy)),
                        "official_months_after_proxy_start": int(sum(1 for m in o.index if len(proxy) and m >= proxy.index.min()))})
            continue
        res.append({"item_id": it, **judge(proxy, o), "proxy_months": int(len(proxy)),
                    "official_months_after_proxy_start": int(sum(1 for m in o.index if len(proxy) and m >= proxy.index.min()))})
    return res
