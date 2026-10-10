"""Read-only loaders. Nothing in this module writes to the pipeline's data."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "rpi.sqlite"
DIVISIONS_CSV = ROOT / "docs" / "data" / "rpi_divisions.csv"
TOTAL_CSV = ROOT / "docs" / "data" / "rpi_total.csv"
WEIGHTS_CSV = ROOT / "data" / "official" / "gujarat_urban_division_weights_implied.csv"


@dataclass
class Panel:
    """Aligned monthly panel. All changes are month-on-month, in percent."""

    periods: list[str]          # every rpi period, e.g. 2025-01 .. 2026-10
    divisions: list[str]        # rpi division codes that the official data also has
    levels: pd.DataFrame        # rpi division levels, index = period
    weights: pd.Series          # division weights over `divisions`, sum to 1
    official_mom: pd.Series     # official general MoM in %, index = period
    rpi_total_mom: pd.Series    # published rpi total MoM in %, index = period
    uncovered_weight: float     # share of the official general weight with no rpi division


def _official_general(con: sqlite3.Connection) -> pd.Series:
    s = pd.read_sql(
        "select period, value from official_series where series_id='CPI2024_GUJARAT_URBAN_GENERAL'",
        con,
    )
    return s.set_index("period")["value"].astype(float).sort_index()


def _official_divisions(con: sqlite3.Connection) -> pd.DataFrame:
    s = pd.read_sql(
        "select series_id, period, value from official_series "
        "where series_id like 'CPI2024_GUJARAT_URBAN_DIV_%'",
        con,
    )
    s["code"] = s.series_id.str.rsplit("_", n=1).str[-1]
    return s.pivot(index="period", columns="code", values="value").sort_index()


def _division_weights() -> pd.Series:
    """Official Gujarat-urban division weights (implied from MoSPI CPI2024; see the file's provenance)."""
    w = pd.read_csv(WEIGHTS_CSV, dtype={"code": str}).set_index("code")["gujarat_urban_implied"]
    return w.astype(float)


def load_panel() -> Panel:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        official = _official_general(con)
        off_div = _official_divisions(con)
    finally:
        con.close()
    dw = _division_weights()

    rpi_div = pd.read_csv(DIVISIONS_CSV, dtype={"period": str}).set_index("period")
    rpi_div.columns = [str(c).zfill(2) for c in rpi_div.columns]
    divisions = [c for c in rpi_div.columns if c in off_div.columns]
    levels = rpi_div[divisions].astype(float)

    w = dw.reindex(divisions).astype(float)
    uncovered = float(dw.drop(index=divisions, errors="ignore").sum() / dw.sum())
    weights = w / w.sum()

    off_mom = (np.log(official).diff() * 100.0).dropna()
    total = pd.read_csv(TOTAL_CSV).set_index("period")["mom_pct"].astype(float)

    return Panel(
        periods=list(rpi_div.index),
        divisions=divisions,
        levels=levels,
        weights=weights,
        official_mom=off_mom,
        rpi_total_mom=total,
        uncovered_weight=uncovered,
    )


def division_changes(p: Panel) -> pd.DataFrame:
    """Month-on-month log changes of the rpi division levels, in percent."""
    return np.log(p.levels).diff() * 100.0
