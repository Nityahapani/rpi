import pandas as pd
from pathlib import Path
from rpi import costpush as C
ROOT = Path(__file__).resolve().parents[1]


def test_spec_shares_sum_to_one_and_inputs_are_independent_of_mospi():
    for it, s in C.SPEC.items():
        assert abs(sum(v[0] for v in s.values()) - 1) < 1e-9
        assert all(v[2] in ("doca_national", "doca_rajkot", "doca_gujarat", "tariff", "cpi_iw_rajkot") for v in s.values())     # never official_link


def test_partial_adjustment_closes_a_share_of_the_gap():
    import numpy as np
    class Conn: pass
    # one-input toy: a 10% cost shock moves the price by LAMBDA of the gap in month 1
    import rpi.costpush as m
    orig = m.input_level
    m.input_level = lambda conn, i, s: pd.Series({"2025-01": 1.0, "2025-02": 1.10})
    try:
        p = m.model(None, ROOT, "D003", ["2025-01", "2025-02"], spec={"x": (1.0, "F008", "doca_national")})
    finally:
        m.input_level = orig
    assert abs(np.log(p["2025-02"] / 100) - m.LAMBDA * np.log(1.10)) < 1e-9


def test_screen_file_records_the_gate_outcome_and_nothing_is_counted_unless_it_passes():
    d = pd.read_csv(ROOT / "data/official/costpush_screen.csv")
    pre = d[d.spec == "pre-registered"]
    assert set(pre.item_id) == {"D001", "D003"}
    assert (pre.counted == pre.verdict.map(lambda v: "YES" if v == "pass" else "no")).all()
    plan = pd.read_csv(ROOT / "data/source_plan.csv").set_index("item_id")
    for r in pre.itertuples():
        assert (plan.loc[r.item_id, "primary_source"] == "costpush_model") == (r.verdict == "pass")
