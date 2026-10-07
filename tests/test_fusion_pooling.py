import numpy as np, pandas as pd
from rpi import fusion as F, pooling as P


def _panel(seed=0, n_states=8, months=12, b=0.7):
    rng = np.random.default_rng(seed)
    t = [str(p) for p in pd.period_range("2025-01", periods=months, freq="M")]
    dn = rng.normal(0, 0.03, months)
    rows = [dict(item="X", state=f"s{k}", t=t[j], dn=dn[j], **{"do": b * dn[j] + rng.normal(0, 0.005)}) for k in range(n_states) for j in range(months)]
    return pd.DataFrame(rows)


def test_slope_recovers_beta_and_handles_short():
    x = np.array([1., 2, 3, 4]); assert abs(P.slope(x, 2 * x)[0] - 2) < 1e-12
    assert not np.isfinite(P.slope(x[:2], x[:2])[0])


def test_shrink_between_own_and_pool_and_falls_back():
    assert abs(P.shrink((1.0, 0.0, 0.0), 0.0, 1.0) - 1.0) < 1e-12          # exact own -> own
    assert abs(P.shrink((1.0, 1e3, 0.0), 0.5, 1e-4) - 0.5) < 1e-3          # hopelessly noisy own -> pool
    assert P.shrink((np.nan, np.inf, np.nan), 0.4, 0.1) == 0.4


def test_prediction_uses_only_past_months():
    df = _panel(); a = P.predict_state(df, "s0", "2025-09")
    df2 = df.copy(); df2.loc[df2.t >= "2025-09", "do"] += 5.0               # corrupt the target month and later: coefficients must not move
    b = P.predict_state(df2, "s0", "2025-09")
    assert abs(a["b_pool"] - b["b_pool"]) < 1e-12 and abs(a["PP"] - b["PP"]) < 1e-12
    assert abs(a["b_pool"] - 0.7) < 0.1


def test_loso_excludes_own_state_from_pool():
    df = _panel(); df.loc[df.state == "s0", "do"] = 9.0                     # a wild state must not leak into its own pooled slope
    r = P.loso_lfo(df, "X", "2025-09"); assert abs(r[r.state == "s0"].b_pool.mean() - 0.7) < 0.1


def test_fuse_precision_weighting():
    f, v = F.fuse(0.0, 1.0, 1.0, 1.0); assert abs(f - 0.5) < 1e-12 and abs(v - 0.5) < 1e-12
    f, v = F.fuse(0.0, 1.0, 1.0, 1e-6); assert f > 0.999


def test_calibrate_no_pairs_returns_priors():
    s = pd.Series([0.01, 0.02], index=["2025-01", "2025-02"])
    b, s2, n = F.calibrate(s, s, "2025-02", 0.8, 0.0004); assert (b, s2, n) == (0.8, 0.0004, 1)


def test_calibrate_shrinks_with_n():
    idx = [str(p) for p in pd.period_range("2025-01", periods=40, freq="M")]
    p = pd.Series(np.linspace(0.01, 0.04, 40) * np.tile([1, -1], 20), index=idx); o = 0.5 * p
    b_small = F.calibrate(p, o, idx[4], 1.0, 1e-4)[0]; b_big = F.calibrate(p, o, idx[39], 1.0, 1e-4)[0]
    assert 0.5 < b_big < b_small < 1.0


def test_item_estimates_ignore_future_pairs():
    idx = [str(p) for p in pd.period_range("2025-01", periods=12, freq="M")]
    p = pd.Series(np.random.default_rng(1).normal(0, .02, 12), index=idx); o = 0.6 * p
    tabs = {"A": (0.0, np.zeros(12))}; args = dict(cls={"A": "gated"}, tables=tabs, sp={"A": 0.02})
    a = F.item_estimates("2025-09", dP={"A": p}, dO={"A": o}, **args)
    o2 = o.copy(); o2["2025-10":] = 9.0
    b = F.item_estimates("2025-09", dP={"A": p}, dO={"A": o2}, **args)
    assert a["A"]["fused"] == b["A"]["fused"] and a["A"]["var_fused"] < a["A"]["var_prior"]


def test_prior_only_and_direct_items():
    idx = [str(p) for p in pd.period_range("2025-01", periods=8, freq="M")]
    p = pd.Series(0.01, index=idx)
    e = F.item_estimates("2025-08", {"A": "prior", "B": "direct"}, {"B": p}, {"B": p}, {"A": (0.003, np.zeros(12))}, {})
    assert e["A"]["fused"] == 0.003 and abs(e["B"]["fused"] - 0.01) < 1e-12


def test_tables_do_not_leak_past_cutoff():
    per = [str(p) for p in pd.period_range("2012-01", "2025-12", freq="M")]
    rng = np.random.default_rng(3)
    lv = 100 * np.exp(np.cumsum(rng.normal(0.005, 0.02, len(per))))
    d = pd.DataFrame(dict(item="Tomato", period=per, index_value=lv))
    m = pd.DataFrame(dict(item_id=["F023"], cpi2012_item=["Tomato"]))
    a = F.build_tables(d, m, "2024-12")
    d2 = d.copy(); d2.loc[d2.period > "2024-12", "index_value"] *= 7
    b = F.build_tables(d2, m, "2024-12")
    assert a["F023"][0] == b["F023"][0] and np.allclose(a["F023"][1], b["F023"][1])
