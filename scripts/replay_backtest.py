"""Replay the production pipeline for past months as if they were nowcasts; compare with the actual; write reports.
Run: PYTHONPATH=. python3 scripts/replay_backtest.py   (about 1 minute per cut-off; writes data/official/replay_backtest.csv + .md)"""
import numpy as np
import pandas as pd

from rpi.replay import replay

r = replay()
df, actual, gu = r["table"], r["actual"], r["gu"]
df.round(4).to_csv("data/official/replay_backtest.csv", index=False)


def stat(x):
    return dict(n=len(x), mae=x.abs().mean(), rmse=float(np.sqrt((x ** 2).mean())), bias=x.mean(), mx=x.abs().max())


lines = ["# Replay back-test of the production index (real engine, official data hidden after each cut-off)", "",
         f"Last official month available now: {r['last_official']}. 'Actual' = the index the same engine publishes with the official data in.",
         "Errors are nowcast / actual - 1, in percent of the index level.", "",
         "| h (months ahead) | n | engine MAE % | RMSE % | bias % | max |abs| % | own-trend-only RMSE % | zero-change RMSE % | wins vs own-trend-only | wins vs zero-change |",
         "|---|---|---|---|---|---|---|---|---|---|"]
for h, g in df.groupby("h"):
    s, o, z = stat(g.err_pct), stat(g.err_own_trend_only_pct), stat(g.err_zero_change_pct)
    lines.append(f"| {h} | {s['n']} | {s['mae']:.3f} | {s['rmse']:.3f} | {s['bias']:+.3f} | {s['mx']:.3f} | {o['rmse']:.3f} | {z['rmse']:.3f} | "
                 f"{int((g.err_pct.abs() < g.err_own_trend_only_pct.abs()).sum())}/{len(g)} | {int((g.err_pct.abs() < g.err_zero_change_pct.abs()).sum())}/{len(g)} |")
g = df[df.h == 1].copy()
lines += ["", "## One-month-ahead nowcast vs actual, month by month", "",
          "| cut-off | target | nowcast | actual | error % | own-trend-only err % | zero-change err % | MoSPI Gujarat-urban general (rebased) | nowcast vs MoSPI % | share of weight observed |", "|---|---|---|---|---|---|---|---|---|---|"]
for x in g.itertuples():
    lines.append(f"| {x.cutoff} | {x.period} | {x.nowcast:.3f} | {x.actual:.3f} | {x.err_pct:+.3f} | {x.err_own_trend_only_pct:+.3f} | {x.err_zero_change_pct:+.3f} | "
                 f"{x.gu_official:.3f} | {x.err_vs_official_pct:+.3f} | {x.nowcast_obs_weight*100:.0f}% |")
lines += ["", "## Published index (actual) vs the official yardstick, all verified months", "",
          "| month | RPI | MoSPI Gujarat-urban general (Jan 2025=100) | RPI / MoSPI - 1 % |", "|---|---|---|---|"]
for p in actual.index:
    if p in gu.index and p <= pd.Period(r["last_official"], "M"):
        lines.append(f"| {p} | {actual[p]:.3f} | {gu[p]:.3f} | {(actual[p]/gu[p]-1)*100:+.3f} |")
lines += ["", "Caveats: independent feeds are used as they exist today (some started after the early cut-offs, which flatters the early replays); the 'actual' contains "
          "official-linked stand-ins for 59.9% of plan weight, so part of the agreement with MoSPI is by construction; the replay tests the nowcast months only."]
open("data/official/replay_backtest.md", "w").write("\n".join(lines))
print("\n".join(lines))
