"""python3 -m econ {fit,compare,breaks,report} [--out DIR]

All commands are read-only on the pipeline. Results go to econ/outputs/ (uncommitted by default).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from econ import dfm, evaluate
from econ.data import ROOT, division_changes, load_panel

DEFAULT_OUT = Path(__file__).resolve().parent / "outputs"


def _out(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    return d


def _params_frame(p, params: dfm.DFMParams) -> pd.DataFrame:
    return pd.DataFrame({"division": p.divisions, "weight": p.weights.values,
                         "loading": params.lam, "idio_var": params.h,
                         "signal_share": params.lam ** 2 / (params.lam ** 2 + params.h)})


def cmd_fit(p, out: Path) -> dict:
    run = evaluate.factor_run(p, upto=None)
    nc = evaluate.nowcast(p)
    ll = dfm.kalman(division_changes(p)[p.divisions].values, run.params).loglik
    _params_frame(p, run.params).to_csv(out / "loadings.csv", index=False)
    nc["table"].to_csv(out / "nowcast.csv")
    br = nc["bridge"]
    summary = {
        "phi": run.params.phi,
        "loglik": ll,
        "bridge": {"alpha": br.alpha, "beta": br.beta, "sigma": br.sigma, "n_official_months": br.n},
        "divisions": p.divisions,
        "uncovered_official_weight_pct": round(100 * p.uncovered_weight, 2),
        "latest_nowcast": nc["table"].tail(3)[["mom_nowcast", "band80_lo", "band80_hi"]].round(3).to_dict("index"),
    }
    print(f"factor AR(1) phi = {run.params.phi:.3f}   log-likelihood = {ll:.2f}")
    print(f"bridge: official MoM = {br.alpha:.3f} + {br.beta:.3f} * factor   (residual sd {br.sigma:.3f}, n={br.n})")
    print(f"divisions used: {len(p.divisions)} (official general weight not covered by rpi: {100*p.uncovered_weight:.1f}%)")
    print("\nlatest nowcasts (MoM %, 80% band):")
    print(nc["table"].tail(4)[["factor", "mom_nowcast", "band80_lo", "band80_hi", "official_mom"]].round(3).to_string())
    print(f"\nwrote {out/'loadings.csv'} and {out/'nowcast.csv'}")
    return summary


def cmd_compare(p, out: Path) -> dict:
    from econ import combine
    c = combine.candidates(p)
    c.to_csv(out / "candidates.csv")
    sc = combine.score(c)
    sc.to_csv(out / "scores.csv", index=False)
    print(f"rolling-origin backtest of the official general MoM, {len(c)} months "
          f"({c.index[0]} .. {c.index[-1]}); each forecast uses only data before its month\n")
    print(f"{'model':<20}{'n':>4}{'RMSE':>9}{'MAE':>9}{'bias':>9}{'RMSE gap vs fixed_weight [95% boot]':>40}")
    for _, r in sc.iterrows():
        if r.model == "fixed_weight":
            gap = "(benchmark)"
        else:
            g, lo, hi = combine.paired_rmse_gap(c, r.model)
            gap = f"{g:+.3f} [{lo:+.3f}, {hi:+.3f}]"
        print(f"{r.model:<20}{r.n:>4}{r.rmse:>9.3f}{r.mae:>9.3f}{r.bias:>9.3f}{gap:>40}")
    print("\nnot adopted unless a candidate beats fixed_weight with an interval clear of zero.")
    print(f"wrote {out/'candidates.csv'} and {out/'scores.csv'}")
    return {"scores": sc.to_dict("records")}


def cmd_breaks(p, out: Path) -> dict:
    run = evaluate.factor_run(p, upto=None)
    y = division_changes(p)[p.divisions].values
    res = dfm.cusum(y, run.params, dfm.kalman(y, run.params))
    rows = []
    for i, d in enumerate(p.divisions):
        r = res[i] or {}
        rows.append({"division": d, "n": r.get("n"), "max_abs_cusum": r.get("max_abs"),
                     "first_breach": (p.periods[1 + r["first_breach_index"]] if r.get("first_breach_index") is not None else None)})
    df = pd.DataFrame(rows)
    df.to_csv(out / "breaks.csv", index=False)
    print("CUSUM of standardised one-step errors (approximate boundary, short sample):\n")
    print(df.to_string(index=False))
    flagged = df[df.first_breach.notna()]
    print(f"\n{len(flagged)} of {len(df)} divisions breach the boundary")
    print(f"wrote {out/'breaks.csv'}")
    return {"flagged": flagged.division.tolist()}


def cmd_report(p, out: Path) -> None:
    s = {"fit": cmd_fit(p, out), "compare": cmd_compare(p, out), "breaks": cmd_breaks(p, out)}
    (out / "summary.json").write_text(json.dumps(s, indent=2, default=float), encoding="utf8")
    print(f"\nwrote {out/'summary.json'}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m econ", description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["fit", "compare", "breaks", "report"])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory (default econ/outputs)")
    args = ap.parse_args(argv)
    p = load_panel()
    out = _out(args.out)
    {"fit": cmd_fit, "compare": cmd_compare, "breaks": cmd_breaks, "report": cmd_report}[args.command](p, out)
    return 0
