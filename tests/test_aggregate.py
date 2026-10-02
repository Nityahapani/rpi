import numpy as np
import pandas as pd
from rpi.index.aggregate import aggregate

def _items():
    return pd.DataFrame({"item_id": ["a", "b", "c"], "division": ["01", "01", "04"], "tier": ["A", "A", "D"]})

def test_young_weighted_average_and_imputation():
    P = pd.period_range("2026-01", periods=3, freq="M")
    rel = pd.DataFrame({"a": [0, np.log(1.1), np.log(1.1)], "b": [0, np.log(1.3), np.log(1.0)],
                        "c": [0, np.nan, np.nan]}, index=P)
    n = pd.DataFrame({"a": [3, 3, 3], "b": [3, 3, 3], "c": [0, 0, 0]}, index=P)
    w = pd.Series({"a": 20.0, "b": 20.0, "c": 60.0})
    out = aggregate(rel, n, _items(), w)
    # month 2: c imputed with overall observed weighted mean log-rel (division 04 has no observed item)
    m = (20 * np.log(1.1) + 20 * np.log(1.3)) / 40
    lvl_a, lvl_b, lvl_c = 110.0, 130.0, 100 * np.exp(m)
    expected = (20 * lvl_a + 20 * lvl_b + 60 * lvl_c) / 100
    assert abs(out["total"].iloc[1] - expected) < 1e-9
    assert abs(out["total"].iloc[0] - 100) < 1e-9
    assert abs(out["coverage"].iloc[1] - 0.4) < 1e-12       # only a,b observed (40% of weight)
    assert out["imputed"]["c"].iloc[1]

def test_division_index():
    P = pd.period_range("2026-01", periods=2, freq="M")
    rel = pd.DataFrame({"a": [0, np.log(1.2)], "b": [0, np.log(1.0)], "c": [0, np.log(1.5)]}, index=P)
    n = pd.DataFrame(5, index=P, columns=rel.columns)
    out = aggregate(rel, n, _items(), pd.Series({"a": 1.0, "b": 1.0, "c": 2.0}))
    assert abs(out["divisions"]["01"].iloc[1] - 110.0) < 1e-9
    assert abs(out["divisions"]["04"].iloc[1] - 150.0) < 1e-9


def test_own_trend_imputation_does_not_smear_a_peer_step():
    """A one-off administered step in item b must not move item c's imputed relative; c carries its own trend."""
    import numpy as np
    import pandas as pd
    from rpi.index.aggregate import aggregate
    idx = pd.period_range("2026-01", periods=6, freq="M")
    items = pd.DataFrame({"item_id": ["b", "c"], "division": ["04", "04"], "tier": ["A", "A"]})
    rel = pd.DataFrame({"b": [0, .001, .001, .001, .001, .08], "c": [0, .002, .002, .002, np.nan, np.nan]}, index=idx)
    n = pd.DataFrame({"b": [2] * 6, "c": [2, 2, 2, 2, 0, 0]}, index=idx)
    w = pd.Series({"b": 1.0, "c": 3.0})
    div = aggregate(rel, n, items, w, impute="division")
    own = aggregate(rel, n, items, w, impute="own_trend")
    assert abs(div["items"]["c"].iloc[5] / div["items"]["c"].iloc[3] - 1) > 0.05      # smeared (old behaviour)
    assert abs(own["items"]["c"].iloc[5] / own["items"]["c"].iloc[3] - np.exp(0.004)) < 1e-9   # own mean trend (0.002/month) x2 months
    assert own["imputed"]["c"].iloc[5] and not own["imputed"]["b"].iloc[5]
