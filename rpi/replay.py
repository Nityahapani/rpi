"""Real-pipeline replay ("pseudo-real-time" back-test) of the published index.

For each past cut-off month c (= "the last official MoSPI month we had"), a COPY of the database is truncated the way it
was in real time: all official-linked stand-in observations dated after c are removed (the official release had not
happened yet), everything else is kept (independent feeds were being collected daily). The unchanged production engine
(`run_index`) then produces the nowcast for c+1, c+2, ... which is compared with what the same engine publishes once the
official data for those months are in (the "actual" = the series in docs/data/rpi_total.csv), and with the independent
official yardstick (MoSPI CPI-2024 Gujarat-urban general index, rebased to the base month).

Caveats stated on the output: (i) the independent feeds are taken as they exist today (several started collecting after
some cut-offs - optimistic); (ii) only the engine's own nowcast rule is replayed (own_trend, no hindsight tuning).
"""
from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from . import db
from .config import ROOT, load_settings
from .index.engine import _load_ref, price_update_weights, run_index


def _run(db_path: Path, settings: dict, cut: str | None):
    # The DB copy is ~45 MB; the temp directory MUST be removed even when run_index raises, or repeated replays
    # (e.g. the test suite) fill up the filesystem. (It did.)
    with tempfile.TemporaryDirectory(prefix="rpi_replay_") as td:
        tmp = Path(td) / "replay.sqlite"
        shutil.copy(db_path, tmp)
        conn = sqlite3.connect(tmp)
        try:
            if cut:
                conn.execute("""DELETE FROM observations WHERE sku_id IN (SELECT sku_id FROM products WHERE source_id='official_link')
                                AND substr(obs_date,1,7) > ?""", (cut,))
                conn.commit()
            s = {**settings, "index": {**settings["index"], "bootstrap_reps": 2}}
            run = run_index(conn, s, store=False)
            wts = None
            if cut is None:
                items, w, wsrc = _load_ref(conn)
                bp = settings.get("project", {}).get("base_period", "")
                w, _ = price_update_weights(w, wsrc, bp)
                wts = w
        finally:
            conn.close()
    return run.variants["jevons_chain"], wts


def replay(root: Path = ROOT, first_cut: str = "2025-06", horizons=(1, 2, 3)) -> dict:
    root = Path(root)
    settings = load_settings()
    dbp = root / "data/rpi.sqlite"
    full, w = _run(dbp, settings, None)
    actual = full.total
    last_off = pd.read_csv(root / "data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str}).period.astype(str).max()
    last_off = pd.Period(last_off, "M")
    off = pd.read_csv(root / "data/official/official_series.csv")
    gu = off[off.series_id == "CPI2024_GUJARAT_URBAN_GENERAL"].assign(p=lambda d: pd.PeriodIndex(d.period.astype(str), freq="M")).set_index("p")["value"].astype(float)
    base = actual.index[0]
    gu = gu / gu.loc[base] * 100 if base in gu.index else gu
    # total-level own-trend benchmark computed from the full-run item levels (no independent information at all)
    L = full.items
    lr = np.log(L).diff()
    wn = w.reindex(L.columns)
    rows = []
    for c in pd.period_range(first_cut, last_off - 1, freq="M"):
        v, _ = _run(dbp, settings, str(c))
        for h in horizons:
            t = c + h
            if t > last_off or t not in actual.index:
                continue
            own = lr.loc[:c].iloc[1:].tail(12).mean().fillna(0.0)
            ownf = float((L.loc[c] * np.exp(h * own) * wn).sum() / wn.sum())
            rows.append(dict(cutoff=str(c), h=h, period=str(t), replay_level_at_cutoff=float(v.total.loc[c]), actual_level_at_cutoff=float(actual.loc[c]),
                             nowcast=float(v.total.loc[t]), actual=float(actual.loc[t]), own_trend_only=ownf, zero_change=float(actual.loc[c]),
                             gu_official=float(gu.loc[t]) if t in gu.index else np.nan, gu_official_at_cutoff=float(gu.loc[c]) if c in gu.index else np.nan,
                             nowcast_obs_weight=float(v.coverage.loc[t])))
    df = pd.DataFrame(rows)
    df["err_pct"] = (df.nowcast / df.actual - 1) * 100
    df["err_own_trend_only_pct"] = (df.own_trend_only / df.actual - 1) * 100
    df["err_zero_change_pct"] = (df.zero_change / df.actual - 1) * 100
    df["err_vs_official_pct"] = (df.nowcast / df.gu_official - 1) * 100
    return dict(table=df, actual=actual, gu=gu, last_official=str(last_off))
