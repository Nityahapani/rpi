"""Command line: python -m rpi <command>"""
from __future__ import annotations
import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import db, ingest
from .config import ROOT, load_settings, resolve
from .collectors.base import PoliteClient, SnapshotStore
from .collectors.agmarknet import AgmarknetCollector
from .collectors.csv_import import CsvImportCollector
from .collectors.tariff_events import TariffEventCollector
from .index.engine import run_index, inflation_table
from .publish import publish, DemoGuard, CoverageGuard
from .quality import health_report
from .validate import load_official, official_series, compare, record_nowcast, score_nowcasts


def _conn(args, s):
    return db.connect(Path(args.db) if args.db else resolve(s, "db"))


def cmd_init(args, s):
    conn = _conn(args, s)
    n = ingest.load_basket(conn, pd.read_csv(resolve(s, "basket"), dtype={"division": str}))
    try:
        w = ingest.load_weights(conn, pd.read_csv(args.weights or resolve(s, "weights")))
    except ValueError as e:
        print(f"WEIGHTS NOT LOADED: {e}")
        w = 0
    off = ROOT / "data" / "official" / "official_series.csv"
    if off.exists():
        load_official(conn, pd.read_csv(off))
    print(f"initialised: {n} items, {w} weights")


def cmd_ingest(args, s):
    conn = _conn(args, s)
    if args.source == "agmarknet":
        client = PoliteClient(s["collectors"]["user_agent"], s["collectors"]["min_delay_seconds"],
                              respect_robots=False)   # official API intended for programmatic use
        col = AgmarknetCollector(client, SnapshotStore(conn, resolve(s, "raw")), s,
                                 pd.read_csv(resolve(s, "commodity_map")))
    elif args.source == "tariff":
        col = TariffEventCollector(resolve(s, "tariff_events"))
    elif args.source == "csv":
        col = CsvImportCollector(args.path)
    else:
        raise SystemExit("unknown source")
    print(ingest.run_collector(conn, col))


def cmd_build(args, s):
    conn = _conn(args, s)
    try:
        run = run_index(conn, s)
    except RuntimeError as e:
        raise SystemExit(f"BUILD SKIPPED: {e}")
    t = inflation_table(run.variants["jevons_chain"].total)
    print(f"run {run.run_id}  demo={run.is_demo}")
    print(t.tail(6).round(2).to_string())
    cov = run.variants['jevons_chain'].coverage.iloc[-1]
    print(f"observed weight share (latest): {cov:.1%}")
    if cov < 0.6:
        print("WARNING: PARTIAL BASKET - this number is NOT the Rajkot price index; most items have no real data yet.")


def cmd_validate(args, s):
    conn = _conn(args, s)
    from .publish import load_run
    meta, res, _ = load_run(conn)
    mine = res[(res.variant == "jevons_chain") & (res.level == "total")].set_index("period")["value"]
    for sid in [r[0] for r in conn.execute("SELECT DISTINCT series_id FROM official_series")]:
        print(sid, compare(mine, official_series(conn, sid)), score_nowcasts(conn, sid))


def cmd_nowcast(args, s):
    conn = _conn(args, s)
    from .publish import load_run
    _, res, _ = load_run(conn)
    mine = res[(res.variant == "jevons_chain") & (res.level == "total")].set_index("period")["value"]
    print(record_nowcast(conn, args.series, mine))


def cmd_publish(args, s):
    conn = _conn(args, s)
    out = Path(args.out) if args.out else resolve(s, "out")
    try:
        print(publish(conn, out, args.official, allow_demo=args.demo))
    except (DemoGuard, CoverageGuard) as e:
        raise SystemExit(f"BLOCKED: {e}")


def cmd_health(args, s):
    conn = _conn(args, s)
    print(health_report(conn, s).to_string(index=False))
    from .quality import freshness_report
    fresh, summ = freshness_report(conn, s)
    print("\nitem freshness (stalest heavy items first):")
    print(fresh.head(8).to_string(index=False))
    print(f"no price change for >{summ['stale_change_days_threshold']}d: {summ['stale_weight_pct']}% of weight "
          f"({summ['n_stale']}/{summ['n_items']} items); feeds quiet >{summ['stale_obs_days_threshold']}d: "
          f"{summ['stale_feed_weight_pct']}% of weight")


def cmd_daily(args, s):
    """Production orchestration: collect -> build -> validate -> publish. Failures are isolated."""
    args.source = "tariff"; cmd_ingest(args, s)
    args.source = "agmarknet"; cmd_ingest(args, s)
    cmd_build(args, s)
    cmd_health(args, s)
    cmd_publish(args, s)


def cmd_demo(args, s):
    """Synthetic end-to-end run into a separate DB and docs_demo/."""
    from .collectors.synthetic import generate
    dbp = ROOT / "data" / "demo.sqlite"
    dbp.unlink(missing_ok=True)
    conn = db.connect(dbp)
    basket = pd.read_csv(resolve(s, "basket"), dtype={"division": str})
    ingest.load_basket(conn, basket)
    ingest.load_weights(conn, pd.read_csv(ROOT / "data" / "weights_demo.csv"))      # demo always uses clearly-labelled DEMO weights
    obs, _, _ = generate(basket, dt.date(2026, 1, 1), dt.date(2026, 9, 30), seed=args.seed)

    class _C:
        source_id = "synthetic"
        def collect(self, d): return obs
    print(ingest.run_collector(conn, _C()))
    run = run_index(conn, s)
    print(inflation_table(run.variants["jevons_chain"].total).round(2).to_string())
    out = ROOT / "docs_demo"
    print(publish(conn, out, None, allow_demo=True))
    print("health:\n", health_report(conn, s, dt.date(2026, 9, 30)).to_string(index=False))


def cmd_audit(args, s):
    from .audit import run_audit
    r = run_audit(ROOT)
    print("basket sufficiency:", {k: round(v, 3) for k, v in r["basket"].items()})
    for it, c in r["items"].items():
        print(it, c)
    print("report: data/official/audit_report.md")


def cmd_refresh(args, s):
    from .refresh import run_refresh
    out = run_refresh(ROOT, s, offline=args.offline, bootstrap_reps=args.reps)
    for st in out["steps"]:
        print(f"{st['status']:8s} {st['step']:28s} {st['detail'][:140]}")
    print("coverage:", out["coverage"])


def cmd_probe(args, s):
    from .probe import run_probe
    print(run_probe(ROOT).to_string(index=False))


def cmd_eval(args, s):
    """Deep pseudo-real-time replay of the nowcast rules + statistical tests + calibration -> evaluation.json."""
    import pandas as pd
    from . import panel_eval
    horizons = tuple(int(h) for h in str(args.horizons).split(","))
    first = pd.Period(args.first, "M") if args.first else panel_eval.SELECT_FIRST
    res = panel_eval.run_and_write(ROOT, horizons=horizons, first=first, conn=_conn(args, s))
    for line in panel_eval.summary_lines(res):
        print(line)
    print("report: data/official/evaluation.json, data/official/replay_index_errors.csv")


def cmd_diag(args, s):
    """Unit roots / autocorrelation / seasonality of the published series -> ts_diagnostics.json (+ SA series).

    Series covered: the published RPI, the official Gujarat-urban general index, the MoM gap between them, and - for
    the unit-root/seasonality battery, which needs decades not months - the basket-weighted official 2012 panel over
    its full 144-month span (the long-horizon analogue of the RPI built from the same items and weights).
    """
    import datetime as _dt
    import json
    from .tsdiag import report, classical_decompose
    from . import panel_eval
    conn = _conn(args, s)
    from .publish import load_run
    _, res, _ = load_run(conn)
    mine = res[(res.variant == "jevons_chain") & (res.level == "total")].set_index("period")["value"]
    mine.index = pd.PeriodIndex(mine.index, freq="M")
    out = {"generated": _dt.date.today().isoformat(), "series": {}}

    # long-horizon official analogue: basket weights applied to the 2012-base official item indices, averaged over
    # the lines that report in each month (same handling as the engine: missing lines do not enter the average)
    panel = panel_eval.load_panel(ROOT)
    lv = np.exp(panel["L"][panel["lines"]])
    ww = panel["line_w"].reindex(panel["lines"]).fillna(0.0)
    den = (lv.notna() * ww).sum(axis=1)
    long_series = (lv.fillna(0.0) * ww).sum(axis=1) / den.replace(0.0, np.nan)
    long_series = long_series.dropna()
    long_series = long_series / long_series.iloc[0] * 100

    series = {"rpi_total": mine, "panel_official_long": long_series}
    from .validate import official_series as _off
    if "CPI2024_GUJARAT_URBAN_GENERAL" in [r[0] for r in conn.execute("SELECT DISTINCT series_id FROM official_series")]:
        series["official_gujarat_urban"] = _off(conn, "CPI2024_GUJARAT_URBAN_GENERAL")
    for key, sr in series.items():
        out["series"][key] = report(sr)
    off = series.get("official_gujarat_urban")
    if off is not None:
        common = mine.index.intersection(off.index)
        if len(common) > 12:
            gap = (mine[common].pct_change() - off[common].pct_change()).dropna() * 100
            out["series"]["gap_mom_rpi_minus_official"] = report(gap)
    dec = classical_decompose(mine).round(4)
    dec.index.name = "period"
    dec.to_csv(ROOT / "data/official/rpi_total_sa.csv")
    (ROOT / "data/official/ts_diagnostics.json").write_text(json.dumps(out, indent=1, default=str))

    def fmt(r):
        if "adf" not in r or r["adf"].get("stat") != r["adf"].get("stat"):
            return f"n={r.get('n', 0):3d}  (unit-root/seasonality battery needs >= 36 obs)"
        ss = r["seasonal_strength"].get("seasonal_strength")
        ss = f"{ss:.2f}" if isinstance(ss, float) and ss == ss else "n/a"
        return (f"n={r['n']:3d}  ADF {r['adf']['stat']:8.2f} (5% {r['adf']['crit_5pct']}: "
                f"{'stationary' if r['adf']['reject_unit_root_5pct'] else 'unit root'})  "
                f"KPSS {r['kpss']['stat']:6.3f} ({'stationary' if not r['kpss']['reject_stationary_5pct'] else 'unit root'})  "
                f"LB(12) on changes p={r['ljung_box_diff']['p']:.3f}  seasonal strength {ss}")
    for key, r in out["series"].items():
        print(f"{key:32s} {fmt(r)}")
    print("seasonally adjusted series: data/official/rpi_total_sa.csv; report: data/official/ts_diagnostics.json")


def cmd_uncertainty(args, s):
    """Three-component bootstrap decomposition of the published CI -> uncertainty_decomposition.json.

    Inputs come from engine.published_band_inputs - exactly what run_index feeds the published band (price-updated
    weights, quotes from the base month, the seasonal-trend prior) - so the quotes-only component IS the published
    band at equal reps, and all levels are on the published scale (base month = 100).
    """
    import json
    import pandas as pd
    from .index.engine import published_band_inputs
    from .index.uncertainty import bootstrap_replicates, quantiles, mc_quantile_error, variance_decomposition
    conn = _conn(args, s)
    b = published_band_inputs(conn, s)
    periods = b["periods"]
    if b["base"] != periods[0]:
        # aggregate() chains from 100 at the first month; the published band is rebased to the base month
        raise SystemExit(f"rpi uncertainty: the quote panel starts {periods[0]}, not at the base month {b['base']}; "
                         "levels would not be on the published scale")
    from .publish import _ref_period
    ref = _ref_period(conn)
    tail = pd.Period(ref, "M") + 1 if ref else None      # items are genuinely unobserved only after the last official month
    reps = int(args.reps or 500)
    runs = {}
    plan = (("quotes", ("quotes",), None), ("items_all", ("items",), None), ("items_tail", ("items",), tail),
            ("weights", ("weights",), None), ("all_tail", ("quotes", "items", "weights"), tail))
    for name, comps, mfrom in plan:
        print(f"  bootstrap {name:9s} reps={reps}{'' if mfrom is None else ' (mask from ' + str(mfrom) + ')'} ...", flush=True)
        runs[name] = bootstrap_replicates(b["arrays"], periods, b["items"], b["weights"], reps, components=comps,
                                          min_matched=b["min_matched"], clip=b["clip"], impute=b["impute"],
                                          seasonal=b["seasonal"], weight_sigma=args.weight_sigma, mask_from=mfrom)
    dec = variance_decomposition({"quotes": runs["quotes"], "items": runs["items_tail"],
                                  "weights": runs["weights"], "all": runs["all_tail"]}, period_index=-1)
    lo_all, hi_all = quantiles(runs["all_tail"], (2.5, 97.5))
    lo90, hi90 = quantiles(runs["all_tail"], (5.0, 95.0))
    lo_q, hi_q = quantiles(runs["quotes"], (2.5, 97.5))   # the historical (quotes-only) band, for comparison
    mc = mc_quantile_error(runs["all_tail"], splits=100)
    var_all_months = float(np.nanvar(runs["items_all"][:, -1]))
    var_tail = float(np.nanvar(runs["items_tail"][:, -1]))
    out = {"generated": pd.Timestamp.utcnow().date().isoformat(), "reps": reps, "weight_sigma": args.weight_sigma,
           "latest_period": str(periods[-1]), "base_period": str(b["base"]),
           "mask_from": str(tail),
           "items_variance_all_months_vs_tail": {"all_months": round(var_all_months, 4), "tail_only": round(var_tail, 4)},
           "ci_95_all_components": [round(float(lo_all[-1]), 4), round(float(hi_all[-1]), 4)],
           "ci_95_quotes_only": [round(float(lo_q[-1]), 4), round(float(hi_q[-1]), 4)],
           "ci_90_all_components": [round(float(lo90[-1]), 4), round(float(hi90[-1]), 4)],
           "mc_error_of_quantiles": {"2.5pct": round(float(mc["2.5"][-1]), 5), "97.5pct": round(float(mc["97.5"][-1]), 5)},
           "decomposition": {k: (round(v, 6) if isinstance(v, float) else v) for k, v in dec["var"].items()},
           "shares_pct": {k: (None if v != v else round(v, 1)) for k, v in dec["shares_pct"].items()},
           "additivity_gap_pct": round(float(dec["additivity_gap_pct"]), 1),
           "note": dec["note"]}
    (ROOT / "data/official/uncertainty_decomposition.json").write_text(json.dumps(out, indent=1))
    print(f"latest {out['latest_period']}: CI95 all components {out['ci_95_all_components']} "
          f"(width {float(hi_all[-1] - lo_all[-1]):.3f})  vs quotes only {out['ci_95_quotes_only']} "
          f"(width {float(hi_q[-1] - lo_q[-1]):.3f})")
    print("component shares of the marginal variance:", out["shares_pct"], f"(additivity gap {out['additivity_gap_pct']}%)")
    print("MC error of the 2.5% quantile:", out['mc_error_of_quantiles']['2.5pct'])
    print(f"items component, all months vs tail only: var {var_all_months:.3f} vs {var_tail:.3f}")
    print("report: data/official/uncertainty_decomposition.json")


def cmd_shadow(args, s):
    """SHADOW candidates - Rajkot web shops, the field diary, listings-based rent: what accrues, how it compares, what could be switched."""
    from . import rentlistings, shadow
    from .collectors import field_diary
    if args.sheet:
        print("field-diary collection sheet:", field_diary.write_sheet(ROOT).relative_to(ROOT))
    conn = _conn(args, s)
    for line in shadow.summary_lines(shadow.screen(ROOT, conn)):
        print(line)
    raw = field_diary.load(ROOT)
    if len(raw):
        items = set(pd.read_csv(ROOT / "registry/items.csv", dtype=str, usecols=["item_id"]).item_id)
        ok, problems = field_diary.validate(raw, items)
        print(f"field diary: {len(ok)}/{len(raw)} rows accepted" + "".join(f"\n  ! {p}" for p in problems[:25]))
    r = rentlistings.screen(ROOT)
    months = ", ".join(f"{m['month']} n={m['n']}{' survivor' if m['survivor'] else ''}{'' if m['complete'] else ' (in progress)'}"
                       for m in r.get("months", []))
    print(f"rent, R001 candidate: {r.get('n_listings_used', 0)} listings by month listed: {months}")
    print(f"  listing share of the 12-month window {r.get('listing_share_latest', 0):.0%}; trend gate "
          f"{r.get('gate_vs_official', {}).get('verdict')}; {r['verdict']}")
    print("reports: data/official/shadow_sources.json, data/official/rent_listings_index.json")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rpi")
    ap.add_argument("--db"); ap.add_argument("--settings")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("--weights"); p.set_defaults(f=cmd_init)
    p = sub.add_parser("ingest"); p.add_argument("source", choices=["agmarknet", "tariff", "csv"])
    p.add_argument("--path"); p.set_defaults(f=cmd_ingest)
    sub.add_parser("build").set_defaults(f=cmd_build)
    sub.add_parser("validate").set_defaults(f=cmd_validate)
    p = sub.add_parser("nowcast"); p.add_argument("series"); p.set_defaults(f=cmd_nowcast)
    p = sub.add_parser("publish"); p.add_argument("--out"); p.add_argument("--official")
    p.add_argument("--demo", action="store_true"); p.set_defaults(f=cmd_publish)
    sub.add_parser("health").set_defaults(f=cmd_health)
    sub.add_parser("audit").set_defaults(f=cmd_audit)
    sub.add_parser("probe").set_defaults(f=cmd_probe)
    p = sub.add_parser("refresh"); p.add_argument("--offline", action="store_true"); p.add_argument("--reps", type=int)
    p.set_defaults(f=cmd_refresh)
    p = sub.add_parser("daily"); p.add_argument("--out"); p.add_argument("--official", default="CPIIW_RAJKOT")
    p.add_argument("--demo", action="store_true"); p.set_defaults(f=cmd_daily)
    p = sub.add_parser("demo"); p.add_argument("--seed", type=int, default=11); p.set_defaults(f=cmd_demo)
    p = sub.add_parser("eval"); p.add_argument("--first", help="first origin, YYYY-MM (default 2018-01)")
    p.add_argument("--horizons", default="1,2,3"); p.set_defaults(f=cmd_eval)
    sub.add_parser("diag").set_defaults(f=cmd_diag)
    p = sub.add_parser("shadow"); p.add_argument("--sheet", action="store_true", help="rewrite data/field_diary/sheet.csv")
    p.set_defaults(f=cmd_shadow)
    p = sub.add_parser("uncertainty"); p.add_argument("--reps", type=int, default=500)
    p.add_argument("--weight-sigma", type=float, default=0.10, dest="weight_sigma"); p.set_defaults(f=cmd_uncertainty)
    args = ap.parse_args(argv)
    args.f(args, load_settings(args.settings))


if __name__ == "__main__":
    main()
