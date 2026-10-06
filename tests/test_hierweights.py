import numpy as np, pandas as pd, pytest
from pathlib import Path
from rpi import hierweights as H, audit

ROOT = Path(__file__).resolve().parents[1]


def _toy_official(true_shares, T=20, seed=1):
    rng = np.random.default_rng(seed)
    k = len(true_shares)
    X = 100 * np.exp(np.cumsum(rng.normal(0.004, 0.01, (T, k)), axis=0))
    y = X @ np.asarray(true_shares)
    return X, y


def test_fit_shares_recovers_exact_aggregation():
    true = np.array([0.5, 0.3, 0.15, 0.05])
    X, y = _toy_official(true)
    s = H.fit_shares(X, y, np.ones(4) / 4, 1e-8)
    assert np.allclose(s, true, atol=5e-3) and abs(s.sum() - 1) < 1e-9


def test_cv_prefers_small_lambda_when_identified():
    true = np.array([0.6, 0.4])
    X, y = _toy_official(true)
    lam, rm = H.cv_lambda(X, y, np.ones(2) / 2)
    assert rm < 1e-2


def _tree():
    rows = [("division", "01", "GEN", .6), ("division", "02", "GEN", .4),
            ("group", "01.1", "01", .75), ("group", "01.2", "01", .25),
            ("group", "02.1", "02", 1.0),
            ("class", "01.1.1", "01.1", 1.0), ("class", "01.2.1", "01.2", 1.0), ("class", "02.1.1", "02.1", 1.0)]
    return pd.DataFrame(rows, columns=["level", "code", "parent", "share"])


def test_basket_weights_hand_off_unmapped_branches_pro_rata():
    t = _tree()
    w = H.basket_weights(t, {"A": "01.1.1", "B": "01.2.1"})       # division 02 has no item -> its weight goes to division 01
    assert abs(w.sum() - 100) < 1e-9
    assert abs(w["A"] - 75) < 1e-9 and abs(w["B"] - 25) < 1e-9     # ancestor split 0.75 : 0.25 is kept
    w2 = H.basket_weights(t, {"A": "01.1.1", "B": "01.2.1", "C": "02.1.1"})
    assert abs(w2["C"] - 40) < 1e-9 and abs(w2["A"] - 45) < 1e-9


def test_basket_items_sharing_a_node_split_its_weight():
    w = H.basket_weights(_tree(), {"A": "01.1.1", "A2": "01.1.1", "C": "02.1.1"})
    assert abs(w["A"] - w["A2"]) < 1e-12 and abs(w["A"] + w["A2"] - 60) < 1e-9


REAL = ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv"


@pytest.mark.skipif(not REAL.exists(), reason="official data not pulled")
def test_real_weights_reproduce_official_general_better_than_equal_split():
    off = audit.load_official(REAL)
    mp = pd.read_csv(ROOT / "data/basket_official_map.csv", dtype=str, keep_default_na=False)
    iw = pd.read_csv(ROOT / "data/official/weights_item_detail.csv")
    _, new = audit.basket_replication(off, iw, mp)
    _, old = audit.basket_replication(off, iw.assign(weight=iw["weight_equal_split_old"]), mp)
    assert new["rmse"] < 0.3 and new["rmse"] < old["rmse"]


@pytest.mark.skipif(not REAL.exists(), reason="official data not pulled")
def test_real_tree_reproduces_parent_indices_to_rounding():
    tree = pd.read_csv(ROOT / "data/official/hier_weights_tree.csv", dtype={"code": str, "parent": str})
    nt = tree[tree.cv_rmse.notna() & (tree.cv_rmse > 0)].drop_duplicates("parent")
    assert (nt.cv_rmse < 0.05).mean() > 0.97                       # blocked-CV error at the 0.01 rounding scale for >97% of nodes
