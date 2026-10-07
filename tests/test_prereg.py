import numpy as np
import pandas as pd
from rpi import prereg as P


def lv(vals, start="2026-01"):
    return pd.Series(vals, index=pd.period_range(start, periods=len(vals), freq="M").strftime("%Y-%m"))


def test_only_targets_after_the_last_official_month_are_logged_and_logging_is_idempotent_per_day(tmp_path):
    off = lv([100, 101, 102, 103])                         # official to 2026-04
    proxy = lv([50, 50.5, 51, 51.5, 52, 52.6])             # proxy to 2026-06
    n = P.log_predictions(tmp_path, {"X": (proxy, off, "src")}, today="2026-10-01")
    led = pd.read_csv(tmp_path / P.LEDGER)
    assert n == 2 and list(led.target_period) == ["2026-05", "2026-06"] and list(led.horizon) == [1, 2] and (led.base_period == "2026-04").all()
    assert abs(led.pred_pp[0] - 100 * np.log(52 / 51.5)) < 1e-3
    assert P.log_predictions(tmp_path, {"X": (proxy, off, "src")}, today="2026-10-01") == 0          # same day: no duplicate
    assert P.log_predictions(tmp_path, {"X": (proxy, off, "src")}, today="2026-10-02") == 2          # new snapshot day: appended, old rows untouched
    assert len(pd.read_csv(tmp_path / P.LEDGER)) == 4


def test_nothing_is_logged_when_the_proxy_has_no_value_in_the_base_month(tmp_path):
    assert P.log_predictions(tmp_path, {"X": (lv([50, 51], "2026-06"), lv([100, 101]), "s")}, today="2026-10-01") == 0


def test_scoring_uses_only_snapshots_made_before_the_official_value_was_first_seen(tmp_path):
    off0 = lv([100, 101, 102, 103])
    proxy = lv([50, 50.5, 51, 51.5, 52, 52.6])
    P.log_official_arrivals(tmp_path, {"X": off0}, today="2026-09-01")                 # bootstrap
    P.log_predictions(tmp_path, {"X": (proxy, off0, "s")}, today="2026-10-01")
    off1 = lv([100, 101, 102, 103, 104.5])                                              # official 2026-05 arrives
    assert P.log_official_arrivals(tmp_path, {"X": off1}, today="2026-10-15") == 1
    P.log_predictions(tmp_path, {"X": (proxy * 1.2 + 1, off1, "s")}, today="2026-10-20")  # made after arrival: must not be used for 2026-05
    sc = P.score(tmp_path, {"X": off1})
    assert len(sc) == 1 and sc.made_on[0] == "2026-10-01" and sc.target_period[0] == "2026-05"
    assert abs(sc.actual_pp[0] - 100 * np.log(104.5 / 103)) < 1e-3 and abs(sc.error_pp[0] - (sc.pred_pp[0] - sc.actual_pp[0])) < 1e-9


def test_bootstrap_sightings_are_never_scored(tmp_path):
    off = lv([100, 101, 102, 103, 104])
    P.log_official_arrivals(tmp_path, {"X": off}, today="2026-10-01")
    (tmp_path / "data/preregistered").mkdir(parents=True, exist_ok=True)
    pd.DataFrame([dict(made_on="2026-09-01", item_id="X", source="s", base_period="2026-04", target_period="2026-05", horizon=1, pred_pp=1.0)]).to_csv(tmp_path / P.LEDGER, index=False)
    assert P.score(tmp_path, {"X": off}).empty


def test_cusum_flags_persistent_bias_and_not_noise():
    assert not P.cusum([0.3, -0.8, 0.5, -0.2, 0.9, -0.6, 0.1, -0.4])["flag"]
    assert P.cusum([1.2, 1.5, 1.1, 1.8, 1.4])["flag"]
    assert P.cusum([-1.3, -1.6, -1.2, -1.9, -1.1])["flag"]


def test_scorecard_summarises_and_flags(tmp_path):
    sc = pd.DataFrame({"item_id": ["A"] * 5, "source": "s", "target_period": [f"2026-{m:02d}" for m in range(5, 10)], "error_pp": [1.0] * 5, "z": [1.5] * 5})
    card = P.scorecard(sc)
    assert card.n_scored[0] == 5 and bool(card.flag[0]) and card.mae_pp[0] == 1.0


def test_auto_demotion_is_off_by_default_and_reverts_the_plan_row_when_enabled(tmp_path):
    (tmp_path / "data").mkdir()
    pd.DataFrame([dict(item_id="X", primary_source="dmart_ahmedabad", **{"class": "independent"}, note="n"), dict(item_id="Y", primary_source="official_link", **{"class": "linked"}, note="m")]).to_csv(tmp_path / "data/source_plan.csv", index=False)
    assert P.apply_demotions(tmp_path, ["X"], enabled=False) == []
    assert pd.read_csv(tmp_path / "data/source_plan.csv").set_index("item_id").loc["X", "primary_source"] == "dmart_ahmedabad"
    assert P.apply_demotions(tmp_path, ["X", "Y"], enabled=True, today="2026-11-01") == ["X"]
    plan = pd.read_csv(tmp_path / "data/source_plan.csv").set_index("item_id")
    assert plan.loc["X", "primary_source"] == "official_link" and plan.loc["X", "class"] == "linked" and "DEMOTED 2026-11-01" in plan.loc["X", "note"]
    assert pd.read_csv(tmp_path / P.DEMOTIONS).was[0] == "dmart_ahmedabad"


def test_repo_setting_keeps_auto_demotion_off():
    import tomllib
    from pathlib import Path
    s = tomllib.loads((Path(__file__).resolve().parents[1] / "config/settings.toml").read_text())
    assert s["prereg"]["auto_demote"] is False
