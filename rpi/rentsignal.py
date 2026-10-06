"""R001 residential rent: independent multi-source SIGNAL, screened against the official rent index (NOT wired).

Why a signal and not a series.  No public dated Rajkot rent series exists (inventory AB).  What does exist, from a different agency and a different
survey than MoSPI, is the Labour Bureau CPI-IW housing group (Labour Bureau's own rent survey for industrial-worker households), which is revised in
half-yearly steps (January and July):
  * all-India housing group, monthly press notes, continuous 2020-2026 (data/labour_bureau/housing_group.csv);
  * the Rajkot centre's own housing group, published in the centre-wise group tables only for Sep 2020 - Mar 2023 (the tables stopped after Mar 2023).
Components considered (all independent of the MoSPI rent survey):
  1. Rajkot-calibrated all-India run-rate (the signal below).   Information: the all-India half-yearly step, scaled by the ratio of Rajkot's own
     cumulative housing growth to the all-India one over the only overlap (2020H2-2023H1).  beta_R = ln(R_end/R_start) / ln(AI_end/AI_start).
  2. Magicbricks listing diary (data/rent_listings.csv): a single cross-section of asking rents (no growth information; asking rents also run about five
     times faster than the stock of rents), so its weight on the trend is zero by construction; it is kept as a level cross-check only.
  3. Rajkot CPI-IW general index and the Gujarat wage orders: tested as drivers in the screen, no incremental information on housing (see inventory AJ).
Fusion is therefore a single bridge, not a Kalman filter: with one informative measurement and no second one to disagree with it, a filter only adds a smoother.
Pre-registration.  beta_R is computed from Labour Bureau data alone, before looking at the MoSPI rent index; nothing is fitted to the official series.
Monthly signal: in every half-year the monthly log growth is beta_R x (that half's all-India step) / 6 (run-rate; the step is taken as known for its own
half, which flatters the signal).  The unchanged proxy gate (>= 6 overlapping months, corr of monthly log changes >= 0.5, |drift| <= 0.10) decides whether
it may count; `compare_halves` reports the half-year accuracy against MoSPI Gujarat-urban rent for 2021-2026 as context.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CODE = "04.1.1.0.2.01"


def load(root) -> pd.DataFrame:
    return pd.read_csv(f"{root}/data/labour_bureau/housing_group.csv").set_index("half")


def beta_rajkot(df: pd.DataFrame, n_boot: int = 2000, seed: int = 7) -> dict:
    """Rajkot / all-India cumulative housing growth ratio over their overlap; bootstrap band over the 5 half-year steps."""
    d = df.dropna(subset=["rajkot_housing"])
    ai, rj = np.log(d.ai_housing.astype(float)).diff().dropna().values, np.log(d.rajkot_housing.astype(float)).diff().dropna().values
    point = float(rj.sum() / ai.sum())
    rng = np.random.default_rng(seed)
    bs = [rj[i].sum() / ai[i].sum() for i in (rng.integers(0, len(ai), len(ai)) for _ in range(n_boot))]
    return dict(beta=round(point, 3), lo=round(float(np.percentile(bs, 5)), 3), hi=round(float(np.percentile(bs, 95)), 3), n_steps=int(len(ai)))


def steps(df: pd.DataFrame) -> pd.Series:
    return np.log(df.ai_housing.astype(float)).diff().dropna()


def monthly_signal(df: pd.DataFrame, beta: float, first: str = "2025-01", last: str = "2026-10") -> pd.Series:
    st = steps(df)
    months = pd.period_range(first, last, freq="M").strftime("%Y-%m")
    lvl, out, cur = 100.0, {}, None
    for m in months:
        half = f"{m[:4]}H{1 if int(m[5:]) <= 6 else 2}"
        if cur is None:
            out[m] = lvl
            cur = half
            continue
        if half in st.index:
            lvl *= float(np.exp(beta * st[half] / 6.0))
        out[m] = lvl
    return pd.Series(out)


def official_rent(root) -> pd.Series:
    o = pd.read_csv(f"{root}/data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    return o[(o.level == "item") & (o.code == CODE)].set_index("period").index_value.sort_index()


def compare_halves(root, beta: float) -> pd.DataFrame:
    """Half-year growth (%): all-India step, the signal (beta x step), MoSPI Gujarat-urban rent (CPI2012 to 2024, CPI2024 after)."""
    df = load(root)
    d12 = pd.read_csv(f"{root}/data/official/mospi_cpi2012_gujarat_urban_items.csv", dtype={"period": str})
    r12 = d12[d12.item == "House Rent, Garage Rent"].drop_duplicates("period").set_index("period").index_value.astype(float).sort_index()
    r24 = official_rent(root)

    def hmean(s, h):
        mm = [f"{h[:4]}-{m:02d}" for m in (range(1, 7) if h[4:] == "H1" else range(7, 13))]
        v = [s[m] for m in mm if m in s.index]
        return float(np.mean(v)) if len(v) >= 5 else np.nan
    st, rows = steps(df), []
    for i in range(1, len(df.index)):
        h, p = df.index[i], df.index[i - 1]
        s = r12 if int(h[:4]) <= 2024 else r24
        ok = int(h[:4]) <= 2024 or int(p[:4]) >= 2025
        g = 100 * np.log(hmean(s, h) / hmean(s, p)) if ok else np.nan
        rows.append(dict(half=h, ai_step_pct=round(100 * st[h], 2), signal_pct=round(100 * beta * st[h], 2), mospi_gujurban_rent_pct=None if g != g else round(g, 2)))
    return pd.DataFrame(rows)


def screen(root) -> dict:
    from .proxy_check import judge
    df = load(root)
    b = beta_rajkot(df)
    o = official_rent(root)
    out = dict(item_id="R001", beta=b, variants={})
    for tag, bt in (("pre-registered (Rajkot-calibrated)", b["beta"]), ("robustness: beta at 5th pct", b["lo"]), ("robustness: beta at 95th pct", b["hi"]), ("robustness: all-India housing as is (beta=1)", 1.0)):
        sig = monthly_signal(df, bt, first=o.index[0], last=o.index[-1])
        j = judge(sig, o)
        lg_s, lg_o = np.log(sig.reindex(o.index)), np.log(o)
        j.update(beta=bt, yoy_signal_pct=round(100 * (lg_s.iloc[-1] - lg_s.iloc[-13]), 2), yoy_official_pct=round(100 * (lg_o.iloc[-1] - lg_o.iloc[-13]), 2),
                 cum_signal_pct=round(100 * (lg_s.iloc[-1] - lg_s.iloc[0]), 2), cum_official_pct=round(100 * (lg_o.iloc[-1] - lg_o.iloc[0]), 2))
        out["variants"][tag] = j
    tv = tvp_beta(df)
    out["tvp"] = {k: v for k, v in tv.items() if k not in ("loglik",)}
    out["tvp"]["loglik"] = tv["loglik"]
    bt = moSPI_free_backtest(df)
    out["mospi_free_backtest"] = {c: round(float(np.sqrt(((bt[c] - bt.actual_pct) ** 2).mean())), 3) for c in ("constant_beta_pct", "tvp_beta_pct", "all_india_pct")}
    for tag, bt_ in (("v2 (chosen after v1 failed): time-varying beta, Kalman", tv["beta"]), ("v2 band: beta - 1.645 se_forward", max(tv["beta"] - 1.645 * tv["se_forward"], 0.0)),
                     ("v2 band: beta + 1.645 se_forward", tv["beta"] + 1.645 * tv["se_forward"])):
        sig = monthly_signal(df, bt_, first=o.index[0], last=o.index[-1])
        j = judge(sig, o)
        lg_s, lg_o = np.log(sig.reindex(o.index)), np.log(o)
        j.update(beta=round(bt_, 3), yoy_signal_pct=round(100 * (lg_s.iloc[-1] - lg_s.iloc[-13]), 2), yoy_official_pct=round(100 * (lg_o.iloc[-1] - lg_o.iloc[-13]), 2),
                 cum_signal_pct=round(100 * (lg_s.iloc[-1] - lg_s.iloc[0]), 2), cum_official_pct=round(100 * (lg_o.iloc[-1] - lg_o.iloc[0]), 2))
        out["variants"][tag] = j
    out["v3"] = screen_v3(root)
    out["v3"]["gate_ceiling"] = gate_ceiling(root)
    out["v4_trend_gate"] = dict(z=Z_TREND, variants=trend_gate_variants(root))
    return out


# ---------------------------------------------------------------------------------------------------------------------------------------------
# v2: time-varying pass-through (Kalman filter on beta).  Chosen AFTER the v1 screen showed the constant beta under-shoots, because Labour Bureau's own
# Rajkot/all-India step ratio visibly drifts up inside the overlap (0.24, 0.13, 0.25, 0.51, 0.55): a fact about Labour Bureau data, not about MoSPI.  Because
# it was chosen after a failed screen, its claim to be out of sample is weaker, and it is judged first on a MoSPI-free test (one-step-ahead forecasts of
# the Rajkot Labour Bureau step) before the MoSPI comparison is shown.
#   r_h = beta_h * a_h + e_h,  e ~ N(0, s2)        (r: Rajkot step, a: all-India step, log points)
#   beta_h = beta_{h-1} + u_h,  u ~ N(0, q2)         (random walk);  beta_0 ~ N(BETA0, P0)
# q2/s2 is chosen by maximising the marginal likelihood over a grid; s2 is concentrated out.  After the last Rajkot step the filtered beta is carried
# forward as a random-walk forecast (its variance grows by q2 per half).
# ---------------------------------------------------------------------------------------------------------------------------------------------
BETA0, P0 = 0.5, 0.25          # diffuse prior centred on a half-way pass-through (fixed before estimation)


def _kf(r: np.ndarray, a: np.ndarray, q_ratio: float):
    """Kalman filter with s2 concentrated out (everything in units of s2). Returns filtered beta, P/s2 and the concentrated log-likelihood."""
    b, P, ll_terms, bs, Ps, preds = BETA0, P0, [], [], [], []
    for rt, at in zip(r, a):
        P_pred = P + q_ratio
        preds.append(b)
        F = at * at * P_pred + 1.0
        v = rt - at * b
        K = P_pred * at / F
        b, P = b + K * v, P_pred - K * at * P_pred
        ll_terms.append((np.log(F), v * v / F))
        bs.append(b); Ps.append(P)
    n = len(r)
    s2 = sum(t[1] for t in ll_terms) / n
    ll = -0.5 * (n * np.log(s2) + sum(t[0] for t in ll_terms))
    return np.array(bs), np.array(Ps), s2, ll, np.array(preds)


def tvp_beta(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["rajkot_housing"])
    a = 100 * np.log(d.ai_housing.astype(float)).diff().dropna().values      # percent units: keeps the observation noise and beta on a comparable scale
    r = 100 * np.log(d.rajkot_housing.astype(float)).diff().dropna().values
    grid = [0.0, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0]
    ll = {q: _kf(r, a, q)[3] for q in grid}
    qb = max(ll, key=ll.get)
    b, P, s2, _, preds = _kf(r, a, qb)
    k = 5.5                                   # mean number of half-years between the end of the overlap (2023H1) and the 2025-26 screen window
    return dict(beta=round(float(b[-1]), 3), se=round(float(np.sqrt(P[-1] * s2)), 3), se_forward=round(float(np.sqrt((P[-1] + k * qb) * s2)), 3), s2=round(float(s2), 4), q_ratio=qb, loglik={str(k): round(v, 2) for k, v in ll.items()},
                path=[round(float(x), 3) for x in b], one_step_pred_beta=[round(float(x), 3) for x in preds])


def moSPI_free_backtest(df: pd.DataFrame) -> pd.DataFrame:
    """One-step-ahead forecasts of the Rajkot Labour Bureau half-year step (no MoSPI data): constant expanding-window beta, TVP beta, and beta = 1."""
    d = df.dropna(subset=["rajkot_housing"])
    a = np.log(d.ai_housing.astype(float)).diff().dropna()
    r = np.log(d.rajkot_housing.astype(float)).diff().dropna()
    rows = []
    for i in range(2, len(a)):             # need two steps to forecast the third onwards
        beta_c = r.iloc[:i].sum() / a.iloc[:i].sum()
        sub = df.dropna(subset=["rajkot_housing"]).iloc[: i + 1]
        beta_t = tvp_beta(sub)["beta"]
        rows.append(dict(half=a.index[i], actual_pct=round(100 * r.iloc[i], 2), constant_beta_pct=round(100 * beta_c * a.iloc[i], 2),
                         tvp_beta_pct=round(100 * beta_t * a.iloc[i], 2), all_india_pct=round(100 * a.iloc[i], 2)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------------------------------------------------------------------------
# v3: panel-validated ensemble.  78 Labour Bureau centres (data/labour_bureau/centre_housing.csv, half-year housing levels 2020H2-2023H1, from the same
# centre-wise group tables as Rajkot) give a MoSPI-free test bed that Rajkot alone (5 steps) could not: every candidate is scored on one-step-ahead forecasts
# of each centre's own step (3 forecast origins x 78 centres).  Findings (inventory AJ.3): single-centre steps are lumpy (forecast RMSE about 1.3-1.5 pp
# against a mean step of 1.5), Rajkot is an unusually smooth centre, and no single model dominates; empirical-Bayes shrinkage helps most and the all-India
# step alone is worst.  With no clear winner the signal is an equal-weight ENSEMBLE of five MoSPI-free step models, the standard robust choice:
#   E1 constant ratio, E2 Kalman time-varying ratio (v2), E3 additive deviation from the all-India step (Rajkot mean), E4 additive deviation shrunk to the
#   all-centre mean by empirical Bayes (lambda from the panel), E5 pooled-parameter Kalman ratio (q, s2, P0 chosen by pooled panel likelihood).
# ---------------------------------------------------------------------------------------------------------------------------------------------
HALVES = ["2020H2", "2021H1", "2021H2", "2022H1", "2022H2", "2023H1"]


def load_panel(root) -> pd.DataFrame:
    return pd.read_csv(f"{root}/data/labour_bureau/centre_housing.csv")


def _panel_steps(root):
    p = load_panel(root)
    S = np.log(p[HALVES].astype(float)).diff(axis=1).iloc[:, 1:] * 100
    S.index = p.centre.str.lower().str.replace(r"[^a-z]", "", regex=True)
    df = load(root)
    a = (np.log(df.loc[HALVES, "ai_housing"].astype(float)).diff().dropna() * 100).values
    return p, S, a


def _kf_plain(r, a, q, b0, P0, s2):
    b, P, ll = b0, P0, 0.0
    for rt, at in zip(r, a):
        Pp = P + q
        F = at * at * Pp + s2
        v = rt - at * b
        K = Pp * at / F
        b, P = b + K * v, Pp - K * at * Pp
        ll += -0.5 * (np.log(F) + v * v / F)
    return b, P, ll


def pooled_tvp_params(S, a, k, b0):
    best = None
    for q in (0.0, 0.01, 0.03, 0.1, 0.3, 1.0):
        for s2 in (0.3, 1.0, 2.0, 3.0):
            for P0 in (0.25, 0.5, 1.0):
                ll = sum(_kf_plain(S.iloc[i, :k].values, a[:k], q, b0, P0, s2)[2] for i in range(len(S)))
                if best is None or ll > best[0]:
                    best = (ll, q, s2, P0)
    return best[1:]


def panel_backtest(root) -> pd.DataFrame:
    """One-step-ahead RMSE (pp) of each step model over all 78 centres at three forecast origins (steps 3, 4, 5)."""
    p, S, a = _panel_steps(root)
    rows = []
    for k in (2, 3, 4):
        hist, ah, tgt, ak = S.iloc[:, :k], a[:k], S.iloc[:, k], a[k]
        dev = hist.sub(ah, axis=1)
        dbar, D = dev.mean(axis=1), float(dev.values.mean())
        within = float(dev.var(axis=1, ddof=1).mean() / k)
        between = max(float(dbar.var(ddof=1)) - within, 1e-6)
        lam = between / (between + within)
        beta = hist.sum(axis=1) / ah.sum()
        b0 = float(beta.mean())
        q, s2, P0 = pooled_tvp_params(S, a, k, b0)
        tv = pd.Series([_kf_plain(hist.iloc[i].values, ah, q, b0, P0, s2)[0] for i in range(len(S))], index=S.index)
        pred = {"all-India step as is": pd.Series(ak, index=S.index), "E1 constant ratio": beta * ak, "E3 additive deviation": ak + dbar,
                "E4 additive, empirical-Bayes shrunk": ak + D + lam * (dbar - D), "E5 pooled-parameter Kalman ratio": tv * ak}
        for m, pr in pred.items():
            rows.append(dict(k=k, model=m, rmse=float(np.sqrt(((pr - tgt) ** 2).mean())), rmse_rajkot=float(abs(pr["rajkot"] - tgt["rajkot"]))))
    r = pd.DataFrame(rows)
    return r.groupby("model", as_index=False).agg(rmse_all_centres=("rmse", "mean"), abs_err_rajkot=("rmse_rajkot", "mean")).round(3)


def ensemble_steps(root) -> pd.DataFrame:
    """Half-year step forecasts (%) of Rajkot housing from each model and the equal-weight ensemble, for every half with an all-India step."""
    df = load(root)
    p, S, a = _panel_steps(root)
    st = steps(df) * 100
    rj = S.loc["rajkot"].values
    b1 = beta_rajkot(df)["beta"]
    b2 = tvp_beta(df)["beta"]
    dev = rj - a
    d3 = float(dev.mean())
    dev_all = S.sub(pd.Series(a, index=S.columns), axis=1)
    dbar = dev_all.mean(axis=1)
    D = float(dev_all.values.mean())
    within = float(dev_all.var(axis=1, ddof=1).mean() / S.shape[1])
    between = max(float(dbar.var(ddof=1)) - within, 1e-6)
    lam = between / (between + within)
    d4 = D + lam * (float(dbar["rajkot"]) - D)
    bm = float((S.sum(axis=1) / a.sum()).mean())
    q, s2, P0 = pooled_tvp_params(S, a, S.shape[1], bm)
    b5 = _kf_plain(rj, a, q, bm, P0, s2)[0]
    # MoSPI-free selection rule (declared before the MoSPI comparison): keep the panel-scored models that beat the all-India-step baseline on the 78-centre panel
    pb = panel_backtest(root).set_index("model").rmse_all_centres
    keep = [k for k, m in (("E1", "E1 constant ratio"), ("E3", "E3 additive deviation"), ("E4", "E4 additive, empirical-Bayes shrunk"), ("E5", "E5 pooled-parameter Kalman ratio"))
            if pb[m] <= pb["all-India step as is"]]
    rows = []
    for h, x in st.items():
        e = {"E1": b1 * x, "E2": b2 * x, "E3": x + d3, "E4": x + d4, "E5": b5 * x}
        v = np.array(list(e.values()))
        sel = np.array([e[k] for k in keep])
        rows.append(dict(half=h, ai_step_pct=round(float(x), 2), **{k: round(float(t), 2) for k, t in e.items()}, ensemble_all_pct=round(float(v.mean()), 2),
                         ensemble_pct=round(float(sel.mean()), 2), model_sd_pct=round(float(v.std(ddof=1)), 2)))
    out = pd.DataFrame(rows)
    out.attrs["params"] = dict(selected=keep, beta_E1=b1, beta_E2=b2, dev_E3=round(d3, 3), dev_E4=round(d4, 3), lam=round(lam, 3), beta_E5=round(float(b5), 3), q=q, s2=s2, P0=P0)
    return out


def ensemble_signal(root, first="2025-01", last="2026-10", col="ensemble_pct") -> pd.Series:
    es = ensemble_steps(root).set_index("half")
    months = pd.period_range(first, last, freq="M").strftime("%Y-%m")
    lvl, out, cur = 100.0, {}, None
    for m in months:
        half = f"{m[:4]}H{1 if int(m[5:]) <= 6 else 2}"
        if cur is None:
            out[m], cur = lvl, half
            continue
        if half in es.index:
            lvl *= float(np.exp(max(es.loc[half, col], 0.0) / 100 / 6.0))
        out[m] = lvl
    return pd.Series(out)


def screen_v3(root) -> dict:
    from .proxy_check import judge
    o = official_rent(root)
    res = {}
    for tag, col in (("panel-selected ensemble (E4+E5)", "ensemble_pct"), ("all-five equal-weight ensemble", "ensemble_all_pct")):
        sig = ensemble_signal(root, first=o.index[0], last=o.index[-1], col=col)
        j = judge(sig, o)
        lg_s, lg_o = np.log(sig.reindex(o.index)), np.log(o)
        j.update(yoy_signal_pct=round(float(100 * (lg_s.iloc[-1] - lg_s.iloc[-13])), 2), yoy_official_pct=round(float(100 * (lg_o.iloc[-1] - lg_o.iloc[-13])), 2),
                 cum_signal_pct=round(float(100 * (lg_s.iloc[-1] - lg_s.iloc[0])), 2), cum_official_pct=round(float(100 * (lg_o.iloc[-1] - lg_o.iloc[0])), 2))
        res[tag] = j
    j = res
    es = ensemble_steps(root)
    return dict(verdict=j, steps=es.to_dict("records"), params=es.attrs["params"], panel_backtest=panel_backtest(root).to_dict("records"))


def gate_ceiling(root) -> dict:
    """Why the monthly-change correlation gate cannot be passed by a trend-type signal: correlation of official monthly rent changes with (a) the v3
    staircase, (b) v3 linearly interpolated between half-year mid-points, (c) the OFFICIAL series' own best linear time trend (an in-sample oracle that
    uses the answer).  If even (c) is far below 0.5 the monthly changes are mostly noise around a flat trend and only a signal that sees that noise can pass."""
    o = official_rent(root)
    do = (np.log(o).diff() * 100).dropna()
    es = ensemble_steps(root).set_index("half").ensemble_pct
    half = lambda m: f"{m[:4]}H{1 if int(m[5:]) <= 6 else 2}"
    stair = pd.Series([es[half(m)] / 6 for m in do.index], index=do.index)
    x = pd.Series({pd.Period(f"{h[:4]}-{'03' if h[-1] == '1' else '09'}", freq="M").ordinal: es[h] / 6 for h in es.index}).sort_index()
    interp = pd.Series(np.interp([pd.Period(m, freq="M").ordinal for m in do.index], x.index, x.values), index=do.index)
    trend = pd.Series(np.arange(len(do), dtype=float), index=do.index)
    return dict(n=len(do), corr_staircase=round(float(do.corr(stair)), 2), corr_interpolated=round(float(do.corr(interp)), 2),
                corr_official_own_linear_trend_oracle=round(float(do.corr(trend)), 2), official_mean_pct=round(float(do.mean()), 3), official_sd_pct=round(float(do.std()), 3),
                official_lag1_autocorr=round(float(do.autocorr(1)), 2))


# ---------------------------------------------------------------------------------------------------------------------------------------------
# v4: a calibrated TREND gate for half-yearly modelled signals (candidate replacement for the monthly-correlation test for R001 ONLY; not adopted).
# Why: the corr test cannot be passed by any trend-type signal (gate_ceiling), and the existing drift cap (0.10 log points = 10 pp) is far looser than the
# whole 19-month rent change (about 3.9 pp), so "corr dropped, drift kept" would pass a FLAT signal and the all-India index.  The tolerance is therefore
# derived from the official series' own noise rather than chosen: its monthly changes have sd s (sampling/rotation noise that no independent signal can
# track), so the cumulative change over n months is uncertain by s*sqrt(n); a signal is accepted if its cumulative change over the overlap, and over the
# latest 12 months, is within z*s*sqrt(m) of official (z = 1.645, fixed in advance).  Size/power are computed below and by Monte Carlo in the tests.
# ---------------------------------------------------------------------------------------------------------------------------------------------
Z_TREND = 1.645


def trend_gate(signal: pd.Series, official: pd.Series, z: float = Z_TREND) -> dict:
    both = pd.concat([signal.rename("p"), official.rename("o")], axis=1).dropna().sort_index()
    lg = np.log(both.astype(float)) * 100
    d_o = lg["o"].diff().dropna()
    s = float(d_o.std())
    n = len(d_o)
    gap_cum = float((lg["p"].iloc[-1] - lg["p"].iloc[0]) - (lg["o"].iloc[-1] - lg["o"].iloc[0]))
    gap_12 = float((lg["p"].iloc[-1] - lg["p"].iloc[-13]) - (lg["o"].iloc[-1] - lg["o"].iloc[-13]))
    tol_cum, tol_12 = z * s * np.sqrt(n), z * s * np.sqrt(12)
    ok = abs(gap_cum) <= tol_cum and abs(gap_12) <= tol_12
    return dict(n=n, official_monthly_sd_pp=round(s, 3), gap_cum_pp=round(gap_cum, 2), tol_cum_pp=round(tol_cum, 2), gap_12m_pp=round(gap_12, 2),
                tol_12m_pp=round(tol_12, 2), verdict="pass" if ok else "fail")


def trend_gate_variants(root) -> dict:
    df = load(root)
    o = official_rent(root)
    tv = tvp_beta(df)
    b = beta_rajkot(df)
    sigs = {"flat (beta=0)": monthly_signal(df, 0.0, first=o.index[0], last=o.index[-1]),
            "v1 constant ratio": monthly_signal(df, b["beta"], first=o.index[0], last=o.index[-1]),
            "v2 Kalman ratio": monthly_signal(df, tv["beta"], first=o.index[0], last=o.index[-1]),
            "v3 panel-selected (E4+E5)": ensemble_signal(root, first=o.index[0], last=o.index[-1], col="ensemble_pct"),
            "v3 all-five equal weight": ensemble_signal(root, first=o.index[0], last=o.index[-1], col="ensemble_all_pct"),
            "all-India housing as is": monthly_signal(df, 1.0, first=o.index[0], last=o.index[-1])}
    return {k: trend_gate(v, o) for k, v in sigs.items()}


def trend_gate_operating_characteristics(s: float, n: int = 19, z: float = Z_TREND, errors=(0.0, 0.5, 1.0, 1.5, 2.0, 3.0)) -> dict:
    """P(accept) when the signal's true cumulative trend error is e pp and the official cumulative carries N(0, s*sqrt(n)) noise (cumulative test only)."""
    from math import erf, sqrt
    Phi = lambda x: 0.5 * (1 + erf(x / sqrt(2)))
    sd, tol = s * np.sqrt(n), z * s * np.sqrt(n)
    return {f"{e:.1f}pp": round(Phi((tol - e) / sd) - Phi((-tol - e) / sd), 3) for e in errors}


def judge_trend(proxy: pd.Series, official: pd.Series) -> dict:
    """proxy_check-compatible verdict dict for the trend gate (corr is not used and is reported as None)."""
    both = pd.concat([proxy.rename("p"), official.rename("o")], axis=1).dropna().sort_index()
    out = {"n_overlap": int(len(both)), "corr": None, "drift": None, "verdict": "pending", "gate": "trend"}
    if len(both) < 14:          # the 12-month leg needs 13 levels; below that the item stays pending
        return out
    g = trend_gate(both["p"], both["o"])
    out.update(drift=round(abs(g["gap_cum_pp"]) / 100, 3), gap_cum_pp=g["gap_cum_pp"], tol_cum_pp=g["tol_cum_pp"], gap_12m_pp=g["gap_12m_pp"],
               tol_12m_pp=g["tol_12m_pp"], verdict=g["verdict"])
    return out
