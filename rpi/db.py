from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
  source_id TEXT PRIMARY KEY, kind TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS items(
  item_id TEXT PRIMARY KEY, name TEXT, division TEXT, tier TEXT, base_unit TEXT, spec TEXT);
CREATE TABLE IF NOT EXISTS weights(
  item_id TEXT PRIMARY KEY, weight REAL, weight_source TEXT);
CREATE TABLE IF NOT EXISTS raw_snapshots(
  snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, fetched_at TEXT, url TEXT,
  params_json TEXT, http_status INTEGER, sha256 TEXT, path TEXT, n_bytes INTEGER);
CREATE TABLE IF NOT EXISTS products(
  sku_id TEXT PRIMARY KEY, source_id TEXT, source_sku TEXT, item_id TEXT, title TEXT,
  qty_base REAL, base_unit TEXT, first_seen TEXT, last_seen TEXT, match_status TEXT DEFAULT 'auto');
CREATE TABLE IF NOT EXISTS observations(
  obs_date TEXT, sku_id TEXT, pincode TEXT, price REAL, regular_price REAL,
  unit_price REAL, regular_unit_price REAL, in_stock INTEGER, on_promo INTEGER,
  delivery_fee REAL, snapshot_id INTEGER, fetched_at TEXT,
  PRIMARY KEY(obs_date, sku_id, pincode));
CREATE INDEX IF NOT EXISTS ix_obs_sku ON observations(sku_id);
CREATE TABLE IF NOT EXISTS collector_runs(
  run_id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT, started_at TEXT, finished_at TEXT,
  status TEXT, n_records INTEGER, n_accepted INTEGER, n_rejected INTEGER, message TEXT);
CREATE TABLE IF NOT EXISTS index_results(
  run_id TEXT, variant TEXT, period TEXT, level TEXT, key TEXT, value REAL, lo REAL, hi REAL);
CREATE INDEX IF NOT EXISTS ix_res_run ON index_results(run_id, variant);
CREATE TABLE IF NOT EXISTS index_diagnostics(
  run_id TEXT, variant TEXT, period TEXT, metric TEXT, key TEXT, value REAL);
CREATE TABLE IF NOT EXISTS index_runs(
  run_id TEXT PRIMARY KEY, built_at TEXT, is_demo INTEGER, weights_source TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS official_series(
  series_id TEXT, period TEXT, value REAL, source_url TEXT, PRIMARY KEY(series_id, period));
CREATE TABLE IF NOT EXISTS nowcasts(
  series_id TEXT, period TEXT, made_at TEXT, nowcast_mom REAL, PRIMARY KEY(series_id, period, made_at));
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
