import numpy as np
from rpi.index.elementary import rel_from_lp
from rpi.index.geks import geks_rel

def test_jevons_geometric_mean():
    # two quotes: +10% and +40% -> geometric mean relative = sqrt(1.1*1.4)
    lp = np.log(np.array([[100, 50], [110, 70]], float))
    rel, n = rel_from_lp(lp)
    assert n.tolist() == [2, 2]
    assert abs(np.exp(rel[1]) - np.sqrt(1.1 * 1.4)) < 1e-12

def test_matched_only_ignores_new_quote_level():
    # quote B appears in month 2 at a very different level: must not affect the relative
    lp = np.log(np.array([[100, np.nan, 200], [110, 1000, 220], [121, 1100, np.nan]], float))
    rel, n = rel_from_lp(lp)
    assert abs(np.exp(rel[1]) - 1.10) < 1e-12 and n[1] == 2
    assert abs(np.exp(rel[2]) - 1.10) < 1e-12 and n[2] == 2

def test_too_few_matches_gives_nan():
    lp = np.log(np.array([[100, np.nan], [110, 50]], float))
    rel, n = rel_from_lp(lp, min_matched=2)
    assert np.isnan(rel[1])

def test_clip_limits_outliers():
    lp = np.log(np.array([[100, 100], [100, 1000]], float))
    rel, _ = rel_from_lp(lp, clip=0.7)
    assert abs(rel[1] - 0.35) < 1e-12        # (0 + 0.7)/2

def test_geks_equals_chain_on_complete_panel():
    rng = np.random.default_rng(0)
    lp = np.cumsum(rng.normal(0.01, 0.03, (8, 5)), axis=0) + rng.normal(0, 1, 5)
    r1, _ = rel_from_lp(lp, clip=10)
    r2, _ = geks_rel(lp, window=13)
    assert np.allclose(np.cumsum(r1), np.cumsum(r2), atol=1e-10)

def test_geks_rolling_window_splice_complete_panel():
    rng = np.random.default_rng(1)
    lp = np.cumsum(rng.normal(0.01, 0.03, (10, 4)), axis=0)
    r1, _ = rel_from_lp(lp, clip=10)
    r2, _ = geks_rel(lp, window=4)
    assert np.allclose(np.cumsum(r1), np.cumsum(r2), atol=1e-10)
