"""One-source index/gate exclusions for replaced local feeds.

When a basket item is promoted to a better single source, its older feeds remain
in the warehouse for diagnostics but must not enter the published index, proxy gate,
or independent-start cut-offs. The DoCA Rajkot centre now carries F002/F003/F005/F006/F008/
F013/F021/F022/F023/F026; F011/F020/F024 remain on the national DoCA panel. For F003/F005/
F021/F022/F023, the replaced short wholesale/Gujarat-panel/yard feeds stay excluded. F020's
NECC feed and F024's older non-national inputs are also excluded, while their active national
DoCA panel remains eligible. The switch rules separately prevent former DoCA national/Gujarat
feeds from being used after the 2025-01 base for items moved to Rajkot.
"""
SUPERSEDED_ITEMS = ("F003", "F005", "F020", "F021", "F022", "F023", "F024")
KEEP_SOURCES = ("doca_national", "doca_gujarat", "doca_rajkot", "official_link", "tariff")


def sql_clause(alias: str = "p") -> str:
    """SQL predicate (AND-able) that drops superseded local-feed rows."""
    items = ",".join(f"'{i}'" for i in SUPERSEDED_ITEMS)
    keep = ",".join(f"'{s}'" for s in KEEP_SOURCES)
    return f"NOT ({alias}.item_id IN ({items}) AND {alias}.source_id NOT IN ({keep}))"
