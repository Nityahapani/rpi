"""Leakage-aware expanding-window item calibration experiments.

The input panel is built from independent raw sources only (econ.experiments.source_panel): no
``official_link`` quote, no imputed month, no target-dependent residual screen, and causal
matched-model chain-Jevons changes. Every outer fold trains strictly before its test month.
Nested Huber selects its clipping constant only in inner expanding folds. Additional candidates
include identity-shrunk Huber calibration, recency-weighted Huber, a robust median bias-only
correction, and an origin-constrained Huber slope. The hierarchical state-space candidate
partially pools item intercepts/slopes and forecasts a common AR(1) state in prequential
training residuals with a scalar Kalman filter.

There are two evaluation modes:
* archive_walk_forward is chronological and target-leakage-safe, but historical source
  fetch vintages may post-date those old test months; it is exploratory, not a real-time claim.
* release_replay rebuilds source inputs using only observations fetched strictly before a
  non-bootstrap official arrival date. It is the conservative real-time check; at present it
  has only one matured official month, so it cannot establish a winner.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from econ.experiments.source_panel import live_release_targets, load_source_panel

C_GRID = (0.8, 1.0, 1.345, 2.0, 3.0)
IDENTITY_SHRINK_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)
RECENCY_HALF_LIFE_GRID = (3.0, 6.0, 12.0, 24.0, float("inf"))
OUTER_MIN_TRAIN_MONTHS = 8
INNER_MIN_TRAIN_MONTHS = 6
HIERARCHICAL_K = 10.0
HIERARCHICAL_MIN_ITEM_MONTHS = 4
HIERARCHICAL_MIN_X_SD = 0.2
STATE_MIN_RESIDUAL_MONTHS = 6
STATE_MIN_TRAIN_MONTHS = 6
STATE_MEASUREMENT_FLOOR = 0.05
BOOTSTRAP_REPS = 4000
BOOTSTRAP_BLOCK = 3


@dataclass(frozen=True)
class HierarchicalFit:
    alpha0: float
    beta0: float
    alpha: dict[str, float]
    beta: dict[str, float]
    k: float


def _row_weights(frame: pd.DataFrame) -> np.ndarray:
    """Normalize item expenditure weights within each month; each month has equal total fit weight."""
    w = pd.to_numeric(frame.weight, errors="coerce").fillna(0.0).to_numpy(float)
    sums = pd.Series(w, index=frame.index).groupby(frame.period).transform("sum").to_numpy(float)
    return np.divide(w, sums, out=np.zeros_like(w), where=sums > 0)


def _weighted_ols(frame: pd.DataFrame) -> tuple[float, float]:
    x = frame.x.to_numpy(float)
    y = frame.y.to_numpy(float)
    w = _row_weights(frame)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(w) & (w > 0)
    if ok.sum() < 2:
        return 0.0, 1.0
    X = np.column_stack([np.ones(ok.sum()), x[ok]])
    sw = np.sqrt(w[ok])
    coef, *_ = np.linalg.lstsq(X * sw[:, None], y[ok] * sw, rcond=None)
    return float(coef[0]), float(coef[1])


def _fit_huber_with_weights(frame: pd.DataFrame, c: float, base: np.ndarray,
                            iters: int = 60) -> tuple[float, float]:
    """Huber IRLS with caller-supplied nonnegative observation weights."""
    x = frame.x.to_numpy(float)
    y = frame.y.to_numpy(float)
    base = np.asarray(base, dtype=float)
    if len(base) != len(frame):
        raise ValueError("base weights must match frame rows")
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(base) & (base > 0)
    x, y, base = x[ok], y[ok], base[ok]
    if len(y) < 2:
        return 0.0, 1.0
    base = base / base.sum()
    X = np.column_stack([np.ones(len(x)), x])
    sw = np.sqrt(base)
    coef, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    for _ in range(iters):
        resid = y - X @ coef
        med = np.median(resid)
        scale = 1.4826 * np.median(np.abs(resid - med)) + 1e-9
        u = np.abs(resid) / scale
        robust = np.ones_like(u)
        mask = u > c
        robust[mask] = c / u[mask]
        sw = np.sqrt(base * robust)
        new, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
        if np.max(np.abs(new - coef)) < 1e-10:
            coef = new
            break
        coef = new
    return float(coef[0]), float(coef[1])


def fit_huber(frame: pd.DataFrame, c: float, iters: int = 60) -> tuple[float, float]:
    """Basket-weighted Huber IRLS for y = intercept + slope*x."""
    return _fit_huber_with_weights(frame, c, _row_weights(frame), iters)


def _weighted_month_mse(frame: pd.DataFrame, pred: np.ndarray) -> float:
    y = frame.y.to_numpy(float)
    w = pd.to_numeric(frame.weight, errors="coerce").fillna(0.0).to_numpy(float)
    if not len(y):
        return float("nan")
    w = w / w.sum() if w.sum() > 0 else np.full(len(y), 1 / len(y))
    return float(np.sum(w * (y - pred) ** 2))


def choose_huber_c(train: pd.DataFrame) -> tuple[float, dict[float, float]]:
    """Select c by month-balanced inner expanding validation, using train data only."""
    months = sorted(train.period.astype(str).unique())
    val_months = months[INNER_MIN_TRAIN_MONTHS:]
    scores: dict[float, float] = {}
    for c in C_GRID:
        loss = []
        for month in val_months:
            tr = train[train.period.astype(str) < month]
            te = train[train.period.astype(str) == month]
            if tr.period.nunique() < INNER_MIN_TRAIN_MONTHS or te.empty:
                continue
            a, b = fit_huber(tr, c)
            loss.append(_weighted_month_mse(te, a + b * te.x.to_numpy(float)))
        scores[c] = float(np.mean(loss)) if loss else float("inf")
    finite = {k: v for k, v in scores.items() if np.isfinite(v)}
    return (min(finite, key=finite.get) if finite else 1.345), scores


def _identity_shrunk_prediction(frame: pd.DataFrame, alpha: float, beta: float,
                                shrink: float) -> np.ndarray:
    """Damp a calibrated line toward the no-correction benchmark y=x."""
    x = frame.x.to_numpy(float)
    return x + float(shrink) * (float(alpha) + (float(beta) - 1.0) * x)


def choose_identity_shrink(train: pd.DataFrame) -> tuple[float, dict[float, float]]:
    """Choose Huber-to-identity blend weight using only inner expanding folds."""
    months = sorted(train.period.astype(str).unique())
    val_months = months[INNER_MIN_TRAIN_MONTHS:]
    losses: dict[float, list[float]] = {g: [] for g in IDENTITY_SHRINK_GRID}
    for month in val_months:
        tr = train[train.period.astype(str) < month]
        te = train[train.period.astype(str) == month]
        if tr.period.nunique() < INNER_MIN_TRAIN_MONTHS or te.empty:
            continue
        alpha, beta = fit_huber(tr, 1.345)
        for shrink in IDENTITY_SHRINK_GRID:
            pred = _identity_shrunk_prediction(te, alpha, beta, shrink)
            losses[shrink].append(_weighted_month_mse(te, pred))
    scores = {g: float(np.mean(v)) if v else float("inf") for g, v in losses.items()}
    finite = {g: loss for g, loss in scores.items() if np.isfinite(loss)}
    # Grid starts at zero, so ties favor the simpler raw benchmark.
    best = min(finite, key=finite.get) if finite else 0.0
    return float(best), scores


def _recency_weights(frame: pd.DataFrame, half_life: float) -> np.ndarray:
    """Basket weights multiplied by an exponential month-age decay."""
    base = _row_weights(frame)
    if not np.isfinite(half_life):
        return base
    if half_life <= 0:
        raise ValueError("half_life must be positive or infinity")
    ordinals = pd.PeriodIndex(frame.period.astype(str), freq="M").asi8.astype(float)
    age = float(ordinals.max()) - ordinals
    decay = np.exp2(-age / float(half_life))
    weights = base * decay
    return weights / weights.sum() if weights.sum() > 0 else base


def choose_recency_half_life(train: pd.DataFrame) -> tuple[float, dict[float, float]]:
    """Choose exponential-decay half-life by inner expanding validation only."""
    months = sorted(train.period.astype(str).unique())
    val_months = months[INNER_MIN_TRAIN_MONTHS:]
    losses: dict[float, list[float]] = {h: [] for h in RECENCY_HALF_LIFE_GRID}
    for month in val_months:
        tr = train[train.period.astype(str) < month]
        te = train[train.period.astype(str) == month]
        if tr.period.nunique() < INNER_MIN_TRAIN_MONTHS or te.empty:
            continue
        for half_life in RECENCY_HALF_LIFE_GRID:
            alpha, beta = _fit_huber_with_weights(
                tr, 1.345, _recency_weights(tr, half_life)
            )
            pred = alpha + beta * te.x.to_numpy(float)
            losses[half_life].append(_weighted_month_mse(te, pred))
    scores = {h: float(np.mean(v)) if v else float("inf") for h, v in losses.items()}
    finite = {h: loss for h, loss in scores.items() if np.isfinite(loss)}
    # The infinite half-life entry is the equal-month-weighted fixed Huber fallback.
    best = min(finite, key=finite.get) if finite else float("inf")
    return float(best), scores


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    ok = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not ok.any():
        return float(np.nanmedian(values)) if np.isfinite(values).any() else 0.0
    values, weights = values[ok], weights[ok]
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    return float(values[np.searchsorted(np.cumsum(weights), 0.5 * weights.sum(), side="left")])


def fit_median_monthly_offset(train: pd.DataFrame) -> float:
    """Median of within-month basket-weighted median residuals y-x."""
    month_offsets = []
    for _, group in train.groupby("period", sort=True):
        residual = group.y.to_numpy(float) - group.x.to_numpy(float)
        weights = pd.to_numeric(group.weight, errors="coerce").fillna(0.0).to_numpy(float)
        month_offsets.append(_weighted_median(residual, weights))
    return float(np.median(month_offsets)) if month_offsets else 0.0


def fit_huber_through_origin(train: pd.DataFrame, c: float = 1.345,
                             iters: int = 60) -> float:
    """Robust one-parameter fit y=beta*x, retaining the raw identity as fallback."""
    x = train.x.to_numpy(float)
    y = train.y.to_numpy(float)
    base = _row_weights(train)
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(base) & (base > 0)
    x, y, base = x[ok], y[ok], base[ok]
    if len(y) < 1 or np.sum(base * x * x) <= 1e-12:
        return 1.0
    base = base / base.sum()
    beta = float(np.sum(base * x * y) / np.sum(base * x * x))
    for _ in range(iters):
        residual = y - beta * x
        median = np.median(residual)
        scale = 1.4826 * np.median(np.abs(residual - median)) + 1e-9
        u = np.abs(residual) / scale
        robust = np.ones_like(u)
        mask = u > c
        robust[mask] = c / u[mask]
        weights = base * robust
        denom = float(np.sum(weights * x * x))
        if denom <= 1e-12:
            break
        new_beta = float(np.sum(weights * x * y) / denom)
        if abs(new_beta - beta) < 1e-10:
            beta = new_beta
            break
        beta = new_beta
    return float(beta)


def fit_hierarchical(train: pd.DataFrame, k: float = HIERARCHICAL_K) -> HierarchicalFit:
    """Empirical-Bayes random intercepts/slopes shrunk toward a pooled regression.

    ``k`` is fixed at 10 prior-month equivalents for this experiment; it is not selected on
    an outer test fold. Within-item estimates with too few periods or a nearly flat x series
    fall back to the pooled fit.
    """
    a0, b0 = _weighted_ols(train)
    alphas: dict[str, float] = {}
    betas: dict[str, float] = {}
    for item, g in train.groupby("item_id", sort=True):
        n = int(g.period.nunique())
        if n >= HIERARCHICAL_MIN_ITEM_MONTHS and float(g.x.std(ddof=0)) >= HIERARCHICAL_MIN_X_SD:
            ai, bi = _weighted_ols(g)
        else:
            ai, bi = a0, b0
        shrink = n / (n + k) if n else 0.0
        alphas[str(item)] = float(shrink * ai + (1 - shrink) * a0)
        betas[str(item)] = float(shrink * bi + (1 - shrink) * b0)
    return HierarchicalFit(a0, b0, alphas, betas, float(k))


def predict_hierarchical(frame: pd.DataFrame, fit: HierarchicalFit) -> np.ndarray:
    a = frame.item_id.astype(str).map(fit.alpha).fillna(fit.alpha0).to_numpy(float)
    b = frame.item_id.astype(str).map(fit.beta).fillna(fit.beta0).to_numpy(float)
    return a + b * frame.x.to_numpy(float)


def _month_residual_measurement(frame: pd.DataFrame, residual: np.ndarray) -> tuple[float, float]:
    w = pd.to_numeric(frame.weight, errors="coerce").fillna(0.0).to_numpy(float)
    w = w / w.sum() if w.sum() > 0 else np.full(len(frame), 1 / max(len(frame), 1))
    z = float(np.sum(w * residual))
    variance = float(np.sum(w * (residual - z) ** 2))
    n_eff = 1.0 / float(np.sum(w ** 2)) if np.sum(w ** 2) else 1.0
    measurement_var = max(variance / max(n_eff, 1.0), STATE_MEASUREMENT_FLOOR ** 2)
    return z, measurement_var


def _prequential_state_observations(train: pd.DataFrame, k: float) -> tuple[np.ndarray, np.ndarray]:
    """Past-only residual measurements: each month is predicted from strictly earlier months."""
    periods = sorted(train.period.astype(str).unique())
    zs: list[float] = []
    rs: list[float] = []
    for j in range(STATE_MIN_TRAIN_MONTHS, len(periods)):
        month = periods[j]
        prior = train[train.period.astype(str) < month]
        observed = train[train.period.astype(str) == month]
        if prior.period.nunique() < STATE_MIN_TRAIN_MONTHS or observed.empty:
            continue
        model = fit_hierarchical(prior, k)
        pred = predict_hierarchical(observed, model)
        z, r = _month_residual_measurement(observed, observed.y.to_numpy(float) - pred)
        zs.append(z)
        rs.append(r)
    return np.asarray(zs, dtype=float), np.asarray(rs, dtype=float)


def _filter_ar1(z: np.ndarray, measurement_var: np.ndarray, phi: float, q: float) -> tuple[float, float]:
    """Scalar Kalman log-likelihood and final filtered state for zero-mean AR(1)."""
    phi = float(np.clip(phi, -0.95, 0.95))
    q = max(float(q), 1e-8)
    a = 0.0
    P = q / max(1.0 - phi * phi, 0.0975)
    ll = 0.0
    for value, r in zip(z, measurement_var):
        ap = phi * a
        Pp = phi * phi * P + q
        S = max(Pp + max(float(r), STATE_MEASUREMENT_FLOOR ** 2), 1e-10)
        e = float(value) - ap
        ll += -0.5 * (np.log(2 * np.pi * S) + e * e / S)
        gain = Pp / S
        a = ap + gain * e
        P = max((1.0 - gain) * Pp, 1e-10)
    return float(ll), float(a)


def fit_state_forecast(z: np.ndarray, measurement_var: np.ndarray) -> dict:
    """Fit a one-factor AR(1) residual state by Kalman likelihood and forecast one step."""
    ok = np.isfinite(z) & np.isfinite(measurement_var)
    z, r = z[ok], measurement_var[ok]
    if len(z) < STATE_MIN_RESIDUAL_MONTHS:
        return {"mean": 0.0, "phi": np.nan, "q": np.nan, "n_state": int(len(z)), "status": "too_few_state_months"}
    level = float(np.average(z, weights=1.0 / np.maximum(r, STATE_MEASUREMENT_FLOOR ** 2)))
    centered = z - level
    var = max(float(np.var(centered)), STATE_MEASUREMENT_FLOOR ** 2)
    q_hi = max(10.0, var * 100.0)

    def objective(theta):
        phi = float(theta[0])
        q = float(np.exp(theta[1]))
        ll, _ = _filter_ar1(centered, r, phi, q)
        return -ll if np.isfinite(ll) else 1e12

    starts = [(0.0, np.log(var * 0.25)), (0.5, np.log(var * 0.5)), (-0.3, np.log(var * 0.5))]
    best = None
    for phi0, logq0 in starts:
        res = minimize(objective, np.array([phi0, logq0]), method="L-BFGS-B",
                       bounds=[(-0.95, 0.95), (np.log(1e-5), np.log(q_hi))])
        if best is None or res.fun < best.fun:
            best = res
    phi = float(best.x[0])
    q = float(np.exp(best.x[1]))
    _, last = _filter_ar1(centered, r, phi, q)
    forecast = level + phi * last
    return {"mean": float(forecast), "phi": phi, "q": q, "n_state": int(len(z)),
            "status": "ok" if best.success else "optimizer_warning"}


def predict_fold(train: pd.DataFrame, test: pd.DataFrame) -> pd.DataFrame:
    """Fit all candidates without reading test y; return predictions joined to test outcomes."""
    if train.empty or test.empty:
        return pd.DataFrame()
    out = test.copy().reset_index(drop=True)
    out["raw"] = out.x.astype(float)

    a, b = _weighted_ols(train)
    out["pooled_ols"] = a + b * out.x.to_numpy(float)

    a, b = fit_huber(train, 1.345)
    out["huber_fixed"] = a + b * out.x.to_numpy(float)

    c, c_scores = choose_huber_c(train)
    a, b = fit_huber(train, c)
    out["huber_nested"] = a + b * out.x.to_numpy(float)
    out["huber_c"] = c
    out["huber_inner_mse"] = min(c_scores.values()) if c_scores else np.nan

    shrink, shrink_scores = choose_identity_shrink(train)
    identity_alpha, identity_beta = fit_huber(train, 1.345)
    out["identity_shrink"] = _identity_shrunk_prediction(
        out, identity_alpha, identity_beta, shrink
    )
    out["identity_shrink_gamma"] = shrink
    out["identity_shrink_inner_mse"] = min(shrink_scores.values()) if shrink_scores else np.nan

    half_life, recency_scores = choose_recency_half_life(train)
    recency_alpha, recency_beta = _fit_huber_with_weights(
        train, 1.345, _recency_weights(train, half_life)
    )
    out["recency_huber"] = recency_alpha + recency_beta * out.x.to_numpy(float)
    out["recency_half_life_months"] = half_life
    out["recency_inner_mse"] = min(recency_scores.values()) if recency_scores else np.nan

    median_offset = fit_median_monthly_offset(train)
    out["median_offset"] = out.x.to_numpy(float) + median_offset
    out["median_offset_value"] = median_offset

    origin_beta = fit_huber_through_origin(train)
    out["huber_through_origin"] = origin_beta * out.x.to_numpy(float)
    out["huber_origin_beta"] = origin_beta

    hier = fit_hierarchical(train, HIERARCHICAL_K)
    static = predict_hierarchical(out, hier)
    out["hierarchical_static"] = static
    z, r = _prequential_state_observations(train, HIERARCHICAL_K)
    state = fit_state_forecast(z, r)
    out["state_correction"] = state["mean"]
    out["state_phi"] = state["phi"]
    out["state_q"] = state["q"]
    out["state_n"] = state["n_state"]
    out["state_status"] = state["status"]
    out["hierarchical_state_space"] = static + state["mean"]
    out["train_periods"] = int(train.period.nunique())
    out["train_rows"] = int(len(train))
    return out


MODEL_COLUMNS = (
    "raw", "pooled_ols", "huber_fixed", "huber_nested", "identity_shrink",
    "recency_huber", "median_offset", "huber_through_origin",
    "hierarchical_static", "hierarchical_state_space",
)


def archive_walk_forward(panel: pd.DataFrame, min_train_months: int = OUTER_MIN_TRAIN_MONTHS) -> pd.DataFrame:
    """Expanding, chronological, source-only folds; historical input-vintage caveat still applies."""
    rows = []
    for month in sorted(panel.period.astype(str).unique()):
        train = panel[panel.period.astype(str) < month]
        test = panel[panel.period.astype(str) == month]
        if train.period.nunique() < min_train_months or test.empty:
            continue
        pred = predict_fold(train, test)
        pred["evaluation"] = "archive_walk_forward"
        pred["test_month"] = month
        rows.append(pred)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def release_replay(targets: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Replay only non-bootstrap official arrivals with inputs fetched before the release date.

    The date-only release record is treated conservatively: same-day source fetches are
    excluded. Targets and source inputs are kept separate until ``predict_fold`` has produced
    its estimates, so the newly released official target cannot enter model fitting.
    """
    targets = live_release_targets() if targets is None else targets.copy()
    if targets.empty:
        return pd.DataFrame(), pd.DataFrame()
    preds: list[pd.DataFrame] = []
    audit: list[dict] = []
    for month, group in targets.groupby("period", sort=True):
        month = str(month)
        cutoff = str(group.first_seen_on.min())
        panel = load_source_panel(as_of=cutoff)
        training = panel[panel.period.astype(str) < month]
        eligible_ids = set(group.item_id.astype(str))
        testing = panel[(panel.period.astype(str) == month) & panel.item_id.astype(str).isin(eligible_ids)]
        safe = testing.max_input_fetched_at.map(
            lambda x: bool(pd.notna(x) and str(x)[:10] < cutoff)
        )
        testing = testing.loc[safe].copy()
        if training.period.nunique() >= OUTER_MIN_TRAIN_MONTHS and not testing.empty:
            p = predict_fold(training, testing)
            p["evaluation"] = "strict_release_replay"
            p["test_month"] = month
            p["release_cutoff"] = cutoff
            preds.append(p)
        audit.append({
            "period": month, "release_cutoff": cutoff, "target_rows_logged": int(len(group)),
            "source_panel_rows_at_cutoff": int(len(panel)), "train_rows": int(len(training)),
            "train_periods": int(training.period.nunique()), "test_rows_source_supported": int(len(panel[(panel.period.astype(str) == month) & panel.item_id.astype(str).isin(eligible_ids)])),
            "test_rows_fetched_before_cutoff": int(len(testing)), "test_items_fetched_before_cutoff": int(testing.item_id.nunique()),
            "latest_test_input_fetch": (testing.max_input_fetched_at.max() if len(testing) else None),
            "status": "scored replay; one target month is descriptive only" if len(testing) else "no source-only test rows available before release cutoff",
        })
    return (pd.concat(preds, ignore_index=True) if preds else pd.DataFrame(), pd.DataFrame(audit))


def _month_weighted_errors(pred: pd.DataFrame, model: str) -> pd.DataFrame:
    rows = []
    for month, g in pred.groupby("period", sort=True):
        w = pd.to_numeric(g.weight, errors="coerce").fillna(0.0).to_numpy(float)
        w = w / w.sum() if w.sum() else np.full(len(g), 1 / len(g))
        e = g.y.to_numpy(float) - g[model].to_numpy(float)
        rows.append({"period": str(month), "mse": float(np.sum(w * e ** 2)),
                     "mae": float(np.sum(w * np.abs(e))), "bias": float(np.sum(w * e)), "n": len(g)})
    return pd.DataFrame(rows)


def _block_gap_ci(monthly: pd.DataFrame, model: str, reps: int = BOOTSTRAP_REPS,
                  block: int = BOOTSTRAP_BLOCK, seed: int = 20261016) -> tuple[float, float, float]:
    base = _month_weighted_errors(monthly, "raw").set_index("period").mse
    cand = _month_weighted_errors(monthly, model).set_index("period").mse
    pair = pd.concat([cand.rename("candidate"), base.rename("raw")], axis=1).dropna()
    if pair.empty:
        return np.nan, np.nan, np.nan
    gap = float(np.sqrt(pair.candidate.mean()) - np.sqrt(pair.raw.mean()))
    n = len(pair)
    if n == 1:
        return gap, np.nan, np.nan
    rng = np.random.default_rng(seed)
    length = min(max(1, int(block)), n)
    draws = np.empty(reps)
    for b in range(reps):
        ix = []
        while len(ix) < n:
            start = int(rng.integers(0, n))
            ix.extend([(start + j) % n for j in range(length)])
        s = pair.iloc[ix[:n]]
        draws[b] = np.sqrt(s.candidate.mean()) - np.sqrt(s.raw.mean())
    return gap, float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def score_predictions(pred: pd.DataFrame) -> pd.DataFrame:
    """Equal-month, basket-weighted metrics and paired moving-block RMSE gaps vs raw input."""
    if pred.empty:
        return pd.DataFrame(columns=["model", "n_months", "n_item_months", "rmse_item_equal", "rmse_basket_month", "mae_basket_month", "bias_basket_month", "gap_vs_raw", "gap_ci95_low", "gap_ci95_high"])
    rows = []
    for model in MODEL_COLUMNS:
        err = pred.y.to_numpy(float) - pred[model].to_numpy(float)
        monthly = _month_weighted_errors(pred, model)
        month_metrics = {"rmse_basket_month": float(np.sqrt(monthly.mse.mean())),
                         "mae_basket_month": float(monthly.mae.mean()),
                         "bias_basket_month": float(monthly.bias.mean())}
        if model == "raw":
            gap, lo, hi = 0.0, 0.0, 0.0
        else:
            gap, lo, hi = _block_gap_ci(pred, model)
        rows.append({"model": model, "n_months": int(pred.period.nunique()), "n_item_months": int(len(pred)),
                     "rmse_item_equal": float(np.sqrt(np.mean(err ** 2))), **month_metrics,
                     "gap_vs_raw": gap, "gap_ci95_low": lo, "gap_ci95_high": hi,
                     "block_length_months": min(BOOTSTRAP_BLOCK, int(pred.period.nunique()))})
    return pd.DataFrame(rows).sort_values("rmse_basket_month").reset_index(drop=True)


def availability_audit(panel: pd.DataFrame, targets: pd.DataFrame | None = None) -> pd.DataFrame:
    """Summarize source fetch vintages without pretending bootstrap official rows are release dates."""
    targets = live_release_targets() if targets is None else targets.copy()
    releases = targets.groupby("period").first_seen_on.min().to_dict() if not targets.empty else {}
    rows = []
    for month, g in panel.groupby("period", sort=True):
        release = releases.get(str(month))
        fetched = pd.to_datetime(g.max_input_fetched_at, utc=True, errors="coerce")
        if release:
            cutoff = pd.Timestamp(release, tz="UTC")
            safe = fetched.notna() & (fetched < cutoff)
            release_status = "non-bootstrap date recorded"
        else:
            safe = pd.Series(False, index=g.index)
            release_status = "no release vintage (official ledger row is bootstrap or absent)"
        rows.append({"period": str(month), "n_source_rows": int(len(g)), "n_rows_with_fetch_time": int(fetched.notna().sum()),
                     "n_source_rows_before_release": int(safe.sum()), "first_source_fetch": fetched.min(),
                     "last_source_fetch": fetched.max(), "official_first_seen_on": release,
                     "release_vintage_status": release_status})
    return pd.DataFrame(rows)


def run_all() -> dict[str, pd.DataFrame]:
    source = load_source_panel()
    archive = archive_walk_forward(source)
    live_targets = live_release_targets()
    strict, audit_live = release_replay(live_targets)
    return {
        "source_panel": source,
        "archive_predictions": archive,
        "archive_scores": score_predictions(archive),
        "strict_predictions": strict,
        "strict_scores": score_predictions(strict),
        "strict_audit": audit_live,
        "vintage_audit": availability_audit(source, live_targets),
    }


def write_outputs(outdir) -> dict[str, pd.DataFrame]:
    from pathlib import Path
    import json

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    tables = run_all()
    for name, frame in tables.items():
        frame.to_csv(out / f"{name}.csv", index=False)
    summary = {
        "protocol": "independent-source-only causal chain-Jevons; official_link and imputation excluded; chronological outer folds; inner-only tuning of Huber clipping, identity shrinkage and recency half-life; robust median offset, through-origin Huber, pooled and hierarchical regressions; one-step AR(1) Kalman residual state",
        "archive_backtest_warning": "source observations are reconstructed from the present archive and may have been fetched after historical test months; these folds are target-leakage-safe but not a real-time vintage backtest",
        "strict_replay_rule": "only non-bootstrap official arrivals; source observations with fetched_at on the same date as release are excluded; train targets strictly precede test month",
        "source_rows": int(len(tables["source_panel"])),
        "source_items": int(tables["source_panel"].item_id.nunique()) if len(tables["source_panel"]) else 0,
        "source_months": int(tables["source_panel"].period.nunique()) if len(tables["source_panel"]) else 0,
        "same_as_official_retained": int(tables["source_panel"].same_as_official.sum()) if len(tables["source_panel"]) else 0,
        "archive_outer_months": int(tables["archive_predictions"].period.nunique()) if len(tables["archive_predictions"]) else 0,
        "strict_test_months": int(tables["strict_predictions"].period.nunique()) if len(tables["strict_predictions"]) else 0,
        "strict_test_rows": int(len(tables["strict_predictions"])),
        "strict_audit": tables["strict_audit"].to_dict("records"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf8")
    return tables
