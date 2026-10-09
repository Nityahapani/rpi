"""Time-series diagnostics for the published series: unit roots, autocorrelation, seasonality.

Pure numpy/scipy (no statsmodels): the implementations are short and the critical values are the standard
response-surface ones for the constant-only and constant+trend cases (Fuller 1976 / MacKinnon 1991 tables, quoted
in the docstrings), which is what a monthly series with ~20-140 observations needs.

* adf  - augmented Dickey-Fuller t on the lagged level (H0: unit root). Lag length by AIC up to `max_lags`.
* kpss - Kwiatkowski-Phillips-Schmidt-Shin LM statistic (H0: level- or trend-stationary).
* ljung_box - portmanteau Q on autocorrelation of the series itself.
* classical_decompose - ratio-to-moving-average (multiplicative or additive), 12-month centred MA.
* seasonal_strength / residual_seasonality - how much of the variation is calendar-driven and whether an F test on
  month dummies still sees seasonality after adjustment.

Used by ``rpi diag`` -> data/official/ts_diagnostics.json, run on the published RPI, the official benchmarks and
the RPI-minus-official gap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

ADF_CRIT = {"c": {0.01: -3.43, 0.05: -2.86, 0.10: -2.57},
            "ct": {0.01: -3.96, 0.05: -3.41, 0.10: -3.12}}
KPSS_CRIT = {"c": {0.01: 0.739, 0.05: 0.463, 0.10: 0.347},
             "ct": {0.01: 0.216, 0.05: 0.146, 0.10: 0.119}}


def _ols(y, X):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    s2 = float(resid @ resid) / max(n - k, 1)
    XtX_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.maximum(np.diag(XtX_inv) * s2, 0.0))
    return beta, se, resid


def adf(x, max_lags: int | None = None, regression: str = "c") -> dict:
    """Augmented Dickey-Fuller t-statistic on the lagged level. H0: unit root (non-stationary).

    regression='c' (constant) or 'ct' (constant + trend). Lag length chosen by AIC; critical values are the
    standard large-sample ones (Fuller/MacKinnon), adequate for T in [20, 200].
    """
    y = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(y)
    if n < 36:
        return {"n": n, "stat": np.nan, "note": "needs >= 36 observations for a meaningful unit-root test"}
    dy = np.diff(y)
    cap = max(1, (n - 2) // 6)                       # never fit more lags than the sample can support
    max_lags = min(int(np.floor((n - 1) ** (1 / 3) * 4)), cap) if max_lags is None else min(int(max_lags), cap)
    best = (np.inf, None)
    for p in range(0, max_lags + 1):
        if n - p - 2 <= 2:
            continue
        yy = dy[p:]
        cols = [y[p:-1], np.ones(len(yy))] + ([np.arange(len(yy))] if regression == "ct" else [])
        # lagged differences dy_{t-1} .. dy_{t-p}, aligned with yy (both length n-1-p)
        cols += [dy[p - j: -j] for j in range(1, p + 1)]
        X = np.column_stack(cols)
        beta, se, resid = _ols(yy, X)
        t = beta[0] / se[0] if se[0] > 0 else np.nan
        k = X.shape[1]
        aic = len(yy) * np.log(max(resid @ resid / len(yy), 1e-300)) + 2 * k
        if aic < best[0]:
            best = (aic, (p, float(t), len(yy), k, float(resid @ resid / len(yy))))
    if best[1] is None:
        return {"n": n, "stat": np.nan, "note": "no estimable lag order"}
    p, t, m, k, s2 = best[1]
    if not np.isfinite(t):
        return {"n": m, "lags": p, "stat": np.nan, "note": "degenerate regression (singular design)"}
    crit = ADF_CRIT[regression]
    return {"n": m, "lags": p, "stat": t, "regression": regression,
            "crit_1pct": crit[0.01], "crit_5pct": crit[0.05], "crit_10pct": crit[0.10],
            "reject_unit_root_5pct": bool(t < crit[0.05]),
            "note": "H0 = unit root; reject => stationary (or at least trend-stationary)"}


def kpss(x, lags: int | None = None, regression: str = "c") -> dict:
    """KPSS LM statistic. H0: (trend-)stationary - the complement of ADF."""
    y = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(y)
    if n < 12:
        return {"n": n, "stat": np.nan, "note": "series too short"}
    t = np.arange(n)
    X = np.column_stack([np.ones(n), t]) if regression == "ct" else np.ones((n, 1))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    if lags is None:
        lags = int(np.floor(4 * (n / 100) ** 0.25))
    s2 = float((resid ** 2).mean())
    for k in range(1, lags + 1):
        w = 1.0 - k / (lags + 1.0)
        s2 += 2.0 * w * float((resid[k:] * resid[:-k]).mean())
    cum = np.cumsum(resid)
    stat = float((cum ** 2).sum() / (n ** 2 * max(s2, 1e-300)))
    crit = KPSS_CRIT[regression]
    return {"n": n, "lags": int(lags), "stat": stat, "regression": regression,
            "crit_1pct": crit[0.01], "crit_5pct": crit[0.05], "crit_10pct": crit[0.10],
            "reject_stationary_5pct": bool(stat > crit[0.05]),
            "note": "H0 = stationary; reject => unit root / stochastic trend"}


def ljung_box(x, lags: int | None = None) -> dict:
    """Portmanteau test on the first `lags` autocorrelations of the (de-meaned) series. H0: no autocorrelation."""
    y = np.asarray(pd.Series(x).dropna(), dtype=float)
    n = len(y)
    if n < 10:
        return {"n": n, "stat": np.nan}
    lags = min(int(10 * np.log10(n)) if lags is None else int(lags), n - 2)
    y = y - y.mean()
    denom = float(y @ y)
    q = 0.0
    for k in range(1, lags + 1):
        rk = float(y[k:] @ y[:-k]) / denom
        q += rk ** 2 / (n - k)
    q *= n * (n + 2)
    return {"n": n, "lags": lags, "stat": float(q), "p": float(stats.chi2.sf(q, df=lags)),
            "reject_no_autocorr_5pct": bool(stats.chi2.sf(q, df=lags) < 0.05)}


def classical_decompose(series: pd.Series, mode: str = "multiplicative") -> pd.DataFrame:
    """Ratio-to-moving-average decomposition with a 12-month centred MA trend (classic Census-I style, no X-13).

    Multiplicative: y = trend * seasonal * irregular, seasonal factors normalised to average 1 over the sample
    (additive: factors normalised to average 0). Monotone series with < 12 months have no trend and yield NaNs.
    """
    y = pd.Series(series).astype(float)
    if not isinstance(y.index, pd.PeriodIndex):
        y.index = pd.PeriodIndex(y.index, freq="M")
    trend = y.rolling(12, center=True, min_periods=12).mean()
    detrended = y / trend if mode == "multiplicative" else y - trend
    months = pd.Index(y.index.month)
    factors = detrended.groupby(months).mean()                     # one value per calendar month
    factors = factors / factors.mean() if mode == "multiplicative" else factors - factors.mean()
    seas = pd.Series([factors.loc[m] for m in y.index.month], index=y.index)
    seas_adj = y / seas if mode == "multiplicative" else y - seas
    irregular = seas_adj / trend if mode == "multiplicative" else seas_adj - trend
    return pd.DataFrame({"series": y, "trend": trend, "seasonal": seas, "seas_adj": seas_adj, "irregular": irregular})


def seasonal_strength(series: pd.Series, mode: str = "multiplicative") -> dict:
    """Wang-Hansen-Huang-style strengths: the share of variation not left in the irregular.

    Fs = max(0, 1 - Var(irregular)/Var(detrended)) and Ft = max(0, 1 - Var(irregular)/Var(SA)) - both in logs for
    the multiplicative decomposition. Fs near 0 means the series has no usable calendar pattern.
    """
    d = classical_decompose(series, mode=mode).dropna()
    if len(d) < 24:
        return {"n": int(len(d)), "note": "too short for a 12-month decomposition"}
    if mode == "multiplicative":
        if (d[["series", "seas_adj", "irregular"]] <= 0).any().any():
            d = d[(d[["series", "seas_adj", "irregular"]] > 0).all(axis=1)]
            if len(d) < 24:
                return {"n": int(len(d)), "note": "not enough strictly positive months for a log decomposition"}
        irr = np.log(d["irregular"])
        sa = np.log(d["seas_adj"])
        detr = np.log(d["series"] / d["trend"])
    else:
        irr, sa = d["irregular"].to_numpy(), d["seas_adj"].to_numpy()
        detr = (d["series"] - d["trend"]).to_numpy()
    fs = max(0.0, 1.0 - np.var(irr) / np.var(detr)) if np.var(detr) > 0 else 0.0
    ft = max(0.0, 1.0 - np.var(irr) / np.var(sa)) if np.var(sa) > 0 else 0.0
    return {"n": int(len(d)), "seasonal_strength": float(fs), "trend_strength": float(ft)}


def residual_seasonality(series: pd.Series, lags: int = 24) -> dict:
    """F test that 11 monthly dummies are jointly zero in the de-trended series, plus a Ljung-Box on its changes.

    For an adequate seasonal adjustment the month dummies should be jointly insignificant. This is the standard
    'residual seasonality' companion to the decomposition; it does not replace an X-13 quality review.
    """
    y = pd.Series(series).astype(float).dropna()
    if len(y) < 36:
        return {"n": int(len(y)), "note": "too short"}
    idx = y.index.month if isinstance(y.index, pd.PeriodIndex) else pd.DatetimeIndex(y.index).month
    t = np.arange(len(y))
    X = np.column_stack([np.ones(len(y)), t])
    resid = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]
    D = np.column_stack([(idx == m).astype(float) for m in range(2, 13)])
    Xd = np.column_stack([np.ones(len(resid)), D])
    b, *_ = np.linalg.lstsq(Xd, resid, rcond=None)
    res_d = resid - Xd @ b
    rss_d, rss_0 = float(res_d @ res_d), float(resid @ resid)
    df1, df2 = D.shape[1], len(resid) - Xd.shape[1]
    F = ((rss_0 - rss_d) / df1) / (rss_d / df2)
    p = float(stats.f.sf(F, df1, df2))
    return {"n": len(y), "F": float(F), "df": [df1, df2], "p": p,
            "residual_seasonality_5pct": bool(p < 0.05),
            "note": "H0: no remaining calendar pattern after trend removal; rejection flags a series that needs seasonal adjustment"}


def report(series: pd.Series, lags: int = 24) -> dict:
    """The standard battery for one monthly series: unit roots, autocorrelation, seasonality."""
    return {"n": int(pd.Series(series).dropna().shape[0]),
            "adf": adf(series), "kpss": kpss(series),
            "ljung_box_level": ljung_box(series, lags),
            "ljung_box_diff": ljung_box(pd.Series(series).diff(), lags),
            "seasonal_strength": seasonal_strength(series),
            "residual_seasonality": residual_seasonality(series, lags)}
