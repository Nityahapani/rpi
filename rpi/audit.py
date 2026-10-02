"""Accuracy audits against OFFICIAL MoSPI Gujarat-urban CPI (2024=100).

The official indices are an independent ground truth for the things our own pipeline cannot verify alone:

  1. basket_replication  - can THIS basket + THESE weights track the official General index at all, if every
                           item had perfect price data? (upper bound on basket/weight error)
  2. compare_item        - does a price series we built agree with the official item index (timing + size)?
  3. blend_share         - for blended official items (LPG+PNG) is the implied share of our item plausible (0..1)?

Nothing here makes network calls; it works on data/official/mospi_cpi2024_gujarat_urban.csv.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def load_official(path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str})
    df["period"] = df["period"].astype(str)
    return df


def official_item_matrix(off: pd.DataFrame) -> pd.DataFrame:
    return (off[off.level == "item"].pivot_table(index="period", columns="code", values="index_value", aggfunc="first")
            .sort_index())


def official_general(off: pd.DataFrame) -> pd.Series:
    return off[off.level == "general"].set_index("period")["index_value"].sort_index()


def basket_replication(off: pd.DataFrame, item_weights: pd.DataFrame, mapping: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Re-aggregate OFFICIAL item indices with OUR item weights and compare to the official General index."""
    iw = item_weights.merge(mapping[["item_id", "official_item_code"]], on="item_id")
    iw = iw[iw["official_item_code"] != ""]
    w = iw.groupby("official_item_code")["weight"].sum()
    w = w / w.sum()
    mat = official_item_matrix(off)
    rep = (mat[w.index] * w).sum(axis=1)
    gen = official_general(off).reindex(rep.index)
    out = pd.DataFrame({"basket_replication": rep, "official_general": gen})
    out["error"] = out["basket_replication"] - out["official_general"]
    stats = {
        "n_months": int(len(out)),
        "items_with_official_index": int(len(w)),
        "weight_share_with_official_index_pct": float(iw["weight"].sum() / item_weights["weight"].sum() * 100),
        "rmse": float(np.sqrt((out["error"] ** 2).mean())),
        "max_abs_error": float(out["error"].abs().max()),
        "cum_change_replicated_pct": float((rep.iloc[-1] / rep.iloc[0] - 1) * 100),
        "cum_change_official_pct": float((gen.iloc[-1] / gen.iloc[0] - 1) * 100),
    }
    return out, stats


def monthly_mean_series(obs: pd.DataFrame) -> pd.Series:
    """obs: columns obs_date, price -> monthly mean indexed by 'YYYY-MM'."""
    d = obs.copy()
    d["period"] = pd.to_datetime(d["obs_date"]).dt.strftime("%Y-%m")
    return d.groupby("period")["price"].mean().sort_index()


def compare_item(mine: pd.Series, official: pd.Series, move_threshold_pct: float = 0.3) -> dict:
    """Compare month-on-month % changes of our price series with the official item index.

    timing_f1   : F1 of 'a month with |change| >= threshold' detections (did we move when the official index moved?)
    corr_mom    : correlation of m/m % changes
    cum_gap_pp  : difference in cumulative % change over the common window (ours - official)
    """
    idx = mine.index.intersection(official.index)
    if len(idx) < 3:
        return {"n": int(len(idx)), "status": "insufficient_overlap"}
    m, o = mine.loc[idx], official.loc[idx]
    dm, do = m.pct_change().dropna() * 100, o.pct_change().dropna() * 100
    a, b = dm.abs() >= move_threshold_pct, do.abs() >= move_threshold_pct
    tp = int((a & b).sum()); fp = int((a & ~b).sum()); fn = int((~a & b).sum())
    f1 = 1.0 if (tp + fp + fn) == 0 else 2 * tp / (2 * tp + fp + fn)
    corr = float(np.corrcoef(dm, do)[0, 1]) if dm.std() > 0 and do.std() > 0 else float("nan")
    cum_m, cum_o = (m.iloc[-1] / m.iloc[0] - 1) * 100, (o.iloc[-1] / o.iloc[0] - 1) * 100
    return {"n": int(len(idx)), "window": f"{idx[0]}..{idx[-1]}", "timing_f1": round(f1, 3),
            "corr_mom": None if np.isnan(corr) else round(corr, 3),
            "cum_change_mine_pct": round(float(cum_m), 2), "cum_change_official_pct": round(float(cum_o), 2),
            "cum_gap_pp": round(float(cum_m - cum_o), 2)}


def blend_share(mine: pd.Series, official: pd.Series, min_move_pct: float = 1.0) -> pd.DataFrame:
    """Implied share s = official m/m / our m/m in months where OUR price moved >= min_move_pct.
    For a blend s*LPG + (1-s)*PNG the share must lie in (0,1) if our component is one of the parts."""
    idx = mine.index.intersection(official.index)
    dm, do = mine.loc[idx].pct_change() * 100, official.loc[idx].pct_change() * 100
    t = pd.DataFrame({"mine_pct": dm, "official_pct": do}).dropna()
    t = t[t["mine_pct"].abs() >= min_move_pct].copy()
    t["implied_share"] = t["official_pct"] / t["mine_pct"]
    t["plausible"] = (t["implied_share"] > 0) & (t["implied_share"] < 1)
    return t


# ----------------------------------------------------------------------------- orchestration
def run_audit(root, through=None) -> dict:
    """Run every audit and write data/official/audit_report.md. Returns the numbers."""
    import datetime as dt
    from pathlib import Path
    from .collectors.tariff_events import load_usable_events, expand_events

    root = Path(root)
    off = load_official(root / "data/official/mospi_cpi2024_gujarat_urban.csv")
    iw = pd.read_csv(root / "data/official/weights_item_detail.csv")
    mp = pd.read_csv(root / "data/basket_official_map.csv", dtype=str, keep_default_na=False)
    rep, st = basket_replication(off, iw, mp)

    last_period = official_general(off).index[-1]
    through = through or dt.date(int(last_period[:4]), int(last_period[5:]), 28)
    ev = load_usable_events(root / "data/tariff_events.csv")
    obs = pd.DataFrame([vars(o) for o in expand_events(ev, through)])
    items = official_item_matrix(off)
    code = dict(zip(mp.item_id, mp.official_item_code))
    comps = {}
    for it in sorted(obs["item_id"].unique()) if len(obs) else []:
        comps[it] = compare_item(monthly_mean_series(obs[obs.item_id == it]), items[code[it]])
    blend = {}
    for it in [i for i in comps if mp.set_index("item_id").loc[i, "match_quality"] == "blend"]:
        blend[it] = blend_share(monthly_mean_series(obs[obs.item_id == it]), items[code[it]])

    L = ["# Accuracy audit vs official MoSPI Gujarat-urban CPI (2024=100)", "",
         f"_Official data through {last_period}. Generated by `python -m rpi audit`._", "",
         "## 1. Basket + weights sufficiency", "",
         "If every basket item had a *perfect* price series (the official item index), how well does this basket and these "
         "weights reproduce the official General index?", "",
         f"- items mapped to an official item index: {st['items_with_official_index']} "
         f"({st['weight_share_with_official_index_pct']:.1f}% of weight)",
         f"- RMSE {st['rmse']:.2f} index points, max |error| {st['max_abs_error']:.2f}",
         f"- cumulative change {rep.index[0]}..{rep.index[-1]}: replicated {st['cum_change_replicated_pct']:.2f}% vs official "
         f"{st['cum_change_official_pct']:.2f}%", "",
         "## 2. Our price series vs official item index", "",
         "| item | window | timing F1 | corr m/m | cum % ours | cum % official | gap pp |", "|---|---|---|---|---|---|---|"]
    for it, c in comps.items():
        if "window" in c:
            tag = " (blend: gap not comparable)" if mp.set_index("item_id").loc[it, "match_quality"] == "blend" else ""
            L.append(f"| {it}{tag} | {c['window']} | {c['timing_f1']} | {c['corr_mom']} | {c['cum_change_mine_pct']} | "
                     f"{c['cum_change_official_pct']} | {c['cum_gap_pp']} |")
        else:
            L.append(f"| {it} | insufficient overlap | | | | | |")
    L += ["", "_Timing F1 < 1 is expected: MoSPI books a price step in the month it is collected, whereas we time-weight a "
          "mid-month change across two months. Cumulative gap is the cleaner accuracy measure._", ""]
    for it, t in blend.items():
        L += [f"## 3. Blend check {it} (official item = LPG + PNG)", "", "| period | ours % | official % | implied share | plausible (0..1) |",
              "|---|---|---|---|---|"]
        for p, r in t.iterrows():
            L.append(f"| {p} | {r.mine_pct:.2f} | {r.official_pct:.2f} | {r.implied_share:.2f} | {bool(r.plausible)} |")
        L.append("")
    (root / "data/official/audit_report.md").write_text("\n".join(L))
    rep.round(3).to_csv(root / "data/official/basket_replication.csv")
    return {"basket": st, "items": comps, "blend": {k: v.round(3).to_dict("index") for k, v in blend.items()}}
