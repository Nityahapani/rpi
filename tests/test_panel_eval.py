"""Panel replay harness: smoke tests on synthetic data + a strict reproduction test against the legacy script.

The reproduction test is the important one: `scripts/panel_nowcast_rules.py` computes the legacy summary
(data/official/panel_nowcast_summary.json) with its own copy of the rules, and rpi/panel_eval.py must reproduce those
numbers exactly - if it ever stops, the port has drifted and the deeper results (extra rules, tests, calibration)
are being computed on a different object than the documented one. The test runs the script afresh on copies of its
inputs instead of reading the committed JSON, which is only rewritten when someone reruns the script and can lag
its inputs (source plan, item weights).
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rpi.config import ROOT
from rpi import panel_eval


def test_index_errors_weighted_and_live_mode_zeroes_independent_lines():
    R = pd.DataFrame({
        "line": ["A", "A", "B", "B"],
        "op": [1, 1, 1, 1], "origin": pd.Period("2020-01", "M"), "tp": [2, 2, 2, 2], "h": [1, 1, 1, 1],
        "e_X": [0.10, 0.10, 0.02, 0.02], "ret": [0.01, 0.01, 0.03, 0.03]})
    meta = {"T": [pd.Period("2020-01", "M"), pd.Period("2020-02", "M")],
            "line_w": pd.Series({"A": 0.75, "B": 0.25}),
            "line_indep": pd.Series({"A": 1.0, "B": 0.0})}
    all_mode = panel_eval.index_errors(R, meta, mode="all", rules=("X",))
    live_mode = panel_eval.index_errors(R, meta, mode="live", rules=("X",))
    assert all_mode["X"].iloc[0] == pytest.approx(0.75 * 0.10 + 0.25 * 0.02)
    assert live_mode["X"].iloc[0] == pytest.approx(0.25 * 0.02)          # independent line A contributes no error
    assert live_mode["actual"].iloc[0] == pytest.approx(0.75 * 0.01 + 0.25 * 0.03)


def test_rmse_table_and_series_shapes():
    P = pd.period_range("2020-01", periods=6, freq="M")
    rows = []
    for i, p in enumerate(P):
        for h in (1, 2):
            rows.append({"line": "A", "op": i, "origin": p, "tp": i + h, "h": h, "e_X": 0.01 * (i + 1) * h, "ret": 0.0})
    R = pd.DataFrame(rows)
    meta = {"T": list(P), "line_w": pd.Series({"A": 1.0}), "line_indep": pd.Series({"A": 0.0})}
    e = panel_eval.index_errors(R, meta, rules=("X",))
    tab = panel_eval.rmse_table(e, rules=("X",))
    assert set(tab["X"]) == {"h1_test", "h1_all", "h2_test", "h2_all"}
    assert tab["X"]["h1_all"]["rmse_pp"] > 0


LEGACY_INPUTS = ("data/official/mospi_cpi2012_gujarat_urban_items.csv", "data/official/basket_to_cpi2012_map.csv",
                 "data/official/weights_item_detail.csv", "data/source_plan.csv")


@pytest.mark.skipif(__import__("os").environ.get("RPI_SLOW") is None,
                    reason="runs the legacy script (~35 s) and the full 2018-2025 replay (~50 s); set RPI_SLOW=1 to run")
def test_replay_reproduces_the_legacy_script_exactly(tmp_path, monkeypatch):
    import runpy
    import shutil
    # the script reads and writes paths relative to the working directory: give it copies of its inputs in tmp_path,
    # so the committed JSON is never overwritten by the test
    for rel in LEGACY_INPUTS:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(ROOT) / rel, tmp_path / rel)
    monkeypatch.chdir(tmp_path)
    runpy.run_path(str(Path(ROOT) / "scripts" / "panel_nowcast_rules.py"), run_name="__main__")
    legacy = json.loads((tmp_path / "data/official/panel_nowcast_summary.json").read_text())
    R, meta = panel_eval.build_rows(ROOT, first=pd.Period("2018-01"), horizons=(1, 2))
    R = R[R.origin <= pd.Period("2025-10", "M")]          # legacy capped origins at 2025-10
    errs = panel_eval.index_errors(R, meta, mode="all")
    differences = []
    for h in (1, 2):
        for win, sel in (("select", ~errs.test), ("test", errs.test)):
            sub = errs[sel & (errs.h == h)]
            key = f"h{h}_{win}_n{sub.op.nunique()}"
            if key not in legacy:
                differences.append((key, "origin count differs", sorted(legacy)))
                continue
            for rule in ("T12", "SEAS", "SEASC", "MR", "PANEL", "ENS"):
                mine = 100 * float(np.sqrt((sub[rule] ** 2).mean()))
                if abs(mine - legacy[key][rule]) > 0.005:
                    differences.append((key, rule, mine, legacy[key][rule]))
    assert not differences, f"replay drifted from scripts/panel_nowcast_rules.py: {differences}"


def test_new_rules_produce_finite_forecasts_on_the_real_panel():
    R, meta = panel_eval.build_rows(ROOT, first=pd.Period("2025-01"), horizons=(1, 2))
    for rule in panel_eval.RULES:
        f = R["f_" + rule]
        assert f.notna().all(), f"{rule} produced NaNs"
        assert np.isfinite(f.to_numpy()).all()
    errs = panel_eval.index_errors(R, meta)
    assert set(panel_eval.RULES) <= set(errs.columns)


def test_calibration_and_band_coverage_run_on_synthetic_errors():
    """calibration() must produce coverage/PIT for a rule with enough origins, and band_coverage must read the committed band."""
    rng = np.random.default_rng(0)
    P = pd.period_range("2015-01", periods=60, freq="M")
    # already-aggregated index errors, the shape calibration()/band_coverage() consume
    errs = pd.DataFrame({
        "op": list(range(len(P))),
        "h": 1,
        "origin": list(P),
        "test": [p >= pd.Period("2018-01", "M") for p in P],
        "SEASC": rng.normal(0, 0.004, len(P)),
        "T12": rng.normal(0, 0.006, len(P)),
        "RW": rng.normal(0, 0.008, len(P)),
        "actual": np.zeros(len(P)),
    })
    cal = panel_eval.calibration(errs, rules=("SEASC", "T12", "RW"))
    assert "SEASC" in cal and "h1" in cal["SEASC"]
    assert cal["SEASC"]["h1"]["alpha_0.1"]["coverage"] >= 0.0
    bc = panel_eval.band_coverage(ROOT, errs)
    assert "coverage_test_origins" in bc
