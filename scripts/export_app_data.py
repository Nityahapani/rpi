"""Export item-level and weight data for the static dashboard in docs/app/.

Read-only on data/rpi.sqlite and registry/items.csv. Writes only
docs/app/data/items.json. Not run by the daily workflow (the workflow is
unchanged); re-run by hand after a refresh to refresh the item view:

    python3 scripts/export_app_data.py

The index, division and status views read docs/data/*.csv/json directly,
which the daily bot already regenerates.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "rpi.sqlite"
REGISTRY = ROOT / "registry" / "items.csv"
OUT = ROOT / "docs" / "app" / "data" / "items.json"
VARIANT = "geks_jevons"


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    run_id = con.execute(
        "select max(run_id) from index_results where variant=? and level='item'",
        (VARIANT,),
    ).fetchone()[0]

    items = {
        r[0]: {"item_id": r[0], "name": r[1], "division": r[2], "tier": r[3], "unit": r[4], "spec": r[5]}
        for r in con.execute("select item_id, name, division, tier, base_unit, spec from items")
    }
    weights = {r[0]: {"weight": r[1], "weight_source": r[2]} for r in con.execute(
        "select item_id, weight, weight_source from weights")}

    series: dict[str, list[list]] = defaultdict(list)
    for period, key, value in con.execute(
        "select period, key, value from index_results "
        "where run_id=? and variant=? and level='item' order by key, period",
        (run_id, VARIANT),
    ):
        series[key].append([period, round(value, 3)])

    reg: dict[str, dict] = {}
    with REGISTRY.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            reg[row["item_id"]] = {
                "source": row.get("primary_source", ""),
                "plan_class": row.get("plan_class", ""),
                "match_quality": row.get("match_quality", ""),
                "official_item": row.get("official_item_name", ""),
            }

    out_items = []
    for iid in sorted(items):
        it = items[iid]
        ser = series.get(iid, [])
        if not ser:
            continue
        w = weights.get(iid, {})
        out_items.append({
            **it,
            **reg.get(iid, {}),
            "weight": w.get("weight"),
            "series": ser,
        })

    payload = {
        "run_id": run_id,
        "weight_source": next(iter(weights.values()), {}).get("weight_source"),
        "variant": VARIANT,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Item index (GEKS-Jevons, base 2025-01 = 100). Exported from the latest run; "
                "re-run scripts/export_app_data.py after a refresh.",
        "items": out_items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out_items)} items, run {run_id}")


if __name__ == "__main__":
    main()
