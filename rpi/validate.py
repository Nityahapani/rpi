"""Validation against official series + nowcast scoring."""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd


def load_official(conn, df: pd.DataFrame) -> int:
    rows = [(r.series_id, str(r.period)[:7], float(r.value), getattr(r, "source_url", "")) for r in df.itertuples()]
    conn.executemany("INSERT OR REPLACE INTO official_series VALUES(?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def official_series(conn, series_id: str) -> pd.Series:
    d = pd.read_sql_query("SELECT period, value FROM official_series WHERE series_id=? ORDER BY period",
                          conn, params=(series_id,))
    return pd.Series(d["value"].to_numpy(), index=pd.PeriodIndex(d["period"], freq="M"), dtype=float)


def compare(mine: pd.Series, official: pd.Series) -> dict:
    """Rebase both to 100 at first common month; compare levels and month-on-month changes."""
    common = mine.index.intersection(official.index)
    if len(common) < 2:
        return {"n_months": len(common), "note": "need >= 2 common months"}
    a, b = mine[common], official[common]
    a, b = a / a.iloc[0] * 100, b / b.iloc[0] * 100
    da, db = a.pct_change().dropna() * 100, b.pct_change().dropna() * 100
    out = {"n_months": len(common), "level_corr": float(a.corr(b)) if len(common) > 2 else np.nan,
           "mom_mae_pp": float((da - db).abs().mean()), "mom_bias_pp": float((da - db).mean())}
    out["mom_corr"] = float(da.corr(db)) if len(da) > 2 else np.nan
    return out


def record_nowcast(conn, series_id: str, mine: pd.Series):
    """Store our MoM estimate for the latest month BEFORE the official figure is known."""
    off = official_series(conn, series_id)
    p = mine.index[-1]
    if p in off.index or len(mine) < 2:
        return None
    mom = float((mine.iloc[-1] / mine.iloc[-2] - 1) * 100)
    conn.execute("INSERT OR REPLACE INTO nowcasts VALUES(?,?,?,?)",
                 (series_id, str(p), dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), mom))
    conn.commit()
    return p, mom


def score_nowcasts(conn, series_id: str) -> dict:
    """Compare stored nowcasts with official MoM; benchmark = 'last official MoM' (naive)."""
    off = official_series(conn, series_id)
    mom = off.pct_change() * 100
    nc = pd.read_sql_query("SELECT period, nowcast_mom FROM nowcasts WHERE series_id=? ORDER BY made_at",
                           conn, params=(series_id,)).drop_duplicates("period", keep="last")
    rows = []
    for r in nc.itertuples():
        p = pd.Period(r.period, "M")
        if p in mom.index and not np.isnan(mom[p]) and (p - 1) in mom.index and not np.isnan(mom[p - 1]):
            rows.append((p, r.nowcast_mom - mom[p], mom[p - 1] - mom[p]))
    if not rows:
        return {"n": 0}
    e = np.array([x[1] for x in rows])
    e0 = np.array([x[2] for x in rows])
    out = {"n": len(rows), "mae_nowcast_pp": float(np.abs(e).mean()), "mae_naive_pp": float(np.abs(e0).mean())}
    if len(rows) >= 8:
        d = e ** 2 - e0 ** 2
        se = d.std(ddof=1) / np.sqrt(len(d))
        out["diebold_mariano_t"] = float(d.mean() / se) if se > 0 else np.nan
        out["note"] = "DM t<0 favours the nowcast; small-sample, one-step, no HAC correction"
    return out
