"""Command line: python -m rpi <command>"""
from __future__ import annotations
import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

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
    print(health_report(_conn(args, s), s).to_string(index=False))


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
    args = ap.parse_args(argv)
    args.f(args, load_settings(args.settings))


if __name__ == "__main__":
    main()
