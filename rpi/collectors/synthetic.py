"""SYNTHETIC data generator - for testing and demos ONLY. Source ids start with 'synthetic'.

Simulates: retail SKUs across pincodes (promos, stock-outs, SKU churn), mandi series with seasonality,
and tariff step-changes. Returns the TRUE monthly log price paths so tests can verify the engine
recovers them. Never mixed into a published real index (publish refuses without --demo).
"""
from __future__ import annotations
import datetime as dt
import numpy as np
import pandas as pd
from .base import Observation
from .tariff_events import expand_events


def generate(basket: pd.DataFrame, start: dt.date, end: dt.date, seed: int = 11,
             pincodes=("360001", "360002", "360003")):
    rng = np.random.default_rng(seed)
    days = pd.date_range(start, end, freq="D")
    months = pd.period_range(start, end, freq="M")
    obs: list[Observation] = []
    truth: dict[str, np.ndarray] = {}
    mi = {p: i for i, p in enumerate(months)}

    def true_path(drift, seas_amp=0.0, vol=0.0):
        t = np.arange(len(months))
        noise = np.cumsum(rng.normal(0, vol, len(months))) if vol else 0
        return drift * t + seas_amp * np.sin(2 * np.pi * t / 12) + noise

    for r in basket.itertuples():
        if r.tier == "D":
            continue
        base = float(np.exp(rng.uniform(2.5, 5.5)))
        if r.tier == "A":
            path = true_path(rng.normal(0.004, 0.003), vol=0.002)
            truth[r.item_id] = path
            for s_i, src in enumerate(("synthetic_retailA", "synthetic_retailB")):
                sku_level = np.exp(rng.normal(0, 0.12))
                churn_day = days[int(len(days) * rng.uniform(0.5, 0.8))] if (s_i == 1 and rng.random() < 0.3) else None
                for pc in pincodes:
                    q_level = np.exp(rng.normal(0, 0.02))
                    for d in days[::2]:
                        if rng.random() < 0.10:
                            continue                                     # not observed / stock-out
                        lvl = base * sku_level * q_level * np.exp(path[mi[d.to_period("M")]])
                        sku = f"{r.item_id}-{s_i}"
                        if churn_day is not None and d >= churn_day:
                            sku, lvl = f"{r.item_id}-{s_i}b", lvl * 1.05  # replacement SKU
                        promo = rng.random() < 0.15
                        price = lvl * (1 - rng.uniform(0.1, 0.25)) if promo else lvl
                        price *= np.exp(rng.normal(0, 0.004))
                        obs.append(Observation(d.date(), src, sku, f"{r.name} 1 kg", r.item_id, pc,
                                               round(price, 2), round(lvl, 2), 1000.0, "g",
                                               True, promo))
        elif r.tier == "B":
            path = true_path(rng.normal(0.003, 0.002), seas_amp=0.08, vol=0.01)
            truth[r.item_id] = path
            for mk in ("MANDI:Rajkot", "MANDI:Gondal"):
                q_level = np.exp(rng.normal(0, 0.05))
                for d in days[::3]:
                    lvl = base * q_level * np.exp(path[mi[d.to_period("M")]]) * np.exp(rng.normal(0, 0.01))
                    obs.append(Observation(d.date(), "synthetic_mandi", f"{r.item_id}|{mk}", r.name,
                                           r.item_id, mk, round(lvl, 2), qty_base=1000.0, base_unit="g"))
        elif r.tier == "C":
            ev, level, p = [], base, []
            n_steps = min(int(rng.integers(1, 4)), len(months) - 1)
            step_months = sorted(rng.choice(range(1, len(months)), size=n_steps, replace=False)) if n_steps > 0 else []
            ev.append((r.item_id, months[0].start_time.date(), round(level, 2)))
            for sm in step_months:
                level *= 1 + rng.uniform(0.02, 0.12)
                ev.append((r.item_id, (months[sm].start_time + pd.Timedelta(days=int(rng.integers(0, 25)))).date(),
                           round(level, 2)))
            events = pd.DataFrame(ev, columns=["item_id", "effective_from", "price"])
            tobs = expand_events(events, end, "synthetic_tariff")
            obs.extend(tobs)
            truth[r.item_id] = np.log(np.array([o.price for o in tobs])) - np.log(tobs[0].price)
    return obs, truth, months
