"""Build the fixed SKU pool for the Instamart Rajkot feed -> data/instamart/pool.csv.

Run once before any history exists; rerunning overwrites the pool and therefore breaks the matched-model chain, so only
run it to ADD items, never to replace SKUs that are already accruing.

    PYTHONPATH=. python3 scripts/build_instamart_pool.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rpi.collectors import instamart as im  # noqa: E402

# one mainstream SKU family per item, largest household pack first.  Kept small on purpose: the item series is the
# matched-model Jevons chain of these SKUs, so every extra SKU is a churn risk for no extra signal.
KEEP = {
    "F014": (1, 1000),      # tea, ~1 kg
    "F017": (1, None),      # biscuits, one pack
    "P001": (2, None),      # soap, two bars
    "P002": (1, None),      # shampoo
    "P003": (1, None),      # toothpaste
    "H001": (1, 1000),      # detergent powder ~1 kg
    "H002": (1, None),
    "F018": (1, None),
    "F012": (1, 500),       # ghee 500 g-ish
    "F010": (1, 400),
    "F019": (1, None),
    "F015": (1, 1000),
    "H003": (1, None),
    "E003": (1, None),
    "M002": (1, None),
}


def main() -> None:
    rows = im.harvest()
    pool = im.build_pool(rows, dt.date.today())
    keep = []
    for item, (n, _weight) in KEEP.items():
        g = pool[pool.item_id == item]
        if not len(g):
            print(f"  {item}: nothing mapped on the Rajkot store today")
            continue
        keep.append(g.sort_values("qty_base", ascending=False).head(n))
    out = pd.concat(keep, ignore_index=True) if keep else pool.head(0)
    dest = ROOT / im.POOL
    dest.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dest, index=False)
    print(out.groupby("item_id").size().to_string())
    print(f"{len(out)} SKUs for {out.item_id.nunique()} items -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
