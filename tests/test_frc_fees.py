import numpy as np, pandas as pd
from pathlib import Path
from rpi import frc_fees as F
from rpi.proxy_check import judge
ROOT = Path(__file__).resolve().parents[1]


def _fees():
    rows = []
    for s in range(30):
        for std in "12345678":
            for ay, f in (("2022-23", 1000), ("2023-24", 1100), ("2024-25", 1210)):
                rows.append(("R", s, "x", "b", "E", std, ay, f * (1 + 0.001 * s)))
    return pd.DataFrame(rows, columns=["district", "school_id", "school", "board", "medium", "standard", "ay", "fee"])


def test_matched_panel_change_and_exclusions():
    d = _fees()
    d.loc[(d.school_id == 0) & (d.ay == "2024-25"), "fee"] = 0          # a school with no fee in AY t drops out
    d = pd.concat([d, d.assign(standard="9", fee=5000)])                 # std 9 is outside the pre-specified range
    ch = F.ay_changes(d)
    assert list(ch.year) == [2023, 2024] and ch.n.tolist() == [240, 232]
    assert abs(ch.dlog.iloc[0] - np.log(1.1)) < 1e-9


def test_profile_sums_to_one_and_level_matches_annual_change():
    items = pd.read_csv(ROOT / "data/official/mospi_cpi2012_gujarat_urban_items.csv")
    prof = F.month_profile(items)
    assert abs(prof.sum() - 1) < 1e-9 and (prof >= 0).all()
    ch = pd.DataFrame({"year": [2023], "dlog": [0.05], "n": [100], "ay": ["2023-24"]})
    lv = F.monthly_level(ch, prof, start="2022-12", end="2024-01")
    assert abs(np.log(lv["2023-12"] / lv["2022-12"]) - 0.05) < 1e-9


def test_published_series_passes_the_unchanged_gate_on_real_data():
    from rpi.collectors.frc_fees import level_series
    lv = level_series(ROOT)
    it = pd.read_csv(ROOT / "data/official/mospi_cpi2012_gujarat_urban_items.csv")
    y = it[it.item == F.CPI2012_LINE].set_index("period").index_value
    j = judge(lv.loc["2021-12":"2025-12"], y.loc["2021-12":"2025-12"])
    assert j["verdict"] == "pass" and j["n_overlap"] >= 40
