"""Item-level calibration models for the rpi-to-official relationship, and their evaluation.

Development window: official months before 2026-01. Holdout: 2026-01 .. 2026-08.
Variants are chosen on the development window only. The frozen prospective model in econ/ledger is
not touched and is not one of these variants.

Test data are the clean item-months (rpi item change differs from the official item change);
back-filled identical months carry no independent information (see econ/items.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from econ.items import load_items

DEV_END = "2026-01"           # months strictly before this are development
SHRINK_K = 10.0               # per-item shrinkage strength (fixed in advance, not tuned)
VAR_FLOOR_SD = 0.2            # items whose rpi change has sd below this (percent) use the pooled slope
HUBER_C = 1.345


def clean_panel(lag: int = 0) -> pd.DataFrame:
    """Rows (period, item_id, quality, x, y). lag=1 pairs the official change with the previous rpi change."""
    L = load_items().long.copy()
    if lag:
        from econ.items import _rpi_item_mom
        xm = _rpi_item_mom().shift(lag)                  # x_{t-lag}, aligned to the official month t
        xl = xm.rename_axis("period").reset_index().melt(id_vars="period", var_name="item_id", value_name="x_lag")
        L = L.merge(xl, on=["period", "item_id"], how="left").dropna(subset=["x_lag"])
        L["x"] = L["x_lag"]
    L = L[(L.x - L.y).abs() >= 1e-6]
    return L.reset_index(drop=True)


def _fit_pooled(tr: pd.DataFrame) -> tuple[float, float]:
    b, a = np.polyfit(tr.x, tr.y, 1)
    return a, b


def _fit_huber(tr: pd.DataFrame, iters: int = 50) -> tuple[float, float]:
    X = np.column_stack([np.ones(len(tr)), tr.x.values])
    y = tr.y.values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    for _ in range(iters):
        r = y - X @ beta
        s = np.median(np.abs(r)) / 0.6745 + 1e-9
        u = np.abs(r) / s
        w = np.where(u <= HUBER_C, 1.0, HUBER_C / u)
        beta = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]
    return float(beta[0]), float(beta[1])


def predict(name: str, tr: pd.DataFrame, te: pd.DataFrame) -> np.ndarray:
    if name == "raw":
        return te.x.values
    if name == "pooled":
        a, b = _fit_pooled(tr)
        return a + b * te.x.values
    if name == "by_quality":
        out = np.empty(len(te))
        pooled = _fit_pooled(tr)
        for q in te.quality.unique():
            t = tr[tr.quality == q]
            a, b = _fit_pooled(t) if len(t) >= 20 else pooled
            m = (te.quality == q).values
            out[m] = a + b * te.x.values[m]
        return out
    if name == "item_shrink":
        a0, b0 = _fit_pooled(tr)
        slopes = {}
        for i, h in tr.groupby("item_id"):
            if len(h) >= 4 and h.x.std() >= VAR_FLOOR_SD:   # flat items fall back to the pooled slope
                bi = np.cov(h.x, h.y, bias=True)[0, 1] / h.x.var()
            else:
                bi = b0
            lam = len(h) / (len(h) + SHRINK_K)
            slopes[i] = lam * bi + (1 - lam) * b0
        b = te.item_id.map(slopes).fillna(b0).values
        return a0 + b * te.x.values
    if name == "huber":
        a, b = _fit_huber(tr)
        return a + b * te.x.values
    raise ValueError(name)


VARIANTS = ["raw", "pooled", "by_quality", "item_shrink", "huber"]


def rolling(panel: pd.DataFrame, variant: str) -> pd.DataFrame:
    rows = []
    for m in sorted(panel.period.unique()):
        tr = panel[panel.period < m]
        te = panel[panel.period == m]
        if len(tr) < 30 or te.empty:
            continue
        pred = predict(variant, tr, te)
        rows.append(pd.DataFrame({"period": m, "item_id": te.item_id.values, "y": te.y.values, "pred": pred}))
    return pd.concat(rows, ignore_index=True)


def rmse(df: pd.DataFrame) -> float:
    return float(np.sqrt(((df.y - df.pred) ** 2).mean()))


def evaluate(lag: int = 0) -> pd.DataFrame:
    panel = clean_panel(lag)
    out = []
    for v in VARIANTS:
        r = rolling(panel, v)
        dev = r[r.period < DEV_END]
        hold = r[r.period >= DEV_END]
        out.append({"variant": v, "lag": lag, "n_dev": len(dev), "rmse_dev": rmse(dev),
                    "n_hold": len(hold), "rmse_hold": rmse(hold), "n_all": len(r), "rmse_all": rmse(r)})
    return pd.DataFrame(out)


# ---- nested evaluation: the Huber threshold is chosen inside each training window only ----
C_GRID = [0.8, 1.0, 1.345, 2.0, 3.0]
MIN_INNER = 6   # first inner origin needs this many prior months


def _fit_huber_c(tr: pd.DataFrame, c: float, iters: int = 50) -> tuple[float, float]:
    X = np.column_stack([np.ones(len(tr)), tr.x.values])
    y = tr.y.values
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    for _ in range(iters):
        r = y - X @ beta
        s = np.median(np.abs(r)) / 0.6745 + 1e-9
        u = np.abs(r) / s
        w = np.where(u <= c, 1.0, c / u)
        beta = np.linalg.lstsq(X * w[:, None], y * w, rcond=None)[0]
    return float(beta[0]), float(beta[1])


def choose_c(train: pd.DataFrame) -> tuple[float, dict]:
    """Expanding-window inner validation inside the training months only."""
    periods = sorted(train.period.unique())
    scores = {}
    for c in C_GRID:
        errs = []
        for k in periods[MIN_INNER:]:
            inner_tr = train[train.period < k]
            inner_te = train[train.period == k]
            a, b = _fit_huber_c(inner_tr, c)
            errs.append(((inner_te.y.values - (a + b * inner_te.x.values)) ** 2).mean())
        scores[c] = float(np.mean(errs)) if errs else np.inf
    best = min(scores, key=scores.get)
    return best, scores


def nested_eval() -> pd.DataFrame:
    panel = clean_panel(0)
    rows = []
    for m in sorted(panel.period.unique()):
        tr = panel[panel.period < m]
        te = panel[panel.period == m]
        if len(tr) < 30 or te.empty or tr.period.nunique() < MIN_INNER + 2:
            continue
        c, _ = choose_c(tr)
        a, b = _fit_huber_c(tr, c)
        rows.append(pd.DataFrame({"period": m, "item_id": te.item_id.values, "y": te.y.values,
                                  "raw": te.x.values, "pooled": _fit_pooled(tr)[0] + _fit_pooled(tr)[1] * te.x.values,
                                  "huber_nested": a + b * te.x.values, "c_chosen": c}))
    return pd.concat(rows, ignore_index=True)
