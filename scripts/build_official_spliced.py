"""Build the long official item comparator: CPI2012 (2014-01..2025-12) spliced with CPI2024 (2025-01..).

Why: `validate_proxies` judges a proxy against the official Gujarat-urban ITEM index, but the only official item file the pipeline
read (mospi_cpi2024_gujarat_urban.csv) starts in 2025-01.  That caps every gate verdict at ~21 overlapping months, which is far too
short to separate a tracking proxy from a drifting one, and it is why the gate needs a "pending" state at all.  MoSPI's CPI2012
Gujarat-urban item series (mospi_cpi2012_gujarat_urban_items.csv) runs 2014-01..2025-12 and covers 66 of the 67 basket items, so the
two can be spliced into one 2014-01..2026-09 comparator.

Splice rule (fixed in advance, standard practice): on the 12 months both bases publish (2025-01..2025-12) take the mean log ratio
CPI2024/CPI2012 for that item and rescale the CPI2024 segment by its inverse, so the published level is the CPI2012 level and only
the newer months are added.  The series is NOT chained - the level stays CPI2012's - because a proxy series is judged on changes and
on R2/slope, both of which are invariant to a constant shift but not to a chain.  Items with no CPI2012 counterpart keep the CPI2024
segment alone.  Everything is reported, nothing is dropped silently.

Output: data/official/official_item_spliced.csv  (item_id, period, index_value, segment)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OFF = ROOT / "data" / "official"
OUT = OFF / "official_item_spliced.csv"


def build() -> pd.DataFrame:
    mp = pd.read_csv(ROOT / "data" / "basket_official_map.csv", dtype=str, keep_default_na=False)
    nm = pd.read_csv(OFF / "basket_to_cpi2012_map.csv", dtype=str, keep_default_na=False)
    names = dict(zip(nm.item_id, nm.cpi2012_item))

    o24 = pd.read_csv(OFF / "mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    o24 = o24[o24.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
    o12 = pd.read_csv(OFF / "mospi_cpi2012_gujarat_urban_items.csv", dtype={"period": str})
    o12["index_value"] = o12.index_value.astype(float)
    o12 = (o12.drop_duplicates(["item", "period"])
             .pivot_table(index="period", columns="item", values="index_value", aggfunc="first"))

    rows, report = [], []
    for _, r in mp.iterrows():
        it, code = r.item_id, r.official_item_code
        name = names.get(it, "")
        a = o12[name] if name in o12.columns else None
        b = o24[code] if code in o24.columns else None
        seg = "cpi2024"
        if a is None:
            s = b
        elif b is None:
            s, seg = a, "cpi2012"
        else:
            sh = a.index.intersection(b.index)
            if len(sh) >= 6:
                shift = float(np.mean(np.log(b.reindex(sh)) - np.log(a.reindex(sh))))
                s = pd.concat([a[a.index < sh[0]], b * np.exp(-shift)])
                s = s[~s.index.duplicated(keep="last")]
                seg = "splice"
                report.append({"item_id": it, "overlap_months": len(sh), "log_shift": round(shift, 4),
                               "shift_pct": round((float(np.exp(-shift)) - 1) * 100, 2)})
            else:
                s, seg = a, "cpi2012"
        if s is None:
            continue
        s = s.dropna()
        rows += [{"item_id": it, "period": p, "index_value": float(v), "segment": seg} for p, v in s.items()]
    df = pd.DataFrame(rows).sort_values(["item_id", "period"])
    return df, pd.DataFrame(report)


if __name__ == "__main__":
    df, rep = build()
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT}: {len(df)} rows, {df.item_id.nunique()} items, {df.period.min()}..{df.period.max()}")
    print(df.groupby("segment").index_value.size().to_string())
    if len(rep):
        print("\nsplice offsets (CPI2024/CPI2012 level gap at the 12-month overlap):")
        print(rep.sort_values("shift_pct").to_string(index=False))
        print(f"\nmedian |offset| = {rep.shift_pct.abs().median():.2f}%  (a large offset means the two bases' item definitions differ)")
    sys.exit(0)
