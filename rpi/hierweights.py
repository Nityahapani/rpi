"""Hierarchical weight recovery for the official MoSPI CPI-2024 tree (Gujarat-urban).

Why: MoSPI publishes index levels for every node of its classification tree (general > division > group > class > sub_class >
item) but not Gujarat weights.  Every published parent index is a fixed-weight (Laspeyres) average of its children's indices:

        I_parent(t) = sum_c s_c * I_c(t),    s_c >= 0, sum_c s_c = 1       (verified: residual ~0.003 index pts = rounding of 0.01)

so the shares s_c can be backed out node by node from the published levels.  Each node has few children, which is far better
conditioned than one flat regression of the general index on 12 divisions or 347 items.  Shares are fitted with a ridge pull
toward a prior (equal split; all-India urban group shares at group level) whose strength is chosen per node by blocked
cross-validation on the parent index.  A basket item then receives the weight of the official node it is mapped to, and
the weight of branches with no basket item is handed to their siblings pro rata (top-down), so every ancestor node keeps its
fitted weight.  Replaces the old "group weight split equally among mapped items" rule (rpi/weights_build.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

CHAIN = ["item", "sub_class", "class", "group", "division"]
SEGS = {"item": 4, "sub_class": 3, "class": 2, "group": 1, "division": 0}
# basket items with no official item index are weighted as the official node they most resemble (weights only; their prices are not official)
UNMAPPED_NODE = {"T005": "07.2.1.2.1.01"}   # two-wheeler service -> official "Parts for personal transport equipment" (07.2.1.2)
LAMS = (1e-8, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2)


def parent_code(code: str, level: str) -> str:
    n = SEGS[level]
    return ".".join(code.split(".")[:n]) if n else "GEN"


def level_matrices(off: pd.DataFrame) -> tuple[dict, pd.Series]:
    off = off.assign(code=off["code"].fillna("").astype(str))
    P = {lv: off[off.level == lv].pivot_table(index="period", columns="code", values="index_value", aggfunc="first").sort_index()
         for lv in CHAIN}
    gen = off[off.level == "general"].set_index("period")["index_value"].sort_index()
    return P, gen


def fit_shares(X: np.ndarray, y: np.ndarray, prior: np.ndarray, lam: float) -> np.ndarray:
    n, k = X.shape
    if k == 1:
        return np.ones(1)
    sc = float(np.mean(y))
    Xs, ys = X / sc, y / sc                       # scale-free, so the lambda grid means the same at every node
    obj = lambda s: float(np.sum((Xs @ s - ys) ** 2) + lam * n * np.sum((s - prior) ** 2))
    jac = lambda s: 2 * Xs.T @ (Xs @ s - ys) + 2 * lam * n * (s - prior)
    r = minimize(obj, prior, jac=jac, method="SLSQP", bounds=[(0, 1)] * k,
                 constraints=[{"type": "eq", "fun": lambda s: s.sum() - 1, "jac": lambda s: np.ones(k)}],
                 options={"maxiter": 300, "ftol": 1e-15})
    s = np.clip(r.x, 0, None)
    return s / s.sum()


def cv_lambda(X, y, prior, folds: int = 4) -> tuple[float, float]:
    """Blocked (contiguous) K-fold CV on the parent index; returns (best lambda, its CV RMSE in index points)."""
    n = len(y)
    edges = np.linspace(0, n, folds + 1).astype(int)
    best = (None, np.inf)
    for lam in LAMS:
        se = []
        for a, b in zip(edges[:-1], edges[1:]):
            tr = np.r_[0:a, b:n]
            s = fit_shares(X[tr], y[tr], prior, lam)
            se.append((X[a:b] @ s - y[a:b]) ** 2)
        rm = float(np.sqrt(np.concatenate(se).mean()))
        if rm < best[1] - 1e-12:
            best = (lam, rm)
    return best


def fit_tree(off: pd.DataFrame, group_prior: dict[str, float] | None = None, division_weights: pd.Series | None = None,
             periods: list[str] | None = None, cv: bool = True) -> pd.DataFrame:
    """Return one row per node: level, code, parent, share (within parent), lam, cv_rmse, equal_rmse, fit_rmse."""
    P, gen = level_matrices(off)
    if periods is not None:
        P = {k: v.loc[v.index.isin(periods)] for k, v in P.items()}
        gen = gen.loc[gen.index.isin(periods)]
    rows = []
    # top: divisions under general
    dv = P["division"]
    if division_weights is not None:
        s = division_weights.reindex(dv.columns).astype(float).values
        s = s / s.sum()
        rows += [dict(level="division", code=c, parent="GEN", share=float(v), lam=np.nan, cv_rmse=np.nan, equal_rmse=np.nan, fit_rmse=np.nan)
                 for c, v in zip(dv.columns, s)]
    for lv in CHAIN[:-1] + ([] if division_weights is not None else ["division"]):
        M = P[lv]
        up = P[CHAIN[CHAIN.index(lv) + 1]] if lv != "division" else None
        groups: dict[str, list[str]] = {}
        for c in M.columns:
            groups.setdefault(parent_code(c, lv), []).append(c)
        for par, kids in groups.items():
            y = (gen if par == "GEN" else up[par]).reindex(M.index).values.astype(float) if lv != "division" or par == "GEN" else None
            if lv == "division":
                y = gen.reindex(M.index).values.astype(float)
            ok = ~np.isnan(y) & ~np.isnan(M[kids].values).any(axis=1)
            X = M[kids].values.astype(float)[ok]; yy = y[ok]
            k = len(kids)
            prior = np.ones(k) / k
            if lv == "group" and group_prior:
                g = np.array([group_prior.get(c, np.nan) for c in kids], float)
                if not np.isnan(g).any() and g.sum() > 0:
                    prior = g / g.sum()
            if k == 1:
                rows.append(dict(level=lv, code=kids[0], parent=par, share=1.0, lam=np.nan, cv_rmse=0.0, equal_rmse=0.0, fit_rmse=0.0)); continue
            lam, cvr = cv_lambda(X, yy, prior) if cv else (1e-4, np.nan)
            s = fit_shares(X, yy, prior, lam)
            eq = float(np.sqrt(np.mean((X @ (np.ones(k) / k) - yy) ** 2)))
            for c, v in zip(kids, s):
                rows.append(dict(level=lv, code=c, parent=par, share=float(v), lam=lam, cv_rmse=cvr, equal_rmse=eq,
                                 fit_rmse=float(np.sqrt(np.mean((X @ s - yy) ** 2)))))
    return pd.DataFrame(rows)


def basket_weights(tree: pd.DataFrame, node_of: dict[str, str], levels_at_ref: dict[str, float] | None = None,
                   pool_level: str | None = None) -> pd.Series:
    """Top-down allocation.  node_of: basket item -> official ITEM code it stands for.  Returns weights summing to 100.

    levels_at_ref (optional): official index level of every node at the engine's base month, to convert base-period shares into
    base-month value shares (our engine chains from 100 at its first month, so the right weight is share * I_node(base) / I_parent(base)).
    """
    t = tree.set_index("code")
    kids: dict[str, list[str]] = {}
    for c, r in t.iterrows():
        kids.setdefault(r["parent"], []).append(c)
    share = t["share"].copy()
    if levels_at_ref:
        # value-share: s_c * I_c / sum_siblings(s * I)
        for par, ks in kids.items():
            v = np.array([share[c] * levels_at_ref.get(c, 100.0) for c in ks])
            for c, x in zip(ks, v / v.sum()):
                share[c] = x
    mapped_nodes: dict[str, list[str]] = {}
    for it, c in node_of.items():
        mapped_nodes.setdefault(c, []).append(it)
    has: dict[str, bool] = {}

    def anym(c):
        if c not in has:
            has[c] = c in mapped_nodes or any(anym(k) for k in kids.get(c, []))
        return has[c]

    out: dict[str, float] = {}
    pool_depth = None if pool_level is None else CHAIN.index(pool_level)

    def own(c, w):                                   # weight of node c itself, no redistribution below
        return w

    def down(c, w):
        if pool_level is not None and c != "GEN" and t.loc[c, "level"] == pool_level:
            # below the pooling level: each mapped item keeps ONLY its own node weight (share product), scaled to the pool node's weight
            def own_w(n, ww, acc):
                if n in mapped_nodes:
                    for it in mapped_nodes[n]:
                        acc[it] = acc.get(it, 0.0) + ww / len(mapped_nodes[n])
                    return
                for k in kids.get(n, []):
                    own_w(k, ww * share[k], acc)
            acc: dict[str, float] = {}
            own_w(c, 1.0, acc)
            tot = sum(acc.values())
            for it, v in acc.items():
                out[it] = out.get(it, 0.0) + w * v / tot
            return
        if c in mapped_nodes:
            for it in mapped_nodes[c]:
                out[it] = out.get(it, 0.0) + w / len(mapped_nodes[c])
            return
        ks = [k for k in kids.get(c, []) if anym(k)]
        tot = sum(share[k] for k in ks)
        for k in ks:
            down(k, w * share[k] / tot)

    down("GEN", 100.0)
    return pd.Series(out)
