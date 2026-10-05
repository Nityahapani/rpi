import numpy as np
import pandas as pd
from rpi import pooled_checks as pc


def test_norm_state_aliases():
    assert pc.norm_state("The Dadra And Nagar Haveli And Daman And Diu") == "dnh and dd"
    assert pc.norm_state("Jammu And Kashmir") == pc.norm_state("Jammu & Kashmir")
    assert pc.norm_state("NCT of Delhi") == "delhi" and pc.norm_state("Gujarat") == "gujarat"


def test_changes_only_between_consecutive_months():
    p = pd.DataFrame({"key": ["a"] * 4, "month": ["2025-01", "2025-02", "2025-04", "2025-05"], "v": [100.0, 110.0, 121.0, 133.1]})
    c = pc.changes(p, "v")
    assert set(c.index) == {("a", "2025-02"), ("a", "2025-05")}
    assert abs(c[("a", "2025-02")] - np.log(1.1)) < 1e-12


def test_triad_recovers_known_reliabilities():
    rng = np.random.default_rng(0); n = 40000
    f = rng.normal(size=n)
    a, b, c = 1.0 * f + rng.normal(0, 0.3, n), 0.8 * f + rng.normal(0, 0.5, n), 0.5 * f + rng.normal(0, 0.8, n)
    t = pc.triad(a, b, c)
    assert abs(t["a"]["reliability"] - 1 / 1.09) < 0.02
    assert abs(t["b"]["reliability"] - 0.64 / 0.89) < 0.02
    assert abs(t["c"]["reliability"] - 0.25 / 0.89) < 0.03
    assert abs(t["a"]["loading"] / t["c"]["loading"] - 2.0) < 0.1


def test_triad_flags_unidentified_case():
    rng = np.random.default_rng(1)
    t = pc.triad(rng.normal(size=500), rng.normal(size=500), rng.normal(size=500))
    assert any(v["reliability"] is None for v in t.values())


def test_pooled_beta_recovered_and_gujarat_excluded():
    rng = np.random.default_rng(2); rows = []
    for s in ["a", "b", "c", "d", "e", "gujarat"]:
        for t in range(9):
            dw = rng.normal(0, 0.1)
            rows.append(dict(state=s, dw=dw, dw1=rng.normal(0, 0.1), do=(5.0 if s == "gujarat" else 0.5) * dw + rng.normal(0, 0.005)))
    df = pd.DataFrame(rows)
    b, lo, hi = pc.boot_beta(df, lag=False)
    assert abs(b[0] - 0.5) < 0.05                        # the wildly different Gujarat rows were not used
    r = pc.loso(df, lag=False)
    assert r["n_states"] == 5 and r["rmse_pool"] < r["rmse_b1"]


def test_dm_sign_and_conformal_coverage():
    rng = np.random.default_rng(3)
    good, bad = rng.normal(0, 0.3, 40), rng.normal(0, 1.0, 40)
    assert pc.dm_test(good, bad)["stat"] < 0
    cov = pc.loo_conformal_coverage(rng.normal(0, 1, 400))
    assert abs(cov["coverage"] - 0.9) < 0.05
