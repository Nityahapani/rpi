"""Prospective test: a frozen model, forecasts logged before the official figure exists, scored later.

Pre-registered (fixed before any prospective month is observed):
  candidate  calibrated item model: official item MoM = alpha + beta * rpi item MoM, pooled,
             weighted by the official-matched basket weights to the general index.
  baseline   raw rpi item aggregate with the same weights (no calibration).
  target     official general CPI2024 Gujarat-urban MoM.
  decision   adopt the candidate only after >= 12 scored months AND its RMSE is lower AND the 95%
             month-bootstrap interval of (candidate RMSE - baseline RMSE) lies entirely below zero.
             Otherwise the result is reported as "not established". The rule is not revisited on the data.

Storage: econ/ledger/ is tracked by git. The forecast file is append-only; a second write for the same
(period, model) is refused. Git history makes later edits visible.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from econ.data import load_panel
from econ.items import _rpi_item_mom, load_items

LEDGER = Path(__file__).resolve().parent / "ledger"
PARAMS = LEDGER / "frozen_params.json"
FORECASTS = LEDGER / "forecasts.csv"
MIN_SCORED = 12
MODEL = "calibrated_item"
BASELINE = "raw_rpi_aggregate"


def _fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def freeze() -> dict:
    """Fit the candidate once on clean history and write it. Refuses to overwrite a frozen file."""
    if PARAMS.exists():
        raise SystemExit(f"{PARAMS} already exists; the model is frozen. Delete it only to start a new test.")
    L = load_items().long.copy()
    clean = L[(L.x - L.y).abs() >= 1e-6]          # back-filled months are not independent evidence
    b, a = np.polyfit(clean.x, clean.y, 1)
    params = {
        "model": MODEL,
        "alpha": float(a),
        "beta": float(b),
        "fitted_on_clean_item_months": int(len(clean)),
        "fitted_through": str(clean.period.max()),
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    params["fingerprint"] = _fingerprint({k: v for k, v in params.items() if k != "frozen_at"})
    LEDGER.mkdir(parents=True, exist_ok=True)
    PARAMS.write_text(json.dumps(params, indent=2), encoding="utf8")
    return params


def _load_params() -> dict:
    if not PARAMS.exists():
        raise SystemExit("no frozen model: run `python3 -m econ freeze` first")
    return json.loads(PARAMS.read_text(encoding="utf8"))


def _forecasts_for(periods_wanted: list[str] | None = None) -> pd.DataFrame:
    """Candidate and baseline for every rpi month that has item data (aggregated with matched weights)."""
    par = _load_params()
    ip = load_items()
    x_all = _rpi_item_mom()   # rpi item MoM for every month, including months without an official figure
    w = ip.matched.set_index("item_id").weight.astype(float)
    cols = [c for c in w.index if c in x_all.columns]
    x = x_all[cols]
    ok = x.notna()
    wsum = (ok * w[cols]).sum(axis=1)
    raw = (x.fillna(0) * w[cols]).sum(axis=1) / wsum
    cal = (par["alpha"] + par["beta"] * x.fillna(0)) * w[cols]
    cal = cal.sum(axis=1) / wsum
    out = pd.DataFrame({"candidate": cal, "baseline": raw})
    out = out[np.isfinite(out.candidate) & np.isfinite(out.baseline)]   # months with no usable item change are not forecasts
    if periods_wanted is not None:
        out = out.loc[out.index.isin(periods_wanted)]
    return out


def log_new() -> list[dict]:
    """Append forecasts for every rpi month that has no official figure yet and no logged row."""
    par = _load_params()
    panel = load_panel()
    released = set(panel.official_mom.index)
    fc = _forecasts_for()
    pending = [p for p in fc.index if p not in released]
    existing = pd.read_csv(FORECASTS, dtype=str) if FORECASTS.exists() else pd.DataFrame(
        columns=["period", "model", "forecast", "baseline", "issued_at", "params_fingerprint", "input_fingerprint"])
    done = set(existing.period) if len(existing) else set()
    rows = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in pending:
        if p in done:
            continue
        inp = _fingerprint({"period": p, "candidate": round(float(fc.loc[p, "candidate"]), 6),
                            "baseline": round(float(fc.loc[p, "baseline"]), 6)})
        rows.append({"period": p, "model": MODEL, "forecast": round(float(fc.loc[p, "candidate"]), 4),
                     "baseline": round(float(fc.loc[p, "baseline"]), 4), "issued_at": now,
                     "params_fingerprint": par["fingerprint"], "input_fingerprint": inp})
    if rows:
        new = pd.DataFrame(rows)
        LEDGER.mkdir(parents=True, exist_ok=True)
        new.to_csv(FORECASTS, mode="a", header=not FORECASTS.exists(), index=False)
    return rows


def score() -> dict:
    if not FORECASTS.exists():
        return {"scored": 0, "status": "nothing logged yet"}
    led = pd.read_csv(FORECASTS, dtype={"period": str})
    off = load_panel().official_mom
    led = led[led.period.isin(off.index)].copy()
    if led.empty:
        return {"scored": 0, "status": "logged months not yet released by the official index"}
    led["official"] = led.period.map(off)
    led["e_cand"] = led.official - led.forecast
    led["e_base"] = led.official - led.baseline
    n = len(led)
    rm = lambda e: float(np.sqrt((e ** 2).mean()))
    res = {"scored": n, "rmse_candidate": rm(led.e_cand), "rmse_baseline": rm(led.e_base),
           "months": led.period.tolist()}
    gap_obs = res["rmse_candidate"] - res["rmse_baseline"]
    res["gap_rmse"] = gap_obs
    if n >= 1:
        rng = np.random.default_rng(0)
        sq = led[["e_cand", "e_base"]].values ** 2
        draws = []
        for _ in range(5000):
            idx = rng.integers(0, n, n)            # same resampled months for both models
            draws.append(np.sqrt(sq[idx, 0].mean()) - np.sqrt(sq[idx, 1].mean()))
        res["gap_ci95"] = [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]
    if n < MIN_SCORED:
        res["status"] = f"not decided: {n}/{MIN_SCORED} scored months"
    elif gap_obs < 0 and res["gap_ci95"][1] < 0:
        res["status"] = "candidate beats baseline (pre-registered rule met)"
    else:
        res["status"] = "not established: the pre-registered rule is not met"
    return res
