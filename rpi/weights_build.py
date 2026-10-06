"""Build Gujarat-urban basket weights from OFFICIAL MoSPI CPI-2024 information.

What is official and what is estimated (be honest about it - this goes in the output file):

  OFFICIAL  all-India URBAN division and group weights (Expert-Group report, Annexure 5.3a/5.3b)
  OFFICIAL  Gujarat-urban division/general index series (MoSPI eSankhyiki API)
  ESTIMATED Gujarat-urban DIVISION weights: MoSPI does not publish them, so they are backed out from
            the official division indices (General = sum_d w_d * I_d) with a ridge penalty pulling the
            solution toward the all-India urban weights. Lambda is chosen by hold-out RMSE.
            (12 division series over ~20 months are nearly collinear - an unpenalised fit is unstable.)
  APPROX    group weight within a division = all-India urban group share (Gujarat group shares unknown)
  ESTIMATED item weights: recovered node by node from the published official index tree (rpi/hierweights.py); the legacy equal split
            is kept in the column weight_equal_split_old for comparison
  NOT COVERED  groups with no basket item. Weights are renormalised over covered groups; coverage is reported.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize


# ----------------------------------------------------------------------------- parsing the annexure
def parse_annex_weights(annex: dict) -> tuple[dict[str, float], dict[str, tuple[str, float]]]:
    """Return (division->urban weight, group->(name, urban weight)) from the extracted annexure text."""
    div_w: dict[str, float] = {}
    for line in annex["114"].split("\n"):
        m = re.match(r"^(\d\d)\s+(.+?)\s+([\d.]{8,})\s+([\d.]{8,})\s+([\d.]{8,})$", line)
        if m:
            div_w[m.group(1)] = float(m.group(4))
    grp_w: dict[str, tuple[str, float]] = {}
    for pg in ("115", "116"):
        for line in annex[pg].split("\n"):
            m = re.match(r"^(\d\d\.\d)\s+(.+?)\s+([\d.]{8,})\s+([\d.]{8,})\s+([\d.]{8,})$", line)
            if m:
                grp_w[m.group(1)] = (m.group(2), float(m.group(4)))
    return div_w, grp_w


# ----------------------------------------------------------------------------- the ridge back-out
def fit_implied_weights(X: np.ndarray, y: np.ndarray, prior: np.ndarray, lam: float) -> np.ndarray:
    """min ||X w - y||^2 + lam * n * ||w - prior||^2   s.t. w >= 0, sum w = 1."""
    n = len(y)

    def obj(w):
        return float(np.sum((X @ w - y) ** 2) + lam * n * np.sum((w - prior) ** 2))

    res = minimize(obj, prior, method="SLSQP", bounds=[(0, 1)] * len(prior),
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-14})
    return res.x


def holdout_rmse(X, y, prior, lam, holdout: int = 6) -> tuple[float, float]:
    w = fit_implied_weights(X[:-holdout], y[:-holdout], prior, lam)
    tr = float(np.sqrt(np.mean((X[:-holdout] @ w - y[:-holdout]) ** 2)))
    ho = float(np.sqrt(np.mean((X[-holdout:] @ w - y[-holdout:]) ** 2)))
    return tr, ho


def choose_lambda(X, y, prior, grid=(1e-4, 1e-3, 1e-2), holdout: int = 6) -> tuple[float, pd.DataFrame]:
    rows = []
    for lam in grid:
        tr, ho = holdout_rmse(X, y, prior, lam, holdout)
        rows.append({"lambda": lam, "train_rmse": tr, "holdout_rmse": ho})
    tab = pd.DataFrame(rows)
    return float(tab.loc[tab["holdout_rmse"].idxmin(), "lambda"]), tab


def implied_gujarat_division_weights(official: pd.DataFrame, div_prior: dict[str, float],
                                     grid=(1e-4, 1e-3, 1e-2)):
    gen = official[official.level == "general"].set_index("period")["index_value"]
    dv = (official[official.level == "division"]
          .pivot_table(index="period", columns="code", values="index_value", aggfunc="first").sort_index(axis=1))
    prior = np.array([div_prior[c] for c in dv.columns], float)
    prior = prior / prior.sum()
    X, y = dv.values, gen.reindex(dv.index).values
    lam, tab = choose_lambda(X, y, prior, grid)
    w = fit_implied_weights(X, y, prior, lam)
    # sanity benchmark: raw all-India weights on the same hold-out
    ai_ho = float(np.sqrt(np.mean((X[-6:] @ prior - y[-6:]) ** 2)))
    out = pd.DataFrame({"all_india_urban": prior, "gujarat_urban_implied": w}, index=dv.columns)
    diag = {"lambda": lam, "grid": tab, "fit_rmse": float(np.sqrt(np.mean((X @ w - y) ** 2))),
            "all_india_holdout_rmse": ai_ho, "n_months": len(y)}
    return out, diag


# ----------------------------------------------------------------------------- item weights
def build_item_weights(div_weights: pd.Series, grp_urban: dict[str, tuple[str, float]],
                       mapping: pd.DataFrame, basket: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Item weights (sum 100 over covered groups) + coverage table by division."""
    # all-India urban group weight -> within-division share
    g = pd.DataFrame([(k, v[0], v[1]) for k, v in grp_urban.items()], columns=["group", "name", "w"])
    g["division"] = g["group"].str[:2]
    g["share_in_div"] = g["w"] / g.groupby("division")["w"].transform("sum")
    g["gj_group_w"] = g["division"].map(div_weights) * g["share_in_div"]          # fraction of Gujarat basket

    m = mapping.merge(basket[["item_id", "name", "tier"]], on="item_id")
    n_in_group = m.groupby("weight_group")["item_id"].transform("count")
    m = m.merge(g[["group", "gj_group_w"]], left_on="weight_group", right_on="group", how="left")
    if m["gj_group_w"].isna().any():
        raise ValueError(f"unmapped groups: {m[m.gj_group_w.isna()].weight_group.unique()}")
    m["raw"] = m["gj_group_w"] / n_in_group.values
    covered = g[g["group"].isin(m["weight_group"].unique())]
    total_cov = covered["gj_group_w"].sum()
    m["weight"] = m["raw"] / m["raw"].sum() * 100
    cov = (g.assign(covered=g["group"].isin(m["weight_group"].unique()))
             .groupby("division")
             .apply(lambda d: pd.Series({"gujarat_div_weight_pct": d["gj_group_w"].sum() * 100,
                                         "covered_pct": d.loc[d["covered"], "gj_group_w"].sum() * 100}),
                    include_groups=False))
    cov["coverage_ratio"] = cov["covered_pct"] / cov["gujarat_div_weight_pct"]
    cov.attrs["total_coverage"] = float(total_cov)
    return m[["item_id", "name", "tier", "weight_group", "match_quality", "weight"]], cov


def run(root: Path) -> dict:
    annex = json.loads((root / "data/sources_raw/expert_report_annex_text.json").read_text())
    div_ai, grp_ai = parse_annex_weights(annex)
    assert len(div_ai) == 12 and len(grp_ai) == 43, (len(div_ai), len(grp_ai))
    official = pd.read_csv(root / "data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    imp, diag = implied_gujarat_division_weights(official, div_ai)
    mapping = pd.read_csv(root / "data/basket_official_map.csv", dtype=str, keep_default_na=False)
    basket = pd.read_csv(root / "data/basket.csv", dtype={"division": str})
    items, cov = build_item_weights(imp["gujarat_urban_implied"], grp_ai, mapping, basket)
    # ---- hierarchical item weights (rpi/hierweights.py): replaces the equal split of a group's weight among its mapped items.
    from . import hierweights as HW
    first = sorted(official.period.unique())[0]
    tree = HW.fit_tree(official, {k: v[1] for k, v in grp_ai.items()}, imp["gujarat_urban_implied"], cv=True)
    lv0 = official[official.period == first]
    lv0 = lv0.set_index(lv0["code"].fillna(""))["index_value"].to_dict()
    node = {r.item_id: (r.official_item_code or HW.UNMAPPED_NODE.get(r.item_id, "")) for r in mapping.itertuples()}
    hw = HW.basket_weights(tree, node, lv0)
    items = items.rename(columns={"weight": "weight_equal_split_old"})
    items["weight"] = items["item_id"].map(hw)
    assert items["weight"].notna().all() and abs(items["weight"].sum() - 100) < 1e-6, items[items.weight.isna()]
    tree.round(6).to_csv(root / "data/official/hier_weights_tree.csv", index=False)

    src = (f"APPROX: MoSPI CPI2024 all-India urban group shares x Gujarat-urban division weights implied from official indices "
           f"(ridge lambda={diag['lambda']:g}, hold-out RMSE {diag['grid'].holdout_rmse.min():.3f} idx pts vs {diag['all_india_holdout_rmse']:.3f} "
           f"for all-India weights); equal split within group; covers {cov.attrs['total_coverage']*100:.1f}% of basket")
    src = src.replace("equal split within group", "within-group weights recovered node by node from the published official index tree (rpi/hierweights.py, blocked-CV ridge, top-down redistribution of unmapped branches)")
    out = items[["item_id", "weight"]].copy()
    out["weight"] = out["weight"].round(5)
    out["weight_source"] = src
    out.to_csv(root / "data/weights_cpi2024_gujarat_urban.csv", index=False)

    imp.assign(diff_pp=(imp.gujarat_urban_implied - imp.all_india_urban) * 100).round(5)\
       .to_csv(root / "data/official/gujarat_urban_division_weights_implied.csv")
    cov.round(4).to_csv(root / "data/official/weights_coverage_by_division.csv")
    items.round(5).to_csv(root / "data/official/weights_item_detail.csv", index=False)
    return {"implied": imp, "diag": diag, "items": items, "coverage": cov, "source": src}


if __name__ == "__main__":
    r = run(Path(__file__).resolve().parents[1])
    print(r["diag"]["grid"].round(4).to_string())
    print(r["coverage"].round(2).to_string())
    print("TOTAL COVERAGE %.1f%%" % (r["coverage"].attrs["total_coverage"] * 100))
    print(r["items"].sort_values("weight", ascending=False).head(12).round(3).to_string())
