"""Persist collector output into the warehouse, with validation and run logging."""
from __future__ import annotations
import datetime as dt
from .collectors.base import Observation
from .units import unit_price


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_basket(conn, df) -> int:
    conn.execute("DELETE FROM items")
    conn.executemany(
        "INSERT INTO items VALUES(?,?,?,?,?,?)",
        [(r.item_id, r.name, str(r.division), r.tier, r.base_unit, r.spec) for r in df.itertuples()])
    conn.commit()
    return len(df)


def load_weights(conn, df) -> int:
    d = df.copy()
    d["weight"] = d["weight"].astype(float)
    if d["weight"].isna().any():
        raise ValueError("weights file has blank weights - fill them from the official CPI 2024 tables")
    conn.execute("DELETE FROM weights")
    conn.executemany("INSERT INTO weights VALUES(?,?,?)",
                     [(r.item_id, float(r.weight), r.weight_source) for r in d.itertuples()])
    conn.commit()
    return len(d)


def persist(conn, observations, snapshot_id: int | None = None) -> tuple[int, int, list[str]]:
    """Insert observations. Returns (accepted, rejected, reasons[:20])."""
    valid_items = {r[0] for r in conn.execute("SELECT item_id FROM items")}
    fetched = now_iso()
    acc = rej = 0
    reasons: list[str] = []
    for o in observations:
        why = None
        if o.item_id not in valid_items:
            why = f"unknown item_id {o.item_id}"
        elif o.price is None or not (o.price > 0):
            why = f"non-positive price for {o.source_sku}"
        if why:
            rej += 1
            if len(reasons) < 20:
                reasons.append(why)
            continue
        sku_id = f"{o.source_id}:{o.source_sku}"
        d = o.obs_date.isoformat()
        conn.execute("INSERT OR IGNORE INTO sources(source_id) VALUES(?)", (o.source_id,))
        conn.execute(
            """INSERT INTO products(sku_id,source_id,source_sku,item_id,title,qty_base,base_unit,first_seen,last_seen)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(sku_id) DO UPDATE SET last_seen=max(last_seen, excluded.last_seen),
                 title=excluded.title, qty_base=excluded.qty_base, base_unit=excluded.base_unit""",
            (sku_id, o.source_id, o.source_sku, o.item_id, o.title, o.qty_base, o.base_unit, d, d))
        reg = o.regular_price if o.regular_price else o.price
        conn.execute(
            """INSERT OR REPLACE INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d, sku_id, o.pincode, o.price, reg,
             unit_price(o.price, o.qty_base, o.base_unit), unit_price(reg, o.qty_base, o.base_unit),
             int(o.in_stock), int(o.on_promo), o.delivery_fee, snapshot_id, fetched))
        acc += 1
    conn.commit()
    return acc, rej, reasons


def run_collector(conn, collector, on_date: dt.date | None = None) -> dict:
    """Run a collector with full logging; failures never crash the pipeline."""
    started = now_iso()
    status, n, acc, rej, msg = "ok", 0, 0, 0, ""
    try:
        obs = list(collector.collect(on_date or dt.date.today()))
        n = len(obs)
        acc, rej, reasons = persist(conn, obs, getattr(collector, "last_snapshot_id", None))
        if rej:
            msg = "; ".join(reasons[:5])
        if n == 0:
            status, msg = "empty", "collector returned no records"
    except Exception as e:  # noqa: BLE001 - we want to log everything
        status, msg = "error", f"{type(e).__name__}: {e}"
    conn.execute(
        "INSERT INTO collector_runs(source_id,started_at,finished_at,status,n_records,n_accepted,n_rejected,message) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (collector.source_id, started, now_iso(), status, n, acc, rej, msg))
    conn.commit()
    return {"source": collector.source_id, "status": status, "records": n, "accepted": acc,
            "rejected": rej, "message": msg}
