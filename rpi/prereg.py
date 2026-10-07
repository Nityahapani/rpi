"""Pre-registration and live scoring of every gated series (inventory AK).

Why: each proxy gate and the rent model were chosen or tuned on data that had already been seen.  The only cure is to commit to predictions BEFORE the official figure exists
and to score them afterwards.  Every refresh therefore does three things, mechanically:

  1. LOG  (`log_predictions`)  For each gated item (proxies, retail quotes, modelled rent) and each target month T after the item's last official month L, append
     pred = 100*(ln proxy[T] - ln proxy[L]) (the cumulative change the series claims since the last official month).  Rows are append-only; a row is never edited.
     Targets at or before L are never logged (that would be a back-fit).  Several snapshots per target are kept (daily feeds move through the month).
  2. SEEN  (`log_official_arrivals`)  Record the first refresh at which each official item-month was seen.  A prediction counts only if it was made strictly before that date.
  3. SCORE (`score`)  When official data for T arrives, error = pred - 100*(ln off[T] - ln off[L]).  Standardised z = error / (s_i * sqrt(h)), where s_i is the item's own
     official monthly sd over the 24 months before L and h = months from L to T (the same noise scaling as the rent trend gate).  A two-sided CUSUM (k = 0.5, h_c = 4) over the
     item's targets in chronological order flags drift.  Flags surface as a refresh error; `[prereg] auto_demote = true` in settings.toml reverts a flagged item to `official_link`
     (default false: a person looks first).

The ledger starts at its first run; nothing is back-filled, so everything in it is genuinely ex ante.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

LEDGER = "data/preregistered/predictions.csv"
SEEN = "data/preregistered/official_seen.csv"
DEMOTIONS = "data/preregistered/demotions.csv"
SCORECARD = "data/official/prereg_scorecard.csv"
LEDGER_COLS = ["made_on", "item_id", "source", "base_period", "target_period", "horizon", "pred_pp"]
SEEN_COLS = ["item_id", "period", "first_seen_on", "bootstrap"]
K_CUSUM, H_CUSUM, WINDOW = 0.5, 4.0, 24


def _read(root, rel, cols):
    p = Path(root) / rel
    return pd.read_csv(p, dtype={"item_id": str}) if p.exists() else pd.DataFrame(columns=cols)


def _write(root, rel, df):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)


def _h(base, target):
    return int((pd.Period(target, freq="M") - pd.Period(base, freq="M")).n)


def log_predictions(root, series: dict, today: str | None = None) -> int:
    """series: item_id -> (proxy level Series, official level Series, source).  Appends new rows; returns the number appended."""
    today = today or dt.date.today().isoformat()
    led = _read(root, LEDGER, LEDGER_COLS)
    new = []
    for it, (proxy, off, src) in series.items():
        off, proxy = off.dropna().sort_index(), proxy.dropna().sort_index()
        if off.empty or proxy.empty or off.index[-1] not in proxy.index:
            continue
        L = off.index[-1]
        for T in proxy.index[proxy.index > L]:
            pred = 100 * (np.log(proxy[T]) - np.log(proxy[L]))
            new.append(dict(made_on=today, item_id=it, source=src, base_period=L, target_period=T, horizon=_h(L, T), pred_pp=round(float(pred), 4)))
    if not new:
        return 0
    new = pd.DataFrame(new)
    key = lambda d: d.made_on + "|" + d.item_id + "|" + d.base_period + "|" + d.target_period
    if len(led):
        new = new[~key(new).isin(set(key(led)))]          # one snapshot per item/target/day
    if new.empty:
        return 0
    _write(root, LEDGER, pd.concat([led, new], ignore_index=True)[LEDGER_COLS])
    return len(new)


def log_official_arrivals(root, official: dict, today: str | None = None) -> int:
    """official: item_id -> official level Series.  First sighting of each item-month is stamped; the first ever run is marked bootstrap (no predictions can be scored against it)."""
    today = today or dt.date.today().isoformat()
    seen = _read(root, SEEN, SEEN_COLS)
    boot = len(seen) == 0
    have = set(seen.item_id + "|" + seen.period) if len(seen) else set()
    rows = [dict(item_id=it, period=p, first_seen_on=today, bootstrap=boot) for it, s in official.items() for p in s.dropna().index if f"{it}|{p}" not in have]
    if rows:
        _write(root, SEEN, pd.concat([seen, pd.DataFrame(rows)], ignore_index=True)[SEEN_COLS])
    return len(rows)


def cusum(z: list[float], k: float = K_CUSUM, h: float = H_CUSUM) -> dict:
    hi = lo = 0.0
    flag = False
    for v in z:
        hi, lo = max(0.0, hi + v - k), max(0.0, lo - v - k)
        flag = flag or hi > h or lo > h
    return dict(cusum_hi=round(hi, 2), cusum_lo=round(lo, 2), flag=bool(flag))


def score(root, official: dict) -> pd.DataFrame:
    """Per-target scored rows (each target scored with the latest snapshot made strictly before the official value was first seen)."""
    led = _read(root, LEDGER, LEDGER_COLS)
    seen = _read(root, SEEN, SEEN_COLS)
    if led.empty or seen.empty:
        return pd.DataFrame()
    seen = seen[~seen.bootstrap.astype(bool)].set_index(["item_id", "period"]).first_seen_on
    rows = []
    for (it, base, tgt), g in led.groupby(["item_id", "base_period", "target_period"]):
        off = official.get(it)
        if off is None or tgt not in off.index or base not in off.index or (it, tgt) not in seen.index:
            continue
        g = g[g.made_on < seen[(it, tgt)]]
        if g.empty:
            continue
        r = g.sort_values("made_on").iloc[-1]
        past = np.log(off.dropna().sort_index()).diff().dropna() * 100
        past = past[past.index < base].iloc[-WINDOW:]
        s = float(past.std()) if len(past) >= 6 else np.nan
        actual = 100 * (np.log(off[tgt]) - np.log(off[base]))
        err = float(r.pred_pp - actual)
        rows.append(dict(item_id=it, source=r.source, base_period=base, target_period=tgt, horizon=int(r.horizon), made_on=r.made_on, pred_pp=float(r.pred_pp),
                         actual_pp=round(float(actual), 4), error_pp=round(err, 4), item_sd_pp=round(s, 4) if s == s else np.nan,
                         z=round(err / (s * np.sqrt(r.horizon)), 3) if s == s and s > 0 else np.nan))
    return pd.DataFrame(rows)


def scorecard(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return pd.DataFrame(columns=["item_id", "source", "n_scored", "mean_error_pp", "mae_pp", "mean_z", "cusum_hi", "cusum_lo", "flag"])
    out = []
    for it, g in scored.sort_values("target_period").groupby("item_id"):
        z = g.z.dropna().tolist()
        out.append(dict(item_id=it, source=g.source.iloc[0], n_scored=len(g), mean_error_pp=round(g.error_pp.mean(), 3), mae_pp=round(g.error_pp.abs().mean(), 3),
                        mean_z=round(float(np.mean(z)), 3) if z else np.nan, **cusum(z)))
    return pd.DataFrame(out)


def apply_demotions(root, flagged: list[str], enabled: bool, today: str | None = None) -> list[str]:
    """Revert flagged items to `official_link` in data/source_plan.csv (only if enabled) and record the demotion."""
    if not enabled or not flagged:
        return []
    today = today or dt.date.today().isoformat()
    p = Path(root) / "data/source_plan.csv"
    plan = pd.read_csv(p, dtype=str, keep_default_na=False)
    done = []
    for it in flagged:
        m = plan.item_id == it
        if m.any() and plan.loc[m, "primary_source"].iloc[0] != "official_link":
            old = plan.loc[m, "primary_source"].iloc[0]
            plan.loc[m, ["primary_source", "class"]] = ["official_link", "linked"]
            plan.loc[m, "note"] = plan.loc[m, "note"] + f" | DEMOTED {today} by the pre-registered CUSUM (was {old})"
            done.append(it)
            d = _read(root, DEMOTIONS, ["date", "item_id", "was"])
            _write(root, DEMOTIONS, pd.concat([d, pd.DataFrame([dict(date=today, item_id=it, was=old)])], ignore_index=True))
    if done:
        plan.to_csv(p, index=False, lineterminator="\r\n")
    return done
