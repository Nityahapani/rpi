"""Tests for the official-data layer: weights back-out, mapping, tariff status gate, audits.
Fixtures are tiny and synthetic; a few integration checks read the committed real files."""
import datetime as dt
import numpy as np
import pandas as pd
import pytest
from rpi import audit
from rpi.config import ROOT
from rpi.collectors.tariff_events import load_usable_events, expand_events
from rpi.weights_build import fit_implied_weights, choose_lambda, build_item_weights, parse_annex_weights


# ---------------------------------------------------------------- ridge back-out
def _synthetic_indices(seed=0, n=20, k=5):
    rng = np.random.default_rng(seed)
    base = np.cumsum(rng.normal(0.3, 0.2, n))
    X = 100 + np.column_stack([base * rng.uniform(0.5, 1.5) + np.cumsum(rng.normal(0, 0.3, n)) for _ in range(k)])
    true = np.array([0.35, 0.25, 0.2, 0.12, 0.08])
    return X, X @ true, true


def test_fit_respects_constraints_and_recovers_when_identified():
    X, y, true = _synthetic_indices()
    w = fit_implied_weights(X, y, np.full(5, 0.2), lam=1e-6)
    assert abs(w.sum() - 1) < 1e-8 and (w >= -1e-9).all()
    assert np.abs(w - true).max() < 0.05


def test_ridge_prior_dominates_when_lambda_huge():
    X, y, _ = _synthetic_indices()
    prior = np.array([0.1, 0.1, 0.1, 0.1, 0.6])
    w = fit_implied_weights(X, y, prior, lam=1e6)
    assert np.abs(w - prior).max() < 0.01


def test_choose_lambda_returns_grid_member():
    X, y, _ = _synthetic_indices()
    lam, tab = choose_lambda(X, y, np.full(5, 0.2), grid=(1e-4, 1e-2))
    assert lam in (1e-4, 1e-2) and len(tab) == 2


# ---------------------------------------------------------------- item weights
def test_item_weights_sum_to_100_and_split_within_group():
    grp = {"01.1": ("Food", 6.0), "01.2": ("Bev", 2.0), "04.1": ("Rent", 4.0)}
    divw = pd.Series({"01": 0.6, "04": 0.4})
    mp = pd.DataFrame({"item_id": ["A", "B", "C"], "weight_group": ["01.1", "01.1", "04.1"],
                       "match_quality": ["exact"] * 3, "official_item_code": ["x"] * 3})
    bk = pd.DataFrame({"item_id": ["A", "B", "C"], "name": list("abc"), "tier": ["A", "A", "D"]})
    items, cov = build_item_weights(divw, grp, mp, bk)
    w = items.set_index("item_id")["weight"]
    assert abs(w.sum() - 100) < 1e-9
    assert abs(w["A"] - w["B"]) < 1e-12                                    # equal split inside a group
    # group 01.1 holds 6/8 of division 01 (0.6) = 0.45 ; rent group = 0.4 ; covered total = 0.85
    assert abs(w["C"] / w.sum() - 0.4 / 0.85) < 1e-9
    assert abs(cov.attrs["total_coverage"] - 0.85) < 1e-9                  # 01.2 uncovered
    assert abs(cov.loc["01", "coverage_ratio"] - 0.75) < 1e-9


def test_unmapped_group_is_an_error():
    mp = pd.DataFrame({"item_id": ["A"], "weight_group": ["99.9"], "match_quality": ["exact"], "official_item_code": ["x"]})
    with pytest.raises(ValueError):
        build_item_weights(pd.Series({"01": 1.0}), {"01.1": ("F", 1.0)}, mp,
                           pd.DataFrame({"item_id": ["A"], "name": ["a"], "tier": ["A"]}))


# ---------------------------------------------------------------- tariff status gate
def test_status_gate_blocks_rejected_and_unverified(tmp_path):
    p = tmp_path / "ev.csv"
    pd.DataFrame({"item_id": ["T001"] * 4, "effective_from": ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"],
                  "price": [100, 110, 115.01, 130], "status": ["verified", "derived", "rejected", "unverified"]}).to_csv(p, index=False)
    ev = load_usable_events(p)
    assert list(ev["price"]) == [100, 110]
    obs = expand_events(ev, dt.date(2026, 4, 30))
    assert max(o.price for o in obs) == 110                                # 115.01 / 130 never reach the index


def test_status_column_is_mandatory(tmp_path):
    p = tmp_path / "ev.csv"
    pd.DataFrame({"item_id": ["T001"], "effective_from": ["2026-01-01"], "price": [100]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="status"):
        load_usable_events(p)


def test_unknown_status_rejected(tmp_path):
    p = tmp_path / "ev.csv"
    pd.DataFrame({"item_id": ["T001"], "effective_from": ["2026-01-01"], "price": [100], "status": ["probably"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="unknown status"):
        load_usable_events(p)


# ---------------------------------------------------------------- audit maths
def test_compare_item_perfect_match():
    o = pd.Series([100, 100, 105, 105, 110.0], index=["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"])
    r = audit.compare_item(o * 3, o)
    assert r["timing_f1"] == 1.0 and abs(r["cum_gap_pp"]) < 1e-9 and r["corr_mom"] == 1.0


def test_compare_item_detects_missed_move():
    idx = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]
    mine = pd.Series([100, 100, 100, 100, 110.0], index=idx)
    off = pd.Series([100, 100, 105, 105, 110.0], index=idx)
    r = audit.compare_item(mine, off)
    assert r["timing_f1"] < 1.0


def test_blend_share_plausibility():
    idx = ["2026-01", "2026-02", "2026-03"]
    mine = pd.Series([100, 100, 110.0], index=idx)
    off = pd.Series([100, 100, 105.0], index=idx)                           # official moved half as much
    t = audit.blend_share(mine, off)
    assert abs(t["implied_share"].iloc[0] - 0.5) < 1e-9 and bool(t["plausible"].iloc[0])
    bad = audit.blend_share(mine, pd.Series([100, 100, 125.0], index=idx))  # official moved MORE than the part -> implausible
    assert not bool(bad["plausible"].iloc[0])


# ---------------------------------------------------------------- integration on committed real files
REAL = ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv"


@pytest.mark.skipif(not REAL.exists(), reason="official data not pulled")
def test_real_weights_file_is_complete_and_labelled():
    w = pd.read_csv(ROOT / "data/weights_cpi2024_gujarat_urban.csv")
    b = pd.read_csv(ROOT / "data/basket.csv")
    assert set(w.item_id) == set(b.item_id) and w.weight.notna().all()
    assert abs(w.weight.sum() - 100) < 0.01
    assert w.weight_source.iloc[0].startswith("APPROX")                    # never presented as official


@pytest.mark.skipif(not REAL.exists(), reason="official data not pulled")
def test_real_basket_tracks_official_general_index():
    off = audit.load_official(REAL)
    iw = pd.read_csv(ROOT / "data/official/weights_item_detail.csv")
    mp = pd.read_csv(ROOT / "data/basket_official_map.csv", dtype=str, keep_default_na=False)
    _, st = audit.basket_replication(off, iw, mp)
    assert st["rmse"] < 0.8 and st["max_abs_error"] < 1.5                   # regression guard on basket/weights quality
    assert st["weight_share_with_official_index_pct"] > 95


@pytest.mark.skipif(not REAL.exists(), reason="official data not pulled")
def test_real_events_fuel_matches_official_cumulative_change():
    off = audit.load_official(REAL)
    items = audit.official_item_matrix(off)
    mp = pd.read_csv(ROOT / "data/basket_official_map.csv", dtype=str, keep_default_na=False).set_index("item_id")
    obs = pd.DataFrame([vars(o) for o in expand_events(load_usable_events(ROOT / "data/tariff_events.csv"), dt.date(2026, 8, 31))])
    for it in ("T001", "T002"):
        r = audit.compare_item(audit.monthly_mean_series(obs[obs.item_id == it]), items[mp.loc[it, "official_item_code"]])
        assert abs(r["cum_gap_pp"]) < 1.0 and r["corr_mom"] > 0.95, (it, r)


def test_rejected_petrol_claim_is_never_used():
    ev = load_usable_events(ROOT / "data/tariff_events.csv")
    liquid = ev[ev.item_id.isin(["T001", "T002"])]
    assert (liquid["price"] > 110).sum() == 0                              # the 115.01 / 100.10 claims stay out


def test_official_series_file_has_labour_bureau_and_mospi():
    s = pd.read_csv(ROOT / "data/official/official_series.csv")
    assert {"CPIIW_RAJKOT", "CPI2024_GUJARAT_URBAN_GENERAL"} <= set(s.series_id)
    assert s.source_url.notna().all()


def test_publish_refuses_partial_basket(tmp_path):
    """Real (non-demo) weights + only 3 items observed -> CoverageGuard, never a published 'index'."""
    from rpi import db, ingest
    from rpi.collectors.base import Observation
    from rpi.config import load_settings, resolve
    from rpi.index.engine import run_index
    from rpi.publish import publish, CoverageGuard
    s = load_settings(); s["index"]["bootstrap_reps"] = 10; s["project"]["base_period"] = "2026-01"
    conn = db.connect(tmp_path / "p.sqlite")
    ingest.load_basket(conn, pd.read_csv(ROOT / "data/basket.csv", dtype={"division": str}))
    ingest.load_weights(conn, pd.read_csv(ROOT / "data/weights_cpi2024_gujarat_urban.csv"))
    obs = [Observation(dt.date(2026, m, 1), "tariff", it, it, it, "RJT", p * (1 + 0.01 * m))
           for it, p in [("T001", 95.0), ("T002", 90.0), ("R003", 858.0)] for m in range(1, 7)]
    ingest.persist(conn, obs)
    run_index(conn, s)
    with pytest.raises(CoverageGuard):
        publish(conn, tmp_path / "out")
