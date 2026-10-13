"""python -m shadowreport report | check | feeds

report  build the report, write shadowreport/outputs/shadow_report.{json,md}, print the summary (exit 0)
check   same, but exit 1 when the overall status is fail, out_of_band or stale (for scheduled use)
feeds   list the registered shadow feeds
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import feeds as F
from .report import build, render_markdown, write

ROOT = Path(__file__).resolve().parent.parent
BLOCKING = {"fail", "out_of_band", "stale"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m shadowreport", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("report", "check"):
        p = sub.add_parser(name)
        p.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today)")
        p.add_argument("--root", default=str(ROOT), help="repo root (default: this repo)")
        p.add_argument("--out", default=None, help="output directory (default: shadowreport/outputs)")
    sub.add_parser("feeds")
    a = ap.parse_args(argv)

    if a.cmd == "feeds":
        for f in F.FEEDS:
            print(f"{f.id:14} {f.kind:5} item={f.item or '-':5} ref={f.reference or 'none'}  ({f.path})")
        return 0

    rep = build(Path(a.root), F.as_of_date(a.as_of))
    jp, mp = write(rep, Path(a.out) if a.out else Path(a.root) / "shadowreport" / "outputs")
    print(render_markdown(rep))
    print(f"wrote {jp} and {mp}")
    if a.cmd == "check" and rep["overall"] in BLOCKING:
        print(f"check: overall status {rep['overall']}", file=sys.stderr)
        return 1
    return 0
