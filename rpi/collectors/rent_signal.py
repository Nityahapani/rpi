"""R001 rent: MODELLED monthly series from Labour Bureau CPI-IW housing data (rpi/rentsignal.py, v3 panel-selected ensemble).

Not an observed price.  Inputs are the all-India housing-group index (half-yearly) and a 78-centre Labour Bureau panel used to calibrate the Rajkot step;
no MoSPI value enters the signal.  It is gated against the official Gujarat-urban rent item index by the calibrated TREND gate (rentsignal.trend_gate),
because the monthly-correlation gate cannot be passed by any trend-type signal (rentsignal.gate_ceiling).  That gate change applies to R001 only and
was adopted by explicit user decision on 2026-10-06 after the signal failed the correlation gate; the evidence is in inventory section AJ.

The signal is defined to the end of the last half-year with an all-India housing step in data/labour_bureau/housing_group.csv.  Beyond that the collector emits
nothing (the item is then imputed by the engine and the staleness is visible) rather than extrapolating.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .base import Observation
from .. import rentsignal as RS

SOURCE_ID = "rent_signal"


def level_series(root: Path, first="2025-01", today: str | None = None) -> pd.Series:
    base = (pd.Period(first, freq="M") - 1).strftime("%Y-%m")       # December base so January carries a full month of the 2025H1 step
    es = RS.ensemble_steps(root)
    last_half = es.half.max()
    last_month = f"{last_half[:4]}-{'06' if last_half.endswith('H1') else '12'}"
    end = min(today or dt.date.today().strftime("%Y-%m"), last_month)
    s = RS.ensemble_signal(root, first=base, last=end)
    return s[s.index >= first]


class RentSignalCollector:
    source_id = SOURCE_ID
    last_snapshot_id = None

    def __init__(self, root: Path, first="2025-01"):
        self.root, self.first = Path(root), first

    def collect(self, on_date):
        if not (self.root / "data/labour_bureau/housing_group.csv").exists():
            return
        for per, v in level_series(self.root, self.first).items():
            y, m = int(per[:4]), int(per[5:7])
            yield Observation(dt.date(y, m, 1), SOURCE_ID, "LB:rent-signal-v3",
                              "Modelled rent signal: Labour Bureau CPI-IW housing, panel-calibrated Rajkot step (E4+E5 ensemble)", "R001", "RAJKOT",
                              float(v), qty_base=1.0, base_unit="pc")
