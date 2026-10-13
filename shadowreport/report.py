"""Build the shadow-vs-actual report for every shadow feed and write it to shadowreport/outputs/."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from . import compare, feeds as F

OUT_DIR = Path(__file__).resolve().parent / "outputs"


def _gate_summary(rows: list[dict]) -> dict:
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    verdicts = set(counts)
    judged = "fail" if "fail" in verdicts else ("pass" if verdicts == {"pass"} else None)
    return dict(n_items=len(rows), verdicts=counts, judged_verdict=judged, n_quotes=len(rows))


def build(root: Path, as_of: dt.date | None = None) -> dict:
    """The full report as a dict: one entry per feed, an overall status, and the rule versions used."""
    root = Path(root)
    as_of = as_of or dt.date.today()
    feed_rows: list[dict] = []
    detail: dict[str, object] = {}
    for feed in F.FEEDS:
        if feed.kind == "price":
            rows = F.price_rows(root, feed, as_of)
            summary = compare.price_summary(rows, feed, as_of)
            detail[feed.id] = rows
        elif feed.kind == "gate":
            rows = F.gate_rows(root)
            summary = _gate_summary(rows)
            summary.update(last_quote=None, days_since_last=None, n_with_reference=sum(1 for r in rows if r["n_overlap"]))
            ds = _gate_days(root, feed, as_of)
            summary.update(days_since_last=ds)
            detail[feed.id] = rows
        else:  # rent
            shadow = F.rent_monthly(root)
            try:
                official = F.official_rent_monthly(root)
            except (FileNotFoundError, KeyError, ValueError) as e:   # no official series: report pending, do not crash
                official = pd.Series(dtype=float)
                detail["official_error"] = f"{type(e).__name__}: {e}"[:200]
            comp = compare.rent_comparison(shadow, official)
            summary = dict(n_quotes=int(_count_rows(root, feed)), last_quote=_last_listed(root, feed),
                           n_with_reference=comp["n_overlap_months"], judged_verdict=comp["verdict"] if comp["judged"] else None)
            summary["days_since_last"] = compare.days_since(summary["last_quote"], as_of)
            summary["comparison"] = comp
            detail[feed.id] = {"shadow_monthly_median": {k: round(float(v), 1) for k, v in shadow.items()}}
        status = compare.feed_status(feed, summary)
        feed_rows.append(dict(id=feed.id, label=feed.label, kind=feed.kind, item=feed.item, reference=feed.reference,
                              freshness_days=feed.freshness_days, notes=feed.notes, status=status, **_public(summary)))
    overall = compare.overall([r["status"] for r in feed_rows])
    return dict(as_of=as_of.isoformat(), overall=overall, feeds=feed_rows,
                rules=dict(price_band_pct=F.PRICE_BAND_PCT, min_overlap_months=F.MIN_OVERLAP_MONTHS,
                           severity=list(F.SEVERITY),
                           note="Report thresholds only. Nothing here changes an index, a switch or a gate."),
                detail=detail)


def _public(summary: dict) -> dict:
    return dict(summary)


def _count_rows(root: Path, feed: F.Feed) -> int:
    return len(F._read(root, feed.path))


def _last_listed(root: Path, feed: F.Feed) -> str | None:
    df = F._read(root, feed.path)
    if df.empty or "listed" not in df.columns:
        return None
    return max(df.listed)


def _gate_days(root: Path, feed: F.Feed, as_of: dt.date) -> int | None:
    df = F._read(root, feed.path)
    if df.empty:
        return None
    return compare.days_since(max(df.date), as_of)


def render_markdown(rep: dict) -> str:
    lines = [f"# Shadow report, as of {rep['as_of']}", "", f"**Overall: {rep['overall']}**", "",
             "| Feed | Kind | Status | Quotes | Last quote | Days since | Reference | Judged | Latest gap |",
             "|---|---|---|---:|---|---:|---|---|---:|"]
    for f in rep["feeds"]:
        judged = f.get("judged_verdict") or "-"
        gap = f.get("latest_gap_pct")
        if gap is None and isinstance(f.get("comparison"), dict):
            gap = f["comparison"].get("gap_cum_pp")
        lines.append(f"| {f['label']} | {f['kind']} | **{f['status']}** | {f.get('n_quotes', 0)} | {f.get('last_quote') or '-'} | "
                     f"{f.get('days_since_last') if f.get('days_since_last') is not None else '-'} | {f['reference'] or 'none'} | "
                     f"{judged} | {'-' if gap is None else gap} |")
    lines += ["", "Gaps: price feeds show the latest % gap to the dated reference; rent shows the cumulative gap in percentage points "
              "over the overlap months.", f"Price band for the report: ±{rep['rules']['price_band_pct']}%. Rent is judged only after "
              f"{rep['rules']['min_overlap_months']} overlap months. {rep['rules']['note']}", ""]
    return "\n".join(lines)


def write(rep: dict, out_dir: Path = OUT_DIR) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp, mp = out_dir / "shadow_report.json", out_dir / "shadow_report.md"
    jp.write_text(json.dumps(rep, indent=2, default=str))
    mp.write_text(render_markdown(rep))
    return jp, mp
