"""Does 13 years of independent Rajkot/Ahmedabad history add seasonal skill to the 'own-trend' nowcast fill?

Rule under test (item level, h=1):   forecast_t = mean(last 12 monthly log relatives)  [own_trend, what the index uses]
                                    vs      own_trend + s_m,  s_m = mean over training years of (dlog_t - own_trend_t) for calendar month m.
Reference series: WFP/HDX Rajkot retail (2012-2023) and NECC Ahmedabad egg rate (2009-2026), data/reference/*.csv.

PRE-REGISTERED adoption rule (agreed before running; no tuning afterwards):
  an item gets the seasonal term only if
    (A) reference out-of-sample test, years 2018-2023 (each year predicted from earlier years only): RMSE improves by >= 10%, AND
    (B) the official Gujarat-urban item index 2025-02..2026-08 (rolling origin, s_m learned on reference years only -> never saw
        2025-26): RMSE does not worsen.
Writes data/reference/seasonal_backtest.csv and, for adopted items, data/reference/seasonal_factors.csv.
Run: PYTHONPATH=. python3 scripts/seasonal_backtest.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from rpi.nowcast_eval import official_panel

ROOT = Path(".")
WINDOW, MIN_OBS = 12, 8
MAP = {"F001": "Wheat flour", "F002": "Rice", "F004": "Lentils (moong)", "F006": "Oil (groundnut)", "F008": "Oil (sunflower)",
       "F009": "Milk (pasteurized)", "F013": "Sugar", "F014": "Tea (black)", "F015": "Salt (iodised)", "F021": "Potatoes",
       "F022": "Onions", "F023": "Tomatoes", "F026": "Sugar (jaggery/gur)", "F020": "NECC Ahmedabad"}


def ref_series() -> dict:
    w = pd.read_csv(ROOT / "data/reference/wfp_gujarat_retail.csv")
    w = w[w.market == "Rajkot"]
    w["p"] = pd.to_datetime(w.date).dt.to_period("M")
    out = {}
    for it, com in MAP.items():
        if com == "NECC Ahmedabad":
            n = pd.read_csv(ROOT / "data/reference/necc_ahmedabad_monthly.csv")
            n = n[n.period < "2026-09"]       # complete months only (Sep-Oct 2026 are partial/nowcast)
            s = pd.Series(n.price_inr_per_egg.values, index=pd.PeriodIndex(n.period, freq="M"))
        else:
            x = w[w.commodity == com].groupby("p").price.mean()
            s = x
        s = s[s > 0]
        out[it] = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    return out


def own_trend_resid(lr: pd.Series) -> pd.DataFrame:
    """For each month t: own-trend forecast made from months < t, and the realised error (actual - forecast)."""
    rows = []
    for i in range(len(lr)):
        h = lr.iloc[max(0, i - WINDOW):i].dropna()
        if len(h) < MIN_OBS or pd.isna(lr.iloc[i]):
            continue
        rows.append((lr.index[i], float(h.mean()), float(lr.iloc[i])))
    d = pd.DataFrame(rows, columns=["p", "own", "act"]).set_index("p")
    d["res"] = d.act - d.own
    return d


def seasonal_from(res: pd.Series, before_year: int) -> pd.Series:
    r = res[[p.year < before_year for p in res.index]]
    s = r.groupby([p.month for p in r.index]).mean()
    return s.reindex(range(1, 13)).fillna(0.0)


def main():
    rs = ref_series()
    off_lr, ww, indep, div = official_panel(ROOT)
    off_lr.index = pd.PeriodIndex(off_lr.index, freq="M")
    rows, adopted = [], {}
    for it, ser in rs.items():
        lr = np.log(ser).diff()
        d = own_trend_resid(lr)
        # (A) out-of-sample 2018-2023
        ea, eb = [], []
        for y in range(2018, 2024):
            s = seasonal_from(d.res, y)
            t = d[[p.year == y for p in d.index]]
            for p, r in t.iterrows():
                ea.append(r.res); eb.append(r.res - s[p.month])
        ea, eb = np.array(ea), np.array(eb)
        rmse_a0, rmse_a1 = np.sqrt((ea ** 2).mean()), np.sqrt((eb ** 2).mean())
        # (B) official overlap with s_m learned on ALL reference data before 2025
        s_all = seasonal_from(d.res, 2025)
        o = off_lr[it] if it in off_lr.columns else None
        rmse_b0 = rmse_b1 = np.nan; nb = 0
        if o is not None:
            e0, e1 = [], []
            for t in range(MIN_OBS, len(o)):
                own = float(o.iloc[max(0, t - WINDOW):t].mean())
                a = float(o.iloc[t]); m = o.index[t].month
                e0.append(a - own); e1.append(a - own - s_all[m])
            e0, e1 = np.array(e0), np.array(e1); nb = len(e0)
            rmse_b0, rmse_b1 = np.sqrt((e0 ** 2).mean()), np.sqrt((e1 ** 2).mean())
        ok = bool(rmse_a1 <= 0.9 * rmse_a0 and rmse_b1 <= rmse_b0)
        rows.append(dict(item_id=it, reference=MAP[it], ref_months=int(lr.notna().sum()), nA=len(ea),
                         A_own_pp=round(rmse_a0 * 100, 3), A_seasonal_pp=round(rmse_a1 * 100, 3), A_gain_pct=round((1 - rmse_a1 / rmse_a0) * 100, 1),
                         nB=nb, B_own_pp=round(rmse_b0 * 100, 3), B_seasonal_pp=round(rmse_b1 * 100, 3),
                         B_gain_pct=round((1 - rmse_b1 / rmse_b0) * 100, 1) if nb else None, adopt=ok))
        if ok:
            adopted[it] = s_all
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "data/reference/seasonal_backtest.csv", index=False)
    print(out.to_string(index=False))
    fac = ROOT / 'data/reference/seasonal_factors.csv'
    if not adopted and fac.exists():
        fac.unlink()
    if adopted:
        pd.DataFrame([dict(item_id=i, month=m, s_log=round(float(v), 5)) for i, s in adopted.items() for m, v in s.items()]).to_csv(
            ROOT / "data/reference/seasonal_factors.csv", index=False)
    if not adopted:
        print('\nNo item meets the pre-registered rule -> seasonal term NOT adopted; nowcast stays own_trend.')
    # total-level effect on the official panel (weights of the whole official-mapped basket)
    if adopted:
        T = len(off_lr); e0, e1 = [], []
        act = (off_lr * ww).sum(axis=1)
        for t in range(MIN_OBS, T):
            own = off_lr.iloc[max(0, t - WINDOW):t].mean().fillna(0.0)
            adj = sum(float(ww[i]) * float(adopted[i][off_lr.index[t].month]) for i in adopted)
            f0 = float((ww * own).sum()); e0.append(f0 - act.iloc[t]); e1.append(f0 + adj - act.iloc[t])
        e0, e1 = np.array(e0), np.array(e1)
        print(f"\nTOTAL nowcast h1 RMSE (pp), official panel origins {off_lr.index[MIN_OBS]}..{off_lr.index[-1]}, n={len(e0)}: "
              f"own_trend {np.sqrt((e0**2).mean())*100:.3f}  +seasonal {np.sqrt((e1**2).mean())*100:.3f}  "
              f"bias {e0.mean()*100:+.3f} -> {e1.mean()*100:+.3f}; adopted weight share {sum(ww[i] for i in adopted)*100:.1f}%")


main()
