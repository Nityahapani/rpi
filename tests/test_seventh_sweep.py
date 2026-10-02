"""Seventh sweep: GEKS fix, CPI-IW centre table, benchmark, event checks, nowcast evaluation, NPPA register."""
import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from rpi.benchmark import compare, merge_centres
from rpi.collectors import labour_bureau as lb
from rpi.event_check import check_events
from rpi.index.geks import geks_rel
from rpi.nowcast_eval import backtest, band_for, log_vintages, score_vintages

ROOT = Path(__file__).resolve().parent.parent
FX = Path(__file__).parent / "fixtures"


def test_geks_ignores_leading_empty_periods_and_matches_chain():
    # 2 items; first 3 periods carry NO quotes (panel stretched by pre-base events), one item has a gap
    lp = np.full((8, 2), np.nan)
    lp[3:, 0] = np.log([100, 101, 103, 104, 106])
    lp[3:, 1] = np.log([50, 50, np.nan, 52, 53])
    rel, n = geks_rel(lp, window=13, min_matched=1)
    assert np.isnan(rel[:3]).all()
    assert np.isfinite(rel[3:]).all()
    # item 0 alone is complete: its chain equals GEKS exactly
    r0, _ = geks_rel(lp[:, :1], window=13, min_matched=1)
    assert abs(np.nansum(r0[4:]) - math.log(106 / 100)) < 1e-9      # rel[] are period-on-period log relatives


def test_parse_gujarat_popover_fixture():
    v = lb.parse_state_popover((FX / "labourbureau_gujarat_popover.html").read_text())
    assert v[("2026-08", "Rajkot")] == 146.2 and v[("2026-07", "Rajkot")] == 146.0
    assert {c for _, c in v} == {"Ahmedabad", "Bhavnagar", "Rajkot", "Surat", "Vadodara"}
    assert lb.parse_state_popover("<html>nothing</html>") == {}


def test_merge_centres_upserts_and_is_idempotent(tmp_path):
    (tmp_path / "data/official").mkdir(parents=True)
    vals = {("2026-07", "Rajkot"): 146.0, ("2026-08", "Rajkot"): 146.2}
    assert merge_centres(tmp_path, vals, "u", "2026-10-02") == 2
    assert merge_centres(tmp_path, vals, "u", "2026-10-03") == 0
    assert merge_centres(tmp_path, {("2026-08", "Rajkot"): 146.3}, "u", "2026-10-03") == 1     # a revision wins
    d = pd.read_csv(tmp_path / "data/official/cpi_iw_gujarat_centres.csv")
    assert len(d) == 2 and d.set_index("period").loc["2026-08", "value"] == 146.3


def test_repo_centre_csv_is_sane():
    d = pd.read_csv(ROOT / "data/official/cpi_iw_gujarat_centres.csv")
    assert set(d.centre) == {"Ahmedabad", "Bhavnagar", "Rajkot", "Surat", "Vadodara"}
    assert d.value.between(100, 250).all() and d.source_url.notna().all()
    assert not d.duplicated(["period", "centre"]).any()
    raj = d[d.centre == "Rajkot"].set_index("period").value
    assert raj["2026-08"] == 146.2 and raj["2025-08"] == 141.2


def test_benchmark_compare_reports_corr_and_yoy():
    rng = np.random.default_rng(1)
    per = [str(p) for p in pd.period_range("2025-05", "2026-08", freq="M")]
    walk = np.cumsum(rng.normal(0.3, 0.3, len(per))) / 100
    cpi = pd.Series(100 * np.exp(walk), index=per)
    rpi = cpi * 1.01 * np.exp(rng.normal(0, 0.001, len(per)))
    root = Path(ROOT)
    out = compare(root, rpi, cpi, "2026-08")        # uses the repo CPI-IW csv for Rajkot; rpi/gu are synthetic
    assert out["status"] == "ok" and out["yoy_pct_at"]["period"] == "2026-08"
    assert "gujarat_centres_yoy_pct" in out and "Rajkot" in out["gujarat_centres_yoy_pct"]


def test_event_checks_flag_muted_official_response():
    res = {e["item_id"]: e for e in check_events(ROOT)}
    assert {"F011", "F012", "M001"} <= set(res)
    assert all(res[i]["verdict"] == "official_muted" for i in ("F011", "F012", "M001"))
    assert res["M001"]["pass_through_ratio"] < res["F011"]["pass_through_ratio"] < 1
    assert res["F011"]["pre"] == "2025-08" and res["F011"]["post"] == "2025-10"      # event month is partial -> skipped


def test_backtest_prefers_own_trend_over_peer_fill_on_synthetic_panel():
    rng = np.random.default_rng(3)
    T, N = 24, 20
    drift = rng.normal(0.004, 0.006, N)          # persistent item-specific drift, as in real CPI
    lr = pd.DataFrame(drift + rng.normal(0, 0.003, (T, N)), index=[str(p) for p in pd.period_range("2025-01", periods=T, freq="M")],
                      columns=[f"I{i}" for i in range(N)])
    ww = pd.Series(1 / N, index=lr.columns)
    div = pd.Series(["1"] * 10 + ["2"] * 10, index=lr.columns)
    r = backtest(lr, ww, ["I0", "I1", "I10"], div)
    m = r["methods"]
    assert m["own_trend"]["h1"]["rmse_pp"] < m["zero_change"]["h1"]["rmse_pp"]
    assert m["own_trend_independents_exact"]["h1"]["rmse_pp"] <= m["own_trend"]["h1"]["rmse_pp"]
    assert r["band"]["h1_valid"] and r["band"]["h2_abs_log"] >= 0


def test_band_for_scales_and_requires_file(tmp_path):
    assert band_for(tmp_path, 1) is None
    (tmp_path / "data/official").mkdir(parents=True)
    (tmp_path / "data/official/nowcast_backtest.json").write_text(json.dumps({"band": {"h1_abs_log": 0.01, "h2_abs_log": 0.02}}))
    assert band_for(tmp_path, 1) == 0.01 and band_for(tmp_path, 2) == 0.02
    assert abs(band_for(tmp_path, 8) - 0.04) < 1e-12 and band_for(tmp_path, 0) is None


def test_vintage_log_idempotent_and_scores_after_official_release(tmp_path):
    (tmp_path / "data").mkdir()
    tot = pd.Series([107.6, 108.2, 108.7], index=pd.period_range("2026-08", periods=3, freq="M"))
    d1 = dt.date(2026, 10, 2)
    assert log_vintages(tmp_path, tot, "2026-08", "r1", d1) == 2
    assert log_vintages(tmp_path, tot, "2026-08", "r1", d1) == 2
    assert len(pd.read_csv(tmp_path / "data/nowcast_vintages.csv")) == 2           # same day -> replaced, not duplicated
    assert score_vintages(tmp_path, tot[:1])["n_scored"] == 0                     # Sep not yet realised
    real = pd.Series([107.6, 108.0], index=pd.period_range("2026-08", periods=2, freq="M"))
    sc = score_vintages(tmp_path, real)
    assert sc["n_scored"] == 1 and abs(sc["rows"][0]["error_pct"] - (108.2 / 108.0 - 1) * 100) < 1e-2


def test_m001_nppa_register_is_proxy_not_direct():
    ev = pd.read_csv(ROOT / "data/tariff_events.csv")
    m = ev[ev.item_id == "M001"].sort_values("effective_from")
    assert list(m.effective_from) == ["2025-01-01", "2025-04-01", "2025-09-22", "2026-04-01"]
    assert math.isclose(m.price.iloc[2], 0.966, abs_tol=1e-6) and math.isclose(m.price.iloc[3], 0.9765, abs_tol=1e-6)
    assert m.price.iloc[2] / m.price.iloc[1] - 1 < -0.06                            # GST cut shows as ~ -6.25%
    assert (m.status.isin(["verified", "derived"])).all()
