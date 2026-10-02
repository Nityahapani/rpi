"""Items whose index series now comes from ONE gated source, so their older local feeds stay in the database as diagnostics
but are kept out of the index, the proxy gate and the independent-start cut-offs.

Reason: F003/F005/F020/F024 were fed by short local wholesale feeds (Rajkot/Gondal yards, NECC) that had about one month of
history and could not be gated against the official item index (proxy_validation: 'pending'). The DoCA all-India retail panel
has 22 months and passes the gate (see data/official/doca_panel_screen.csv), so it is the primary series. Mixing the two
price levels inside one Jevons item would be wrong, hence this exclusion."""
SUPERSEDED_ITEMS = ("F003", "F005", "F020", "F024")
KEEP_SOURCES = ("doca_national", "official_link", "tariff")


def sql_clause(alias: str = "p") -> str:
    """SQL predicate (AND-able) that drops superseded local-feed rows."""
    items = ",".join(f"'{i}'" for i in SUPERSEDED_ITEMS)
    keep = ",".join(f"'{s}'" for s in KEEP_SOURCES)
    return f"NOT ({alias}.item_id IN ({items}) AND {alias}.source_id NOT IN ({keep}))"
