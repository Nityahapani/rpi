"""Accuracy tests that do not need a Rajkot ground truth (pure functions; the runner is scripts/pooled_accuracy.py).

1. POOLED PASS-THROUGH.  How far does a retail (official) item index move when wholesale moves by 1%?  The Rajkot-only history is 9 monthly changes,
   so the coefficient is estimated on every OTHER state (about 25 states x 9 changes) and then applied to Gujarat / Rajkot, which is held out.
   No Gujarat official data enter the estimate.  Specification is fixed in advance: monthly log changes, no intercept, lag 0 or lag 0+1 chosen by
   leave-one-state-out RMSE on the states other than Gujarat.
2. THREE-CORNERED HAT (one-factor measurement model).  Three institutionally independent measurements of the same item's monthly price change -
   the official CPI survey, DoCA retail reporters, Agmarknet wholesale - are modelled x_k = lambda_k * f + e_k.  With three indicators the model is
   exactly identified from the covariance matrix: lambda_a^2 = C_ab * C_ac / C_bc, noise_a = C_aa - lambda_a^2, reliability_a = lambda_a^2 / C_aa.
   That gives each source's share of signal without any ground truth, and an attenuation-corrected pass-through lambda_official / lambda_wholesale.
3. FORECAST SCORING.  Diebold-Mariano test (Harvey-Leybourne-Newbold small-sample correction) and leave-one-out coverage of the conformal band.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

ALIASES = {"nct of delhi": "delhi", "orissa": "odisha", "jammu and kashmir": "jammu and kashmir", "andaman and nicobar islands": "andaman and nicobar islands",
           "dadra and nagar haveli and daman and diu": "dnh and dd", "dadra and nagar haveli": "dnh and dd", "daman and diu": "dnh and dd"}


def norm_state(s: str) -> str:
    s = str(s).lower().replace("&", "and").replace("the ", "", 1) if str(s).lower().startswith("the ") else str(s).lower().replace("&", "and")
    s = " ".join(s.split())
    return ALIASES.get(s, s)


def changes(panel: pd.DataFrame, col: str) -> pd.Series:
    """panel columns: key, month ('YYYY-MM'), <col> level -> monthly log change indexed by (key, month); only between consecutive calendar months."""
    out = {}
    for k, g in panel.groupby("key"):
        s = g.drop_duplicates("month").set_index("month")[col].astype(float).sort_index()
        s = s[s > 0]
        if len(s) < 2: continue
        per = pd.PeriodIndex(s.index, freq="M")
        ls = np.log(s.values)
        for a in range(1, len(s)):
            if (per[a] - per[a - 1]).n == 1:
                out[(k, str(per[a]))] = float(ls[a] - ls[a - 1])
    return pd.Series(out, dtype=float)


def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def design(df: pd.DataFrame, lag: bool) -> tuple[np.ndarray, np.ndarray]:
    X = df[["dw", "dw1"]].values if lag else df[["dw"]].values
    return X, df["do"].values


def loso(df: pd.DataFrame, lag: bool, exclude=("gujarat",)) -> dict:
    """Leave-one-state-out RMSE of pooled pass-through vs baselines beta=1 (what the index implicitly assumes) and beta=0, over states not excluded."""
    res = []
    for s in sorted(set(df.state) - set(exclude)):
        tr, te = df[(df.state != s) & ~df.state.isin(exclude)], df[df.state == s]
        if len(te) < 6 or len(tr) < 20: continue
        b = _ols(*design(tr, lag)[:1], tr["do"].values) if False else _ols(design(tr, lag)[0], tr["do"].values)
        Xte = design(te, lag)[0]
        pred = Xte @ b
        base1 = te["dw"].values
        r = lambda p: math.sqrt(float(np.mean((te["do"].values - p) ** 2)))
        dr = lambda p: abs(float(np.sum(p) - np.sum(te["do"].values)))
        res.append(dict(state=s, rmse_pool=r(pred), rmse_b1=r(base1), rmse_b0=r(0 * base1), drift_pool=dr(pred), drift_b1=dr(base1), drift_b0=dr(0 * base1)))
    r = pd.DataFrame(res)
    if r.empty: return dict(n_states=0)
    return dict(n_states=len(r), rmse_pool=float(r.rmse_pool.mean()), rmse_b1=float(r.rmse_b1.mean()), rmse_b0=float(r.rmse_b0.mean()),
                drift_pool=float(r.drift_pool.median()), drift_b1=float(r.drift_b1.median()), drift_b0=float(r.drift_b0.median()),
                wins_vs_b1=int((r.rmse_pool < r.rmse_b1).sum()), wins_vs_b0=int((r.rmse_pool < r.rmse_b0).sum()))


def boot_beta(df: pd.DataFrame, lag: bool, reps: int = 400, seed: int = 11, exclude=("gujarat",)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pooled coefficient(s) on non-excluded states with a 90% state-cluster bootstrap interval."""
    d = df[~df.state.isin(exclude)]
    b = _ols(design(d, lag)[0], d["do"].values)
    states = sorted(d.state.unique()); rng = np.random.default_rng(seed); draws = []
    groups = {s: d[d.state == s] for s in states}
    for _ in range(reps):
        pick = rng.choice(len(states), len(states))
        x = pd.concat([groups[states[i]] for i in pick])
        draws.append(_ols(design(x, lag)[0], x["do"].values))
    draws = np.array(draws)
    return b, np.percentile(draws, 5, axis=0), np.percentile(draws, 95, axis=0)


def triad(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> dict:
    """One-factor model from three change vectors (rows aligned). Returns loadings, noise variances and reliabilities (None if not identified)."""
    X = np.column_stack([a, b, c]); X = X - X.mean(axis=0)
    C = np.cov(X, rowvar=False)
    out = {}
    names = ("a", "b", "c")
    for i, j, k, n in ((0, 1, 2, "a"), (1, 0, 2, "b"), (2, 0, 1, "c")):
        if C[j, k] <= 1e-12: out[n] = dict(loading=None, reliability=None, noise_sd=None); continue
        l2 = C[i, j] * C[i, k] / C[j, k]
        if l2 <= 0 or l2 > C[i, i] * 1.0000001:
            out[n] = dict(loading=None, reliability=None, noise_sd=None, note="Heywood case"); continue
        out[n] = dict(loading=math.sqrt(l2), reliability=l2 / C[i, i], noise_sd=math.sqrt(max(C[i, i] - l2, 0.0)), sd=math.sqrt(C[i, i]))
    return out


def triad_boot(frame: pd.DataFrame, cols=("o", "d", "w"), reps: int = 400, seed: int = 5) -> dict:
    """Point estimate plus 90% state-cluster bootstrap intervals of reliabilities and of the pass-through loading ratio lambda_o / lambda_w."""
    est = triad(*(frame[c].values for c in cols))
    states = sorted(frame.state.unique()); rng = np.random.default_rng(seed); groups = {s: frame[frame.state == s] for s in states}
    rel = {c: [] for c in "abc"}; ratio = []
    for _ in range(reps):
        x = pd.concat([groups[states[i]] for i in rng.choice(len(states), len(states))])
        t = triad(*(x[c].values for c in cols))
        for n, c in zip("abc", "abc"):
            if t[n]["reliability"] is not None: rel[c].append(t[n]["reliability"])
        if t["a"]["loading"] and t["c"]["loading"]: ratio.append(t["a"]["loading"] / t["c"]["loading"])
    pc = lambda v, q: float(np.percentile(v, q)) if len(v) >= 20 else None
    return dict(est=est, rel_ci={c: (pc(rel[c], 5), pc(rel[c], 95), len(rel[c])) for c in "abc"}, ratio_ci=(pc(ratio, 5), pc(ratio, 95), len(ratio)),
                ratio=(est["a"]["loading"] / est["c"]["loading"]) if est["a"]["loading"] and est["c"]["loading"] else None)


def dm_test(e1: np.ndarray, e2: np.ndarray) -> dict:
    """Diebold-Mariano for squared-error loss, one-step horizon, HLN small-sample correction; H0 equal accuracy. Negative stat = forecast 1 better."""
    d = np.asarray(e1) ** 2 - np.asarray(e2) ** 2
    n = len(d)
    if n < 5 or d.std() == 0: return dict(n=n, stat=None, p=None)
    stat = d.mean() / math.sqrt(d.var(ddof=1) / n)
    stat *= math.sqrt((n - 1) / n)           # HLN with h = 1
    from math import erf
    # Student-t(n-1) two-sided p via numeric integration of the t density (no scipy dependency)
    p = _t_two_sided(abs(stat), n - 1)
    return dict(n=n, stat=float(stat), p=float(p))


def _t_two_sided(x: float, df: int) -> float:
    from math import gamma, pi, sqrt
    c = gamma((df + 1) / 2) / (sqrt(df * pi) * gamma(df / 2))
    xs = np.linspace(0, x, 4001)
    area = np.trapezoid(c * (1 + xs ** 2 / df) ** (-(df + 1) / 2), xs)
    return max(0.0, 1 - 2 * area)


def loo_conformal_coverage(err: np.ndarray, alpha: float = 0.10) -> dict:
    """Leave-one-out: the band for month i is the finite-sample-corrected (1-alpha) quantile of |errors| of all OTHER months; coverage = share of months inside."""
    e = np.abs(np.asarray(err)); n = len(e); hit = []
    for i in range(n):
        o = np.sort(np.delete(e, i)); k = math.ceil((len(o) + 1) * (1 - alpha))
        q = o[min(k, len(o)) - 1] if k <= len(o) else np.inf
        hit.append(e[i] <= q)
    return dict(n=n, coverage=float(np.mean(hit)), target=1 - alpha)
