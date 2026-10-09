"""Listings-based Rajkot rent: a NEW-LEASE (asking-rent) index, turned into a STOCK-rent candidate for R001 - a SHADOW candidate.

R001 (house rent, 19% of the basket) is currently MODELLED from Labour Bureau CPI-IW housing data (rpi/rentsignal.py).  This module builds
the observed alternative from the accruing listings panel (rpi/collectors/rent_listings.py) and says, every refresh, how far it has got.

1. prepare()        residential listings in Rajkot city (separate towns of the district dropped), the project's junk screen
                    (rent_listings.clean), one row per listing at its FIRST asking rent (later cuts are bargaining while marketed, not rent
                    inflation), cross-portal duplicates dropped (same BHK, area, locality, rent within 2%, listed within 14 days).
2. hedonic_index()  log rent on month effects + log area (imputed by BHK x type where missing, with a flag) + BHK + type + locality fixed
                    effects (localities with >= 6 listings) + portal + furnished-page flag, Huber-robust IRLS; month index = exp(effect);
                    listing bootstrap within month for a 90% band.  A month QUALIFIES with >= 25 kept listings (the project rule).  A month
                    is a SURVIVOR month when most of its listings were first captured > 14 days after posting (the first crawl was
                    2026-10-02, so Jul-Sep 2026 are survivor samples: listings let quickly are missing); survivor and incomplete months are
                    reported but never used for the stock candidate.
3. stock_candidate() the CPI concept is what sitting tenants pay.  With 11-month leave-and-licence agreements about 1/K (K = 12) of
                    tenancies re-price to market each month, so stock rent grows at the 12-month average of new-lease growth.  The candidate
                    starts AS the modelled signal M and corrects it by the listings' average deviation from it over the last K months:
                        dlog S_t = dlog M_t + (1/K) * sum_{k<K} 1[usable(t-k)] * (dlog N_{t-k} - dlog M_{t-k})
                    With no usable listing month S == M (today's R001 input); with K usable months dlog S_t = mean_K(dlog N) plus the modelled
                    signal's deviation from its own 12-month mean (small: M is a half-year run-rate).  listing_share = usable months / K.
                    Beyond the modelled signal's last month S is extended only with a full window of listing changes - never extrapolated.
4. screen()         R001 trend gate (rentsignal.judge_trend) against the official Gujarat-urban house-rent index, the qualifying-months rule
                    and a readiness verdict -> data/official/rent_listings_index.json.  Switching R001 to primary_source = rent_listings is a
                    recorded decision once listing_share >= 0.5, two consecutive months qualify and the gate passes.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .collectors.rent_listings import clean

K_STOCK = 12
MIN_KEPT = 25
MIN_MONTH_ROWS = 8           # a month with fewer kept listings gets no effect in the regression at all
MIN_LOCALITY = 6
FRESH_DAYS = 14
N_BOOT = 200
OUT_JSON = "data/official/rent_listings_index.json"
OUTSIDE_CITY = {"jetpur", "gondal", "morbi", "dhoraji", "upleta", "jasdan", "wankaner", "jamnagar", "junagadh", "kotda sangani",
                "lodhika", "paddhari", "padadhari", "virpur", "shapar", "veraval", "metoda"}
RESIDENTIAL = ("flat", "house", "villa", "builder_floor", "studio", "room", "penthouse")


def prepare(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["key"] = df["key"].astype(str)
    df = df.sort_values("first_seen").drop_duplicates("key", keep="first")          # first asking rent per listing
    df = df[df.ptype.isin(RESIDENTIAL) & ~df.locality.fillna("").isin(OUTSIDE_CITY)]
    df = clean(df)
    df = df[df.listed.astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$")].copy()
    df["month"] = df.listed.astype(str).str[:7]
    df["lag_days"] = (pd.to_datetime(df.first_seen) - pd.to_datetime(df.listed)).dt.days.clip(lower=0)
    # cross-portal duplicates: keep the earliest-seen copy
    df = df.sort_values("first_seen").reset_index(drop=True)
    drop = set()
    if df.portal.nunique() > 1:
        a = df[df.portal == "squareyards"]
        b = df[df.portal != "squareyards"]
        for i, r in a.iterrows():
            m = b[(b.bhk == r.bhk) & (b.locality == r.locality) & ((b.rent / r.rent - 1).abs() <= 0.02) &
                  ((pd.to_datetime(b.listed) - pd.to_datetime(r.listed)).dt.days.abs() <= 14) &
                  ((b.sqft.isna() & pd.isna(r.sqft)) | ((b.sqft - r.sqft).abs() <= 25))]
            if len(m):
                drop.add(i if r.first_seen >= m.first_seen.min() else m.index[0])
    df = df.drop(index=list(drop))
    df["lrent"] = np.log(df.rent.astype(float))
    df["bhk_c"] = df.bhk.fillna(0).astype(int).clip(upper=4)
    med = df.groupby(["bhk_c", "ptype"]).sqft.transform("median")
    df["sqft_missing"] = df.sqft.isna().astype(float)
    sq = df.sqft.fillna(med).fillna(df.sqft.median() if df.sqft.notna().any() else 900.0)
    df["lsqft_c"] = np.log(sq.astype(float)) - np.log(900.0)
    vc = df.locality.fillna("").value_counts()
    keep_loc = set(vc[(vc >= MIN_LOCALITY) & (vc.index != "")].index)
    df["loc_c"] = df.locality.where(df.locality.isin(keep_loc), "other")
    df["furnished_page"] = df.source_url.astype(str).str.contains("furnished").astype(float)
    return df.reset_index(drop=True)


def _design(df: pd.DataFrame, months: list[str]) -> tuple[np.ndarray, list[str]]:
    cols, X = ["const"], [np.ones(len(df))]
    for m in months[1:]:
        cols.append(f"m:{m}"); X.append((df.month == m).to_numpy(float))
    for c in ("lsqft_c", "sqft_missing", "furnished_page"):
        cols.append(c); X.append(df[c].to_numpy(float))
    for b in (0, 1, 3, 4):                                                  # base: 2 BHK
        cols.append(f"bhk:{b}"); X.append((df.bhk_c == b).to_numpy(float))
    for t in RESIDENTIAL[1:]:                                               # base: flat
        cols.append(f"type:{t}"); X.append((df.ptype == t).to_numpy(float))
    for loc in sorted(set(df.loc_c) - {"other"}):                           # base: other localities
        cols.append(f"loc:{loc}"); X.append((df.loc_c == loc).to_numpy(float))
    if df.portal.nunique() > 1:
        cols.append("portal:squareyards"); X.append((df.portal == "squareyards").to_numpy(float))
    X = np.column_stack(X)
    keep = [i for i in range(X.shape[1]) if i == 0 or X[:, i].std() > 0]
    return X[:, keep], [cols[i] for i in keep]


def huber_fit(X: np.ndarray, y: np.ndarray, c: float = 1.345, iters: int = 50) -> np.ndarray:
    """Huber M-estimate by iteratively reweighted least squares (scale = MAD of the current residuals), started from OLS."""
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    for _ in range(iters):
        r = y - X @ beta
        s = 1.4826 * np.median(np.abs(r - np.median(r))) or 1e-9
        u = np.abs(r) / s
        sw = np.sqrt(np.where(u <= c, 1.0, c / np.maximum(u, 1e-12)))
        beta_new = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0]
        done = np.max(np.abs(beta_new - beta)) < 1e-8
        beta = beta_new
        if done:
            break
    return beta


def _month_effects(df: pd.DataFrame, months: list[str]) -> pd.Series:
    X, cols = _design(df, months)
    beta = huber_fit(X, df.lrent.to_numpy(float))
    eff = {months[0]: 0.0}
    eff.update({c[2:]: float(b) for c, b in zip(cols, beta) if c.startswith("m:")})
    return pd.Series(eff).reindex(months)


def coefficient_summary(df: pd.DataFrame, months: list[str]) -> dict:
    """Non-month, non-locality coefficients of the hedonic fit (log points), for transparency in the report."""
    sub = df[df.month.isin(months)].reset_index(drop=True)
    if not months or len(sub) < 20:
        return {}
    X, cols = _design(sub, months)
    if X.shape[0] <= X.shape[1]:
        return {}
    b = huber_fit(X, sub.lrent.to_numpy(float))
    return {c: round(float(v), 3) for c, v in zip(cols, b) if not c.startswith(("m:", "loc:"))}


def hedonic_index(df: pd.DataFrame, n_boot: int = N_BOOT, seed: int = 7, today: dt.date | None = None) -> pd.DataFrame:
    """One row per listing month: n, fresh share, flags, index (first month = 100) and a 90% bootstrap band."""
    today = today or dt.date.today()
    cnt = df.month.value_counts().sort_index()
    months = [m for m in cnt.index if cnt[m] >= MIN_MONTH_ROWS]
    out = pd.DataFrame({"month": cnt.index, "n": cnt.values})
    out["fresh_share"] = out.month.map(df.assign(f=(df.lag_days <= FRESH_DAYS).astype(float)).groupby("month").f.mean()).round(3)
    out["survivor"] = out.fresh_share < 0.5
    out["complete"] = out.month < today.strftime("%Y-%m")
    out["qualified"] = out.n >= MIN_KEPT
    out["usable"] = out.qualified & ~out.survivor & out.complete
    if len(months) < 2:
        out["index"], out["lo90"], out["hi90"] = np.nan, np.nan, np.nan
        return out
    sub = df[df.month.isin(months)].reset_index(drop=True)
    eff = _month_effects(sub, months)
    rng = np.random.default_rng(seed)
    boots = []
    groups = [np.flatnonzero(sub.month.to_numpy() == m) for m in months]
    for _ in range(n_boot):
        idx = np.concatenate([rng.choice(g, size=len(g), replace=True) for g in groups])
        try:
            boots.append(_month_effects(sub.iloc[idx].reset_index(drop=True), months).to_numpy())
        except np.linalg.LinAlgError:
            continue
    B = np.array(boots) if boots else np.full((1, len(months)), np.nan)
    lev = pd.Series(100 * np.exp(eff.to_numpy()), index=months)
    lo = pd.Series(100 * np.exp(np.nanpercentile(B, 5, axis=0)), index=months)
    hi = pd.Series(100 * np.exp(np.nanpercentile(B, 95, axis=0)), index=months)
    out["index"] = out.month.map(lev).round(2)
    out["lo90"] = out.month.map(lo).round(2)
    out["hi90"] = out.month.map(hi).round(2)
    return out


def stock_candidate(new_idx: pd.Series, modelled: pd.Series, usable: set[str], K: int = K_STOCK) -> pd.DataFrame:
    """Modelled stock signal corrected by the listings' average new-lease deviation over the last K months (see module docstring)."""
    m = np.log(modelled.astype(float).sort_index())
    dm = m.diff()
    n = np.log(new_idx.astype(float).sort_index())
    months = sorted(set(m.index) | set(n.index))
    allp = pd.period_range(months[0], months[-1], freq="M").strftime("%Y-%m")
    dn = {}
    for p in allp:
        prev = (pd.Period(p, "M") - 1).strftime("%Y-%m")
        if p in usable and prev in usable and p in n.index and prev in n.index:
            dn[p] = float(n[p] - n[prev])
    rows, level = [], None
    for i, p in enumerate(allp):
        window = [allp[j] for j in range(max(0, i - K + 1), i + 1)]
        dev = [dn[q] - float(dm.get(q, np.nan)) for q in window if q in dn and pd.notna(dm.get(q, np.nan))]
        share = sum(1 for q in window if q in dn) / K
        if level is None:
            if p in m.index:
                level = float(np.exp(m[p]))
                rows.append(dict(month=p, level=level, dlog=np.nan, listing_share=share, from_listings_only=False))
            continue
        if pd.notna(dm.get(p, np.nan)):
            d = float(dm[p]) + sum(dev) / K
            only = False
        elif len([q for q in window if q in dn]) == K:
            d = float(np.mean([dn[q] for q in window]))
            only = True
        else:
            break                                                          # beyond the modelled signal without a full listings window: stop
        level *= float(np.exp(d))
        rows.append(dict(month=p, level=level, dlog=d, listing_share=share, from_listings_only=only))
    return pd.DataFrame(rows)


def candidate_series(root: Path) -> pd.Series:
    res = screen(Path(root), write=False)
    s = pd.DataFrame(res["stock_candidate"])
    return s.set_index("month").level if len(s) else pd.Series(dtype=float)


def _consecutive(flags: list[bool]) -> int:
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    return best


def screen(root: Path, write: bool = True, today: dt.date | None = None, n_boot: int = N_BOOT) -> dict:
    from . import rentsignal as RS
    from .collectors.rent_listings import _load_panel
    from .collectors.rent_signal import level_series
    root = Path(root)
    today = today or dt.date.today()
    panel = _load_panel(root / "data/rent_listings.csv")
    res = {"generated": today.isoformat(), "item_id": "R001", "stock_rule": f"dlog S = dlog M + mean_{K_STOCK}(usable dlog N - dlog M)",
           "n_panel_rows": int(len(panel))}
    if panel.empty:
        return {**res, "verdict": "no listings yet", "stock_candidate": [], "months": []}
    df = prepare(panel)
    idx = hedonic_index(df, n_boot=n_boot, today=today)
    usable = set(idx.loc[idx.usable, "month"])
    modelled = level_series(root)
    lev = idx.set_index("month")["index"].dropna()
    sc = stock_candidate(lev, modelled, usable)
    official = RS.official_rent(root)
    gate = RS.judge_trend(sc.set_index("month").level if len(sc) else pd.Series(dtype=float), official)
    share = float(sc.listing_share.iloc[-1]) if len(sc) else 0.0
    q_run = _consecutive(idx.sort_values("month").qualified.tolist())
    u_run = _consecutive(idx.sort_values("month").usable.tolist())
    revisions = panel.groupby("key").rent.agg(["first", "last", "count"])
    cut = revisions[revisions["count"] > 1]
    if share >= 0.5 and u_run >= 2 and gate["verdict"] == "pass":
        verdict = "ready to PROPOSE switching R001 to rent_listings (recorded decision)"
    elif gate["verdict"] == "fail" and share >= 0.5:
        verdict = "listings-based stock rent FAILS the R001 trend gate: keep the modelled signal"
    else:
        nxt = (pd.Period(today, "M")).strftime("%Y-%m")
        verdict = (f"accruing: listing share of the 12-month window {share:.0%}; usable months so far {sorted(usable) or 'none'} "
                   f"(the first usable month-on-month change needs two consecutive complete, non-survivor months; the first such pair "
                   f"can be {nxt} and the month after)")
    fit_months = [m for m, n in zip(idx.month, idx.n) if n >= MIN_MONTH_ROWS]
    coefs = coefficient_summary(df, fit_months)
    res.update({
        "n_listings_used": int(len(df)), "portals": df.portal.value_counts().to_dict(),
        "months": idx.to_dict("records"), "qualified_consecutive": q_run, "usable_consecutive": u_run,
        "usable_months": sorted(usable), "hedonic_coefficients": coefs,
        "asking_rent_revisions": {"listings_revised": int(len(cut)),
                                  "median_change_pct": round(float(((cut["last"] / cut["first"] - 1) * 100).median()), 2) if len(cut) else None},
        "stock_candidate": sc.round(6).to_dict("records"), "listing_share_latest": round(share, 3),
        "gate_vs_official": gate, "verdict": verdict,
        "note": "SHADOW: R001 stays on rent_signal (modelled) until the verdict says 'ready' and the switch is recorded in data/source_plan.csv",
    })
    if write:
        (root / OUT_JSON).write_text(json.dumps(res, indent=1, default=str))
    return res
