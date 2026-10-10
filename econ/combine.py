"""Candidate nowcasts of the official general MoM, all evaluated on one rolling-origin protocol.

Protocol (fixed before running, see econ/cli.py): origin m uses only information dated before m,
except for the rpi division changes of month m itself, which the rpi already has. Candidates are
never tuned on the test month. Every candidate is reported, not only the winner.

Candidates
  fixed_weight       official division weights applied to rpi division changes (no parameters)
  fw_mean_bias       fixed_weight + mean past gap (official - fixed_weight)
  fw_ewma_bias       fixed_weight + EWMA past gap, half-life 3 months (fixed in advance)
  anchored_ridge     OLS of official MoM on division MoMs, ridge-shrunk toward the official
                     weights, penalty by leave-one-out on the training months
  factor_bridge      the one-factor DFM bridge from econ/evaluate.py (previous version)
  combo_fw_anchored  equal average of fixed_weight, fw_ewma_bias and anchored_ridge
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from econ import evaluate
from econ.data import Panel, division_changes

MIN_TRAIN = 8
RIDGE_GRID = np.logspace(-3, 3, 25)
EWMA_HALFLIFE = 3.0


def _ewma_last(x: np.ndarray, halflife: float) -> float:
    if len(x) == 0:
        return 0.0
    w = 0.5 ** (np.arange(len(x))[::-1] / halflife)
    return float(np.sum(w * x) / np.sum(w))


def _anchored_ridge(X: np.ndarray, y: np.ndarray, w: np.ndarray, x_new: np.ndarray) -> tuple[float, float]:
    """Predict y_new from X with coefficients shrunk toward w. Returns (prediction, chosen lambda).

    Model: y = a + X b,  b = w + d,  d shrunk to zero. Solve for d on the residual y - X w,
    intercept a from centred data. The penalty is chosen by leave-one-out (closed form).
    """
    xm, ym = X.mean(axis=0), y.mean()
    Xc = X - xm
    r = (y - X @ w) - (y - X @ w).mean()
    best = None
    for lam in RIDGE_GRID:
        A = Xc.T @ Xc + lam * np.eye(X.shape[1])
        H = Xc @ np.linalg.solve(A, Xc.T)
        resid = r - H @ r
        loo = np.mean((resid / (1.0 - np.diag(H))) ** 2)
        if best is None or loo < best[0]:
            best = (loo, lam, np.linalg.solve(A, Xc.T @ r))
    _, lam, d = best
    b = w + d
    intercept = ym - X.mean(axis=0) @ b
    return float(intercept + x_new @ b), float(lam)


def candidates(p: Panel) -> pd.DataFrame:
    dc = division_changes(p)[p.divisions]
    w = p.weights.values
    fw = (dc * w).sum(axis=1, min_count=len(p.divisions))
    official = p.official_mom
    rows = []
    for m in official.index:
        prior_idx = official.loc[:m].index[:-1]
        if len(prior_idx) < MIN_TRAIN:
            continue
        prev = evaluate._prev(p.periods, m)
        y_prior = official.loc[prior_idx].values
        X_prior = dc.loc[prior_idx].values
        gap = y_prior - fw.loc[prior_idx].values
        x_new = dc.loc[m].values

        row = {"period": m, "official_mom": official.loc[m]}
        row["fixed_weight"] = fw.loc[m]
        row["fw_mean_bias"] = fw.loc[m] + gap.mean()
        row["fw_ewma_bias"] = fw.loc[m] + _ewma_last(gap, EWMA_HALFLIFE)
        pred, lam = _anchored_ridge(X_prior, y_prior, w, x_new)
        row["anchored_ridge"] = pred
        row["ridge_lambda"] = lam

        run = evaluate.factor_run(p, upto=m, params_upto=prev)
        br = evaluate.fit_bridge(run.f.loc[:prev], official.loc[prior_idx])
        row["factor_bridge"] = br.alpha + br.beta * run.f.loc[m]

        row["combo_fw_anchored"] = np.mean([row["fixed_weight"], row["fw_ewma_bias"], row["anchored_ridge"]])
        rows.append(row)
    return pd.DataFrame(rows).set_index("period")


def score(cands: pd.DataFrame) -> pd.DataFrame:
    names = ["fixed_weight", "fw_mean_bias", "fw_ewma_bias", "anchored_ridge", "factor_bridge", "combo_fw_anchored"]
    out = []
    for n in names:
        e = (cands[n] - cands["official_mom"]).dropna()
        out.append({"model": n, "n": len(e), "rmse": float(np.sqrt((e ** 2).mean())), "mae": float(e.abs().mean()),
                    "bias": float(e.mean())})
    return pd.DataFrame(out).sort_values("rmse").reset_index(drop=True)


def paired_rmse_gap(cands: pd.DataFrame, model: str, base: str = "fixed_weight", reps: int = 5000, seed: int = 0):
    """Bootstrap 95% interval for RMSE(model) - RMSE(base) over the same months."""
    d = pd.concat([(cands[model] - cands.official_mom) ** 2, (cands[base] - cands.official_mom) ** 2], axis=1).dropna()
    rng = np.random.default_rng(seed)
    n = len(d)
    gaps = np.empty(reps)
    for k in range(reps):
        s = d.values[rng.integers(0, n, n)]
        gaps[k] = np.sqrt(s[:, 0].mean()) - np.sqrt(s[:, 1].mean())
    obs = np.sqrt(d.iloc[:, 0].mean()) - np.sqrt(d.iloc[:, 1].mean())
    return float(obs), float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5))
