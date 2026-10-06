"""FRC-approved Rajkot private-school fees -> monthly E001 series (see rpi/frc_fees.py for the rules, fixed before the gate was run)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from .base import Observation
from .. import frc_fees as F

SOURCE_ID = "frc_rajkot"


def level_series(root: Path) -> pd.Series:
    fees = pd.read_csv(Path(root) / "data/frc/rajkot_fees.csv")
    items = pd.read_csv(Path(root) / "data/official/mospi_cpi2012_gujarat_urban_items.csv")
    lv = F.monthly_level(F.ay_changes(fees), F.month_profile(items))
    lv.index = lv.index.astype(str)
    return lv


class FrcSchoolFeeCollector:
    source_id = SOURCE_ID
    last_snapshot_id = None

    def __init__(self, root: Path, first="2025-01"):
        self.root, self.first = Path(root), first

    def collect(self, on_date):
        if not (self.root / "data/frc/rajkot_fees.csv").exists():
            return
        lv = level_series(self.root)
        today = dt.date.today().strftime("%Y-%m")
        for per, v in lv.items():
            if self.first <= per <= today:
                y, m = int(per[:4]), int(per[5:7])
                yield Observation(dt.date(y, m, 1), SOURCE_ID, "FRC:rajkot-city-private-std1-8",
                                  "FRC-approved fee, Rajkot-city private schools, std 1-8 (matched panel, timing profile)", "E001", "RAJKOT",
                                  float(v), qty_base=1.0, base_unit="pc")
