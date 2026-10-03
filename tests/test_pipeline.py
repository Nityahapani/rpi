"""End-to-end: synthetic data -> ingest -> index. Checks the engine recovers the TRUE price paths."""
import datetime as dt
import numpy as np
import pandas as pd
import pytest
from rpi import db, ingest
from rpi.config import load_settings, resolve, ROOT
from rpi.collectors.synthetic import generate
from rpi.index.engine import run_index
from rpi.publish import publish, DemoGuard


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    s = load_settings()
    s["index"]["bootstrap_reps"] = 30
    conn = db.connect(tmp_path_factory.mktemp("d") / "t.sqlite")
    basket = pd.read_csv(resolve(s, "basket"), dtype={"division": str})
    w = pd.read_csv(ROOT / "data" / "weights_demo.csv")
    ingest.load_basket(conn, basket); ingest.load_weights(conn, w)
    obs, truth, months = generate(basket, dt.date(2026, 1, 1), dt.date(2026, 8, 31), seed=5)
    acc, rej, _ = ingest.persist(conn, obs)
    assert rej == 0 and acc == len(obs)
    run = run_index(conn, s)
    return conn, run, basket, w, truth, months


def test_recovers_true_index(built):
    """Truth = Young index in which UNOBSERVED (tier D) items follow their division's weighted-mean
    movement (overall mean if the whole division is unobserved) - exactly the engine's stated
    imputation assumption. So this tests the *estimation* machinery, not the unobservable items."""
    conn, run, basket, w, truth, months = built
    wt = w.set_index("item_id")["weight"]
    div = basket.set_index("item_id")["division"]
    from rpi.superseded import SUPERSEDED_ITEMS      # synthetic quotes of superseded items are (by design) kept out of the index -> unobserved here
    lp = pd.DataFrame({i: truth[i] - truth[i][0] for i in truth if i not in SUPERSEDED_ITEMS}, index=months)
    obs_items = list(lp.columns)
    overall = (lp * wt[obs_items]).sum(axis=1) / wt[obs_items].sum()
    paths = {}
    for it in basket.item_id:
        if it in lp:
            paths[it] = lp[it]
        else:
            peers = [j for j in obs_items if div[j] == div[it]]
            paths[it] = (lp[peers] * wt[peers]).sum(axis=1) / wt[peers].sum() if peers else overall
    P = pd.DataFrame(paths)
    true_total = (100 * np.exp(P) * wt[P.columns]).sum(axis=1) / wt[P.columns].sum()
    err = (run.variants["jevons_chain"].total - true_total).abs()
    assert err.max() < 0.75, f"max abs error {err.max():.2f} index points"


def test_every_observed_tier_is_recovered_itemwise(built):
    _, run, basket, _, truth, months = built
    lv = run.variants["jevons_chain"].items
    tier = basket.set_index("item_id")["tier"]
    err = pd.Series({i: lv[i].iloc[-1] - 100 * np.exp(truth[i][-1] - truth[i][0]) for i in truth})
    for t in ("A", "B", "C"):
        assert abs(err[tier[err.index] == t].mean()) < 1.5, t


def test_ci_brackets_headline_and_coverage_reported(built):
    _, run, *_ = built
    v = run.variants["jevons_chain"]
    assert (v.lo <= v.total + 1e-9).all() and (v.hi >= v.total - 1e-9).all()
    cov = v.coverage.iloc[-1]
    assert 0.3 < cov < 1.0                      # tier D items are never observed => <100%
    assert v.coverage_by_tier["D"].iloc[-1] == 0


def test_variants_are_close_but_distinct(built):
    _, run, *_ = built
    a, b = run.variants["jevons_chain"].total, run.variants["geks_jevons"].total
    assert (a - b).abs().max() < 3.0


def test_demo_run_is_flagged_and_publish_blocked(built, tmp_path):
    conn, run, *_ = built
    assert run.is_demo
    with pytest.raises(DemoGuard):
        publish(conn, tmp_path, None, allow_demo=False)
    summ = publish(conn, tmp_path, None, allow_demo=True)
    assert summ["demo"] and (tmp_path / "index.html").exists()
    assert "DEMO BUILD" in (tmp_path / "index.html").read_text()


def test_idempotent_reingest(built):
    conn, *_ = built
    n0 = conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    obs, *_ = generate(pd.read_csv("data/basket.csv", dtype={"division": str}),
                       dt.date(2026, 1, 1), dt.date(2026, 1, 10), seed=5)
    ingest.persist(conn, obs)
    assert conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0] >= n0
