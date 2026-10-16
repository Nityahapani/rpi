"""Build the long official item comparator from CPI2012 and CPI2024.

The CPI2012 Gujarat-urban item file supplies the long history (2014-01..2025-12).
For items present on both bases, the CPI2024 segment (2025-01 onward, through the
latest available official month) is rescaled to CPI2012 using the mean log ratio over
the 12 overlapping 2025 months. A constant level offset is immaterial to chain-relative
validation; the splice preserves the newer CPI2024 movements while extending history.

`validate_proxies()` requires this comparator. It deliberately does not fall back to the
CPI2024-only file, which starts in 2025 and would make the long-history legs unavailable.

Output: data/official/official_item_spliced.csv (item_id, period, index_value, segment).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def build(root: Path | str = ROOT) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build the item-id comparator and a per-item splice-offset report from `root/data`."""
    root = Path(root).resolve()
    off = root / "data" / "official"
    mp_path = root / "data" / "basket_official_map.csv"
    old_path = off / "mospi_cpi2012_gujarat_urban_items.csv"
    new_path = off / "mospi_cpi2024_gujarat_urban.csv"
    for path in (mp_path, old_path, new_path):
        if not path.is_file():
            raise FileNotFoundError(f"required input missing: {path}")

    mp = pd.read_csv(mp_path, dtype=str, keep_default_na=False)
    names_path = off / "basket_to_cpi2012_map.csv"
    if not names_path.is_file():
        raise FileNotFoundError(f"required CPI2012 item map missing: {names_path}")
    nm = pd.read_csv(names_path, dtype=str, keep_default_na=False)
    names = dict(zip(nm.item_id, nm.cpi2012_item))

    o24 = pd.read_csv(new_path, dtype={"code": str, "period": str})
    o24 = o24[o24.level == "item"].pivot_table(
        index="period", columns="code", values="index_value", aggfunc="first"
    ).sort_index()
    o12 = pd.read_csv(old_path, dtype={"period": str})
    o12["index_value"] = pd.to_numeric(o12["index_value"], errors="coerce")
    o12 = o12.drop_duplicates(["item", "period"]).pivot_table(
        index="period", columns="item", values="index_value", aggfunc="first"
    ).sort_index()

    rows: list[dict] = []
    report: list[dict] = []
    for _, r in mp.iterrows():
        item_id, code = r.item_id, r.official_item_code
        name = names.get(item_id, "")
        old = o12[name].dropna() if name and name in o12.columns else None
        new = o24[code].dropna() if code and code in o24.columns else None
        segment = "cpi2024"

        if old is None and new is None:
            continue
        if old is None:
            series = new
        elif new is None:
            series, segment = old, "cpi2012"
        else:
            overlap = old.index.intersection(new.index)
            if len(overlap) < 6:
                raise ValueError(
                    f"{item_id}: only {len(overlap)} CPI2012/CPI2024 overlap months; "
                    "cannot make a defensible splice"
                )
            log_shift = float(np.mean(np.log(new.reindex(overlap)) - np.log(old.reindex(overlap))))
            series = pd.concat([old[old.index < overlap[0]], new * np.exp(-log_shift)])
            series = series[~series.index.duplicated(keep="last")].sort_index()
            segment = "splice"
            report.append({
                "item_id": item_id,
                "overlap_months": int(len(overlap)),
                "overlap_first": str(overlap.min()),
                "overlap_last": str(overlap.max()),
                "log_shift": round(log_shift, 6),
                "shift_pct": round((float(np.exp(-log_shift)) - 1) * 100, 3),
            })

        for period, value in series.dropna().items():
            if float(value) > 0:
                rows.append({
                    "item_id": item_id, "period": str(period),
                    "index_value": float(value), "segment": segment,
                })

    df = pd.DataFrame(rows, columns=["item_id", "period", "index_value", "segment"])
    if df.empty:
        raise ValueError("the official splice produced no item observations")
    df = df.sort_values(["item_id", "period"]).reset_index(drop=True)
    return df, pd.DataFrame(report)


def main() -> None:
    df, report = build(ROOT)
    out = ROOT / "data" / "official" / "official_item_spliced.csv"
    df.to_csv(out, index=False)
    print(f"wrote {out}: {len(df)} rows, {df.item_id.nunique()} items, {df.period.min()}..{df.period.max()}")
    print(df.groupby("segment").size().to_string())
    if len(report):
        print("\nCPI2024/CPI2012 overlap offsets:")
        print(report.sort_values("shift_pct").to_string(index=False))
        print(f"\nmedian |offset| = {report.shift_pct.abs().median():.2f}%")


if __name__ == "__main__":
    main()
