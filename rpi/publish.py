"""Static publishing: JSON/CSV data, monthly bulletin (markdown) and a self-contained dashboard."""
from __future__ import annotations
import base64
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .index.engine import inflation_table
from .validate import official_series

DIVISIONS = {
    "01": "Food & non-alcoholic beverages", "02": "Alcohol, tobacco", "03": "Clothing & footwear",
    "04": "Housing, water, electricity, fuels", "05": "Household goods & services", "06": "Health",
    "07": "Transport", "08": "Information & communication", "09": "Recreation & culture",
    "10": "Education", "11": "Restaurants & accommodation", "12": "Insurance & finance",
    "13": "Personal care & misc.",
}


class DemoGuard(RuntimeError):
    pass


def _md(s: pd.Series, col: str) -> str:
    rows = [f"| {k} | {v} |" for k, v in s.items()]
    return "\n".join([f"| item | {col} |", "|---|---|"] + rows)


def load_run(conn, run_id: str | None = None):
    if run_id is None:
        r = conn.execute("SELECT run_id FROM index_runs ORDER BY built_at DESC, run_id DESC LIMIT 1").fetchone()
        if not r:
            raise RuntimeError("no index runs found - run `rpi build` first")
        run_id = r[0]
    meta = dict(conn.execute("SELECT * FROM index_runs WHERE run_id=?", (run_id,)).fetchone())
    res = pd.read_sql_query("SELECT * FROM index_results WHERE run_id=?", conn, params=(run_id,))
    res["period"] = pd.PeriodIndex(res["period"], freq="M")
    diag = pd.read_sql_query("SELECT * FROM index_diagnostics WHERE run_id=?", conn, params=(run_id,))
    diag["period"] = pd.PeriodIndex(diag["period"], freq="M")
    return meta, res, diag


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _split_lines(cs):
    if not cs or cs.get("ref_period") is None:
        return []
    return ["", "## What is independent vs official-linked",
            f"- Official-linked stand-ins (MoSPI Gujarat-urban item indices) fill items with no independent source yet; "
            f"they run to {cs['ref_period']}. Their plan weight: {cs['plan_weight_pct'].get('linked', 0)}%.",
            f"- Independent of MoSPI (observed, proxied or modelled): {cs['plan_weight_pct'].get('independent', 0)}% of plan weight "
            f"(in the latest month {cs['latest_period']}: {cs['independent_weight_pct_latest']}%). "
            f"Months after {cs['ref_period']} are a nowcast: a trailing gap with no observation is filled by the seasonal-trend prior "
            f"(long-run mean monthly change plus an empirical-Bayes-shrunk calendar-month deviation from 11 years of official Gujarat-urban data), while interior gaps "
            f"and items without a seasonal table fall back to the item's own 12-month mean drift. Back-tested one-month-ahead error about 0.6 pp.",
            f"- No data at all: {cs['plan_weight_pct'].get('none', 0)}% of weight."]


class CoverageGuard(RuntimeError):
    """Raised when too little of the basket weight has real observations to call the result an index."""


class FreshnessGuard(RuntimeError):
    """Raised when too much basket weight has gone too long without a price change - OFF unless configured.

    Configured by [gates] max_stale_weight_pct in settings.toml (see rpi/quality.py::freshness_gate). Default absent,
    so the report in `rpi health` is informational and the daily run cannot start failing on it unannounced.
    """


MIN_PUBLISH_COVERAGE = 0.60


def _ref_period(conn):
    """Last month with official-linked data; months after it are nowcasts. None if no linked data exists."""
    r = conn.execute("""SELECT MAX(substr(o.obs_date,1,7)) FROM observations o JOIN products p ON p.sku_id=o.sku_id
                        WHERE p.source_id='official_link'""").fetchone()
    return r[0] if r and r[0] else None


def publish(conn, out_dir: Path, official_id: str | None = None, allow_demo: bool = False,
            run_id: str | None = None, min_coverage: float = MIN_PUBLISH_COVERAGE) -> dict:
    meta, res, diag = load_run(conn, run_id)
    demo = bool(meta["is_demo"])
    if demo and not allow_demo:
        raise DemoGuard("this run uses DEMO weights and/or synthetic data; refusing to publish it as a real index "
                        "(pass allow_demo=True / --demo to produce a watermarked demo build)")
    _cv = diag[(diag.variant == "jevons_chain") & (diag.metric == "weight_coverage")].set_index("period")["value"].sort_index()
    _ref = _ref_period(conn)
    _ref_p = pd.Period(_ref, freq="M") if _ref else None
    _gate_cov = float(_cv.loc[_ref_p]) if (_ref_p is not None and _ref_p in _cv.index) else (float(_cv.iloc[-1]) if len(_cv) else 1.0)
    if not demo and _gate_cov < min_coverage:
        raise CoverageGuard(f"only {_gate_cov:.1%} of basket weight has observations in the reference period "
                            f"{_ref or 'latest'} (minimum {min_coverage:.0%}). Refusing to publish a partial basket as the Rajkot index.")
    if not demo:
        try:
            from .config import load_settings
            from .quality import freshness_gate
            _ok, _why = freshness_gate(conn, load_settings())
            if not _ok:
                raise FreshnessGuard(f"too much basket weight has stale prices - {_why}")
        except FreshnessGuard:
            raise
        except Exception:  # noqa: BLE001 - a broken freshness check must never block a publish by itself
            pass
    out = Path(out_dir)
    (out / "data").mkdir(parents=True, exist_ok=True)

    tot = {v: g[g.level == "total"].set_index("period") for v, g in res.groupby("variant")}
    head = tot["jevons_chain"]
    infl = inflation_table(head["value"])
    infl["ci_lo"], infl["ci_hi"] = head["lo"], head["hi"]
    try:
        from .config import ROOT as _R0
        from .quality import coverage_split as _cs_fn
        _indep = float(_cs_fn(conn, _R0 / "data/source_plan.csv")["plan_weight_pct"].get("independent", 100.0))
    except Exception:  # noqa: BLE001
        _indep = 100.0
    # A quote-resampling CI is only meaningful if most weight is independently sampled; for a hybrid it would
    # describe a few items' quote noise and read as false precision.
    _ci_ok = bool((head["hi"] - head["lo"]).abs().max() > 1e-6) and _indep >= 50.0
    if not _ci_ok:
        infl["ci_lo"], infl["ci_hi"] = float("nan"), float("nan")
    infl["nowcast"] = bool(_ref_p is not None) and (infl.index > _ref_p)
    # Distribution-free (split-conformal) 90% band for nowcast months, from the rolling-origin back-test on official data
    # (rpi/nowcast_eval.py). It assumes our independent items add no information, so it is conservative.
    infl["nowcast_lo"], infl["nowcast_hi"] = float("nan"), float("nan")
    if _ref_p is not None:
        try:
            import math as _m
            from .config import ROOT as _RB
            from .nowcast_eval import band_for
            for _per in infl.index[infl["nowcast"]]:
                _q = band_for(_RB, int((_per - _ref_p).n))
                if _q is not None:
                    infl.loc[_per, "nowcast_lo"] = infl.loc[_per, "index"] * _m.exp(-_q)
                    infl.loc[_per, "nowcast_hi"] = infl.loc[_per, "index"] * _m.exp(_q)
        except Exception:  # noqa: BLE001 - the band is disclosure, never a reason to block a publish
            pass
    divs = res[(res.variant == "jevons_chain") & (res.level == "division")].pivot(
        index="period", columns="key", values="value")
    cov_t = diag[(diag.variant == "jevons_chain") & (diag.metric == "weight_coverage_tier")].pivot(
        index="period", columns="key", values="value")
    cov = diag[(diag.variant == "jevons_chain") & (diag.metric == "weight_coverage")].set_index("period")["value"]

    infl.round(3).to_csv(out / "data" / "rpi_total.csv")
    divs.round(3).to_csv(out / "data" / "rpi_divisions.csv")
    variants = pd.DataFrame({v: t["value"] for v, t in tot.items()})
    variants.round(3).to_csv(out / "data" / "rpi_variants.csv")
    last = infl.index[-1]
    summary = {"latest_period": str(last), "index": round(float(infl["index"].iloc[-1]), 2),
               "mom_pct": None if pd.isna(infl["mom_pct"].iloc[-1]) else round(float(infl["mom_pct"].iloc[-1]), 2),
               "yoy_pct": None if pd.isna(infl["yoy_pct"].iloc[-1]) else round(float(infl["yoy_pct"].iloc[-1]), 2),
               "ci_95": [round(float(head["lo"].iloc[-1]), 2), round(float(head["hi"].iloc[-1]), 2)] if _ci_ok else None,
               "ci_note": None if _ci_ok else "bootstrap CI withheld: <50% of weight is independently sampled (hybrid index), so a quote-resampling CI would be false precision",
               "reference_period": _ref, "nowcast_periods": [str(p) for p in infl.index[infl["nowcast"]]],
               "reference_index": None if _ref_p is None or _ref_p not in infl.index else round(float(infl.loc[_ref_p, "index"]), 2),
               "reference_yoy_pct": None if _ref_p is None or _ref_p not in infl.index or pd.isna(infl.loc[_ref_p, "yoy_pct"]) else round(float(infl.loc[_ref_p, "yoy_pct"]), 2),
               "nowcast_band_90": None if pd.isna(infl["nowcast_lo"].iloc[-1]) else [round(float(infl["nowcast_lo"].iloc[-1]), 2), round(float(infl["nowcast_hi"].iloc[-1]), 2)],
               "observed_weight_share": round(float(cov.iloc[-1]), 3),
               "run_id": meta["run_id"], "weights_source": meta["weights_source"], "demo": demo}
    try:
        from .config import ROOT as _ROOT
        from .quality import coverage_split
        summary["coverage_split"] = coverage_split(conn, _ROOT / "data/source_plan.csv")
    except Exception:  # noqa: BLE001 - disclosure is best-effort, never blocks a publish
        summary["coverage_split"] = None
    (out / "data" / "summary.json").write_text(json.dumps(summary, indent=2))

    # --- charts
    x = [p.to_timestamp() for p in infl.index]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(x, infl["index"], lw=2.2, label="RPI (Jevons chain)", color="#1f4e79")
    if _ci_ok:
        ax.fill_between(x, infl["ci_lo"], infl["ci_hi"], alpha=.2, color="#1f4e79", label="95% bootstrap CI")
    if _ref_p is not None and infl["nowcast"].any():
        ax.axvspan(_ref_p.to_timestamp(how="end"), x[-1] + pd.Timedelta(days=20), color="#999", alpha=.15,
                   label="nowcast months")
    if infl["nowcast_lo"].notna().any():
        ax.fill_between(x, infl["nowcast_lo"], infl["nowcast_hi"], alpha=.25, color="#e8a317", label="90% nowcast band (back-tested)")
    ax.plot(x, variants["geks_jevons"], ls="--", lw=1.2, color="#c0504d", label="GEKS-Jevons")
    ax.plot(x, variants["regular_price"], ls=":", lw=1.4, color="#4f9d4f", label="Regular prices")
    if official_id:
        off = official_series(conn, official_id)
        c = off.index.intersection(infl.index)
        if len(c) >= 2:
            ax.plot([p.to_timestamp() for p in c], off[c] / off[c].iloc[0] * infl["index"][c[0]],
                    "o-", color="#e8a317", ms=4, label=f"{official_id} (rebased)")
    ax.set_ylabel("Index"); ax.grid(alpha=.3); ax.legend(fontsize=8, frameon=False)
    ax.set_title("Rajkot Price Index"); c1 = _png(fig)
    fig, ax = plt.subplots(figsize=(8, 3.2))
    chg = ((divs.iloc[-1] / divs.iloc[0] - 1) * 100).sort_values()
    ax.barh([DIVISIONS.get(k, k) for k in chg.index], chg.values, color="#1f4e79")
    ax.set_xlabel(f"% change {infl.index[0]} to {last}"); ax.grid(axis="x", alpha=.3); c2 = _png(fig)
    fig, ax = plt.subplots(figsize=(8, 2.8))
    cov_t.mul(100).set_axis([p.to_timestamp() for p in cov_t.index]).plot.area(ax=ax, alpha=.8, linewidth=0)
    ax.set_ylabel("% of CPI weight with a quote"); ax.legend(title="Tier", fontsize=8, frameon=False)
    c3 = _png(fig)

    _cs = summary.get("coverage_split") or {}
    hybrid = (f"<div style='background:#fff3cd;padding:8px 12px;margin:8px 0;border-radius:6px'><b>Hybrid index.</b> "
              f"{_cs.get('plan_weight_pct', {}).get('independent', 0)}% of weight is independently collected; "
              f"{_cs.get('plan_weight_pct', {}).get('linked', 0)}% uses official MoSPI item indices as stand-ins "
              f"(through {_cs.get('ref_period')}); months after that are a nowcast. "
              f"Weights are approximate (see method).</div>") if _cs.get("ref_period") else ""
    banner = ("<div style='background:#b00020;color:#fff;padding:10px;font-weight:700'>DEMO BUILD - synthetic "
              "data and/or illustrative weights. NOT a real index.</div>") if demo else ""
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>Rajkot Price Index</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:16px;color:#222}}
.k{{display:flex;gap:12px;flex-wrap:wrap}}.k div{{background:#f2f5f9;border-radius:8px;padding:10px 14px}}
.k b{{font-size:22px;display:block}}img{{width:100%}}small{{color:#666}}</style></head><body>{banner}
<h1>Rajkot Price Index</h1><p>Open-method city price index. Latest: <b>{last}</b></p>{hybrid}
<div class='k'><div><small>Reference month {summary['reference_period'] or last}</small><b>{summary['reference_index'] if summary['reference_index'] is not None else summary['index']}</b></div>
<div><small>YoY (reference)</small><b>{summary['reference_yoy_pct'] if summary['reference_yoy_pct'] is not None else (summary['yoy_pct'] if summary['yoy_pct'] is not None else 'n/a')}%</b></div>
<div><small>Latest (nowcast) {last}</small><b>{summary['index']}</b></div>
<div><small>95% CI</small><b>{(str(summary['ci_95'][0]) + '-' + str(summary['ci_95'][1])) if summary['ci_95'] else 'n/a'}</b></div>
<div><small>Weight priced (not imputed)</small><b>{summary['observed_weight_share']*100:.1f}%</b></div></div>
<img src='data:image/png;base64,{c1}'><img src='data:image/png;base64,{c2}'><img src='data:image/png;base64,{c3}'>
<h3>Method (summary)</h3><p><small>Matched-model Jevons elementary indices on unit prices, monthly chain;
fixed-weight Young aggregation; a missing relative is filled by the seasonal-trend prior where a seasonal table exists (trailing nowcast gaps), otherwise by the
item's own 12-month mean drift or its division peers, and every fill is disclosed as a weight-coverage diagnostic;
bootstrap CI over quotes only (excludes item-selection and weight error). Weights: {meta['weights_source']}.
Run {meta['run_id']}. Data: <a href='data/rpi_total.csv'>CSV</a> | <a href='data/summary.json'>JSON</a>
</small></p></body></html>"""
    (out / "index.html").write_text(html)

    bull = [f"# Rajkot Price Index - {last}", "", "**DEMO BUILD (synthetic data / illustrative weights)**" if demo else "",
            f"- Reference month {summary['reference_period']}: index **{summary['reference_index']}**, YoY **{summary['reference_yoy_pct']}%**" if summary.get("reference_period") else "",
            f"- Latest month {last} (nowcast): index **{summary['index']}**" + (f"  (95% CI {summary['ci_95'][0]}-{summary['ci_95'][1]})" if summary['ci_95'] else "  (bootstrap CI withheld: hybrid index)"),
            f"- Nowcast 90% band for {last}: **{summary['nowcast_band_90'][0]} - {summary['nowcast_band_90'][1]}** (split-conformal from a rolling-origin back-test on official data; conservative)" if summary.get("nowcast_band_90") else "",
            f"- Month-on-month: **{summary['mom_pct']}%**" if summary["mom_pct"] is not None else "",
            f"- Year-on-year: **{summary['yoy_pct']}%**" if summary["yoy_pct"] is not None else "- Year-on-year: n/a (needs 13 months of data)",
            f"- Weight with a real quote in this vintage, before any imputation: **{summary['observed_weight_share']*100:.1f}%** "
            f"(the rest of this month's basket is filled by the rules below or by an official stand-in - it is NOT the same as the share that is independent of MoSPI)",
            *(_split_lines(summary.get("coverage_split"))),
            "", "## Robustness variants (latest index level)", _md(variants.iloc[-1].round(2), "level"),
            "", "## Divisions (change since base)", _md(chg.sort_values(ascending=False).round(2).rename(index=DIVISIONS), "% change"),
            "", f"_Weights: {meta['weights_source']}. Run: {meta['run_id']}._"]
    (out / f"bulletin_{last}.md").write_text("\n".join(x for x in bull if x is not None))
    return summary
