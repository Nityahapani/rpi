"""Index switches: items whose index series moves from their old source to a new one from a given month.

Why this exists.  Changing `primary_source` in data/source_plan.csv only changes which collector feeds an item. The index itself
(rpi/index/panel.py load_quotes) reads EVERY source's quotes for an item, so a switched item kept its old history and the new
quotes only entered through matched-model pairs - the index did not change at all (checked 2026-10-10 on an offline rebuild).

A switch is therefore declared here, in config/settings.toml [index.switches]:

    F001 = ["rajkot_shops", "2026-11"]     # new source, first month that source drives the index

Rules, for an item with a switch (src, first month M):
  * observations of the OLD sources dated before M are used as before (the published history is untouched);
  * observations of the old sources dated M or later are excluded;
  * observations of the NEW source dated before the month before M are excluded; the month before M is kept so that the new
    source's first matched pair (month M-1 -> M) exists. Quotes of the new source in M-1 cannot change M-1 (no earlier new-source quote);
  * from M on, the item's monthly relative is the new source's matched-model chain.
So the first month that moves is M, and it moves from a real matched pair, not from a level splice.

The plan and this table must agree (tests/test_switches.py): a candidate source in the plan without a row here, or a row whose
source differs from the plan, is an error.
"""
from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from pathlib import Path

from .config import ROOT

import pandas as pd

_ID = re.compile(r"^[A-Z]\d{3}$")
_SRC = re.compile(r"^[a-z_]+$")
_MONTH = re.compile(r"^\d{4}-\d{2}$")


@lru_cache(maxsize=4)
def _load(path: str) -> tuple:
    cfg = tomllib.loads(Path(path).read_text(encoding="utf8"))
    rows = []
    for item, v in cfg.get("index", {}).get("switches", {}).items():
        if not (_ID.match(item) and isinstance(v, list) and len(v) == 2):
            raise ValueError(f"[index.switches] {item} = {v!r}: expected [source, 'YYYY-MM']")
        src, frm = v
        if not (_SRC.match(str(src)) and _MONTH.match(str(frm))):
            raise ValueError(f"[index.switches] {item} = {v!r}: bad source or month")
        rows.append((item, str(src), str(frm)))
    return tuple(sorted(rows))


def load(settings_path: Path | None = None) -> dict[str, tuple[str, str]]:
    """item_id -> (new source, first month that source drives the index)."""
    p = Path(settings_path) if settings_path else ROOT / "config" / "settings.toml"
    return {i: (s, m) for i, s, m in _load(str(p))}


def clause(alias_p: str = "p", alias_o: str = "o", rules: dict | None = None) -> str:
    """AND-able SQL predicate for the switch rules (requires `observations <alias_o>` joined to `products <alias_p>`)."""
    rules = load() if rules is None else rules
    if not rules:
        return "1=1"
    parts = []
    for item, (src, frm) in sorted(rules.items()):
        first = f"{frm}-01"
        link = (pd.Period(frm, "M") - 1).strftime("%Y-%m-%d")[:7] + "-01"     # the month before M: the new source needs it to link
        parts.append(
            f"NOT ({alias_p}.item_id='{item}' AND (({alias_p}.source_id<>'{src}' AND {alias_o}.obs_date>='{first}') "
            f"OR ({alias_p}.source_id='{src}' AND {alias_o}.obs_date<'{link}')))")
    return " AND ".join(parts)


def check_against_plan(plan, rules: dict | None = None) -> list[str]:
    """Problems between the switch table and data/source_plan.csv (empty list = consistent)."""
    rules = load() if rules is None else rules
    problems = []
    p = plan.set_index("item_id")
    for item, (src, _frm) in rules.items():
        if item not in p.index:
            problems.append(f"{item}: switch declared but not in the plan")
        elif p.loc[item, "primary_source"] != src:
            problems.append(f"{item}: plan says {p.loc[item, 'primary_source']!r}, switch says {src!r}")
    return problems
