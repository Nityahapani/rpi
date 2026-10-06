import json
import numpy as np
import pandas as pd
from pathlib import Path
from rpi import rentsignal as R
ROOT = Path(__file__).resolve().parents[1]


def test_housing_table_is_complete_and_half_yearly_steps_are_positive():
    df = R.load(ROOT)
    assert len(df) == 13 and df.ai_housing.is_monotonic_increasing and df.rajkot_housing.dropna().is_monotonic_increasing
    assert df.rajkot_housing.notna().sum() == 6 and df.loc["2026H2", "ai_housing"] == 143.0


def test_beta_is_rajkot_over_all_india_and_never_uses_the_official_rent_index():
    b = R.beta_rajkot(R.load(ROOT))
    assert 0.3 < b["beta"] < 0.4 and b["lo"] < b["beta"] < b["hi"] and b["n_steps"] == 5
    import inspect
    assert "official_rent" not in inspect.getsource(R.beta_rajkot) and "official_rent" not in inspect.getsource(R.monthly_signal)


def test_monthly_signal_is_a_run_rate_of_the_half_year_step():
    df = R.load(ROOT)
    s = R.monthly_signal(df, 0.5, first="2025-01", last="2025-12")
    st = R.steps(df)
    assert abs(np.log(s["2025-03"] / s["2025-02"]) - 0.5 * st["2025H1"] / 6) < 1e-9
    assert abs(np.log(s["2025-09"] / s["2025-08"]) - 0.5 * st["2025H2"] / 6) < 1e-9


def test_screen_records_a_failed_gate_and_the_signal_is_not_wired():
    r = json.loads((ROOT / "data/official/rent_signal_screen.json").read_text())
    v = r["variants"]["pre-registered (Rajkot-calibrated)"]
    assert v["verdict"] == "fail" and v["n_overlap"] == 20
    # the signal fails the (unchanged) correlation gate, so R001 may only be wired under the separately documented trend gate (see test_r001_is_wired_*)
    assert v["corr"] < 0.5


def test_tvp_filter_is_mospi_free_and_beats_constant_beta_on_the_labour_bureau_backtest():
    import inspect
    assert "official_rent" not in inspect.getsource(R.tvp_beta) and "official_rent" not in inspect.getsource(R.moSPI_free_backtest)
    t = R.tvp_beta(R.load(ROOT))
    assert 0.45 < t["beta"] < 0.65 and t["se_forward"] > t["se"]
    bt = R.moSPI_free_backtest(R.load(ROOT))
    rmse = lambda c: float(np.sqrt(((bt[c] - bt.actual_pct) ** 2).mean()))
    assert rmse("tvp_beta_pct") < rmse("constant_beta_pct") < rmse("all_india_pct")


def test_v2_fails_the_unchanged_gate_on_correlation_only():
    r = json.loads((ROOT / "data/official/rent_signal_screen.json").read_text())
    v2 = r["variants"]["v2 (chosen after v1 failed): time-varying beta, Kalman"]
    assert v2["verdict"] == "fail" and v2["corr"] < 0.5 and v2["drift"] <= 0.10


def test_panel_has_78_complete_centres_including_rajkot():
    p = R.load_panel(ROOT)
    assert len(p) == 78 and p[R.HALVES].notna().all().all() and "Rajkot" in set(p.centre)
    assert (p.loc[p.centre == "Rajkot", R.HALVES].values[0] == [109.9, 110.3, 110.5, 111.0, 112.0, 113.2]).all()


def test_panel_backtest_ranks_shrinkage_first_and_ratio_models_below_baseline():
    b = R.panel_backtest(ROOT).set_index("model")
    assert b.rmse_all_centres.idxmin() == "E4 additive, empirical-Bayes shrunk"
    assert b.loc["E1 constant ratio", "rmse_all_centres"] > b.loc["all-India step as is", "rmse_all_centres"]
    assert b.loc["all-India step as is", "abs_err_rajkot"] > 2 * b.loc["E4 additive, empirical-Bayes shrunk", "abs_err_rajkot"]


def test_ensemble_is_mospi_free_and_selection_rule_is_panel_only():
    import inspect
    for f in (R.ensemble_steps, R.ensemble_signal, R.panel_backtest, R._panel_steps):
        assert "official_rent" not in inspect.getsource(f)
    es = R.ensemble_steps(ROOT)
    assert es.attrs["params"]["selected"] == ["E4", "E5"]
    assert (es.model_sd_pct < 0.3).all() and es.ensemble_pct.between(0.5, 1.4).all()


def test_v3_fails_the_unchanged_correlation_gate_on_correlation_only():
    v = json.loads((ROOT / "data/official/rent_signal_screen.json").read_text())["v3"]["verdict"]
    for j in v.values():
        assert j["verdict"] == "fail" and j["corr"] < 0.5 and j["drift"] <= 0.10 and abs(j["yoy_signal_pct"] - j["yoy_official_pct"]) < 0.5


def test_gate_ceiling_even_the_officials_own_trend_cannot_reach_the_corr_gate():
    g = R.gate_ceiling(ROOT)
    assert g["n"] == 19 and g["corr_official_own_linear_trend_oracle"] < 0.5 and g["corr_interpolated"] < 0.5 and g["corr_staircase"] < 0.5
    assert g["official_sd_pct"] > 0.3 * g["official_mean_pct"] and g["official_lag1_autocorr"] < 0.3


def test_trend_gate_rejects_flat_and_all_india_and_v1_but_accepts_v2_and_v3():
    v = R.trend_gate_variants(ROOT)
    assert v["v3 panel-selected (E4+E5)"]["verdict"] == "pass" and v["v2 Kalman ratio"]["verdict"] == "pass"
    for k in ("flat (beta=0)", "v1 constant ratio", "all-India housing as is", "v3 all-five equal weight"):
        assert v[k]["verdict"] == "fail"


def test_existing_drift_cap_alone_would_pass_a_flat_signal_so_it_is_not_a_trend_gate():
    from rpi.proxy_check import judge, MAX_DRIFT
    df, o = R.load(ROOT), R.official_rent(ROOT)
    j = judge(R.monthly_signal(df, 0.0, first=o.index[0], last=o.index[-1]), o)
    assert j["drift"] <= MAX_DRIFT


def test_trend_gate_monte_carlo_size_and_power_match_the_analytic_values():
    rng = np.random.default_rng(7)
    s, n, z = 0.071, 19, R.Z_TREND
    oc = R.trend_gate_operating_characteristics(s, n)
    for e in (0.0, 1.0, 2.0):
        noise = rng.normal(0, s * np.sqrt(n), 200000)
        acc = float((np.abs(e + noise) <= z * s * np.sqrt(n)).mean())
        assert abs(acc - oc[f"{e:.1f}pp"]) < 0.01
    assert oc["0.0pp"] > 0.88 and oc["1.0pp"] < 0.08 and oc["2.0pp"] < 0.001


def test_r001_is_wired_as_a_modelled_trend_gated_source_and_every_registry_knows_it():
    from rpi.collectors.official_link import BACKFILL_SOURCES
    from rpi.index.engine import SINGLE_SERIES_SOURCES
    from rpi.proxy_check import GATED_SOURCES, MODELLED_SOURCES, PROXY_SOURCES
    plan = pd.read_csv(ROOT / "data/source_plan.csv", dtype=str, keep_default_na=False).set_index("item_id")
    assert plan.loc["R001", "primary_source"] == "rent_signal" and plan.loc["R001", "class"] == "independent"
    assert "MODELLED" in plan.loc["R001", "note"] and "TREND gate" in plan.loc["R001", "note"]
    assert "rent_signal" in BACKFILL_SOURCES and "rent_signal" in SINGLE_SERIES_SOURCES and "rent_signal" in GATED_SOURCES and "rent_signal" in MODELLED_SOURCES
    assert "rent_signal" not in PROXY_SOURCES          # a model is reported in its own bucket, never as an observed proxy
    g = R.trend_gate_variants(ROOT)["v3 panel-selected (E4+E5)"]
    assert g["verdict"] == "pass"                      # wiring is only valid while the gate passes


def test_collector_series_equals_the_screened_signal_and_never_extrapolates_beyond_the_last_housing_half():
    from rpi.collectors.rent_signal import RentSignalCollector, level_series
    s = level_series(ROOT, today="2030-01")
    assert s.index[0] == "2025-01" and s.index[-1] == "2026-12"
    o = R.official_rent(ROOT)
    a = R.ensemble_signal(ROOT, first=o.index[0], last=o.index[-1])
    b = s.reindex(o.index)
    assert abs(np.log(b.iloc[-1] / b.iloc[0]) - np.log(a.iloc[-1] / a.iloc[0])) < 1e-9
    obs = list(RentSignalCollector(ROOT).collect(None))
    assert obs and all(x.item_id == "R001" and x.source_id == "rent_signal" for x in obs)


def test_judge_trend_is_pending_when_short_and_agrees_with_the_trend_gate():
    o = R.official_rent(ROOT)
    sig = R.ensemble_signal(ROOT, first=o.index[0], last=o.index[-1])
    assert R.judge_trend(sig.iloc[:8], o)["verdict"] == "pending"
    j = R.judge_trend(sig, o)
    assert j["verdict"] == "pass" and j["corr"] is None and j["gate"] == "trend"
    assert R.judge_trend(sig * 0 + 100, o)["verdict"] == "fail"
