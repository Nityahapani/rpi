"""What stands between us and full independent coverage? Every item whose `class` in data/source_plan.csv is NOT `independent`,
grouped by the concrete blocker found while probing on 2026-10-02 (those notes are kept verbatim - they are the evidence from
the probe), with the item lists and weights read live from source_plan/weights so the file cannot drift from the wiring again.
Writes data/official/coverage_ceiling.md.

History: this file was created on 2026-10-02 to answer "what blocks the 40% target" when the independent share was 38.5%. The
share has since passed that milestone, and the item sets that used to be hard-coded here went stale (it still listed items that
had been wired as independent). Everything variable is now derived on each run.
"""
import datetime as dt

import pandas as pd

BLOCK = {
 "Captcha-gated (DoCA retail price monitor)": (["F001","F002","F003","F004","F005","F006","F008","F013","F014","F015","F026"], "fcainfoweb.nic.in tracks exactly these staples, but the report form requires a CAPTCHA. Not automatable without circumvention. data.gov.in/Agmarknet needs a key and was unreachable from the sandbox."),
 "Cloudflare-blocked (mandi grain pages)": (["F007"], "commodityonline /mandiprices/* pages challenge non-browser clients; kisandeals 403; napanta 502."),
 "Brand MRP, history incomplete (not safe to register)": (["F010","F011","F012","F016","F017","F018","F019","P001","P002","P003","H001","H002","H003","H004","C001","C002","C003","T006","K002"], "Packaged goods: only isolated documented steps exist (e.g. Amul butter 62->58, ghee 650->610 on 22 Sep 2025, GST cut). Official butter/ghee indices rose ~3.5% after Oct 2025, so a flat register would be wrong. ToS blocks e-commerce scraping."),
 "No machine-readable source: fares/fees/services": (["T003","E001","E002","E003","E004","M002","M003","M004","P004","S001","S003","D001","D003","R004"], "Bus/auto fares (latest press is 2022), school/tuition fees, doctor/hospital, haircut, cinema, street food, newspaper, RMC water (increase only proposed)."),
 "Judged unrepresentative (kept official-linked on purpose)": (["M001"], "NPPA paracetamol ceiling is real but one controlled drug is a worse proxy for 'medicines' than the broad official index."),
 "No revision found / unverifiable": (["K001","K003","S002"], "Telecom/broadband/OTT: last verified hike Jul 2024; no later revision found, which is not proof of none."),
 "Genuinely no data": (["T005"], "No official item and no independent source."),
}
RENT_NOTE = ("Rent. No public Rajkot rent series: the Magicbricks Rental Index is listing-based, national/metro only "
             "(+14% y/y Q1 2026), not CPI-style rent, so a survey or licensed data is needed. NOTE: R001 is no longer blocked - "
             "it was wired on 2026-10-06 as an independent MODELLED series (Labour Bureau CPI-IW housing, trend-gated, 19.0% of weight).")

plan = pd.read_csv("data/source_plan.csv", dtype=str)
w = pd.read_csv("data/weights_cpi2024_gujarat_urban.csv"); wc = [c for c in w.columns if "weight" in c][0]
b = pd.read_csv("data/basket.csv", dtype=str)
m = plan.merge(w[["item_id", wc]], on="item_id").merge(b[["item_id", "name"]], on="item_id")
ind = m[m["class"] == "independent"]
blk = m[m["class"] != "independent"]
cur, left = ind[wc].sum(), blk[wc].sum()

lines = [f"# Coverage ceiling (generated {dt.date.today().isoformat()}; blocker notes from the 2026-10-02 probe)", "",
         f"Independent weight: **{cur:.1f}%** ({len(ind)} of {len(m)} items). Remaining non-independent weight: "
         f"**{left:.1f}%** ({len(blk)} items).",
         "",
         "The 40% milestone this file was written around (2026-10-02, independent share then 38.5%) has been passed; the live question "
         "is now what still blocks the remainder. Item lists and weights below are read live from data/source_plan.csv.", "",
         "| Blocker | Items (still blocked) | Weight % | What the probe found |", "|---|---|---|---|"]
seen, tot = set(), 0.0
for k, (ids, why) in BLOCK.items():
    sub = m[m.item_id.isin(ids) & (m["class"] != "independent")]
    seen |= set(sub.item_id); wt = sub[wc].sum(); tot += wt
    if len(sub):
        lines.append(f"| {k} | {len(sub)} ({', '.join(sub.item_id)}) | {wt:.1f} | {why} |")
rest = blk[~blk.item_id.isin(seen)]
if len(rest):
    lines.append(f"| UNCLASSIFIED | {len(rest)} ({', '.join(rest.item_id)}) | {rest[wc].sum():.1f} | |")
lines += ["", f"Sum of blocked weight: {tot + rest[wc].sum():.1f}% (= 100 - {cur:.1f}).", ""]

wired = m[m.item_id.isin([i for ids, _ in BLOCK.values() for i in ids]) & (m["class"] == "independent")]
if len(wired):
    lines += [f"Wired since the probe (no longer blockers): {len(wired)} items, {wired[wc].sum():.1f}% of weight - "
              f"{', '.join(wired.item_id)}.", ""]
lines += ["Rent (R001, 19.0%): " + RENT_NOTE, "",
          "## What is left to unlock (largest remaining blocks first)", "| Unlock | + points | Independent % after |", "|---|---|---|"]
def add(ids): return m[m.item_id.isin(ids) & (m["class"] != "independent")][wc].sum()
by_block = sorted(((k, ids, m[m.item_id.isin(ids) & (m["class"] != "independent")][wc].sum()) for k, (ids, _) in BLOCK.items()),
                  key=lambda kv: -kv[2])
run = cur
for k, ids, wt in by_block:
    if wt <= 0:
        continue
    a = add(ids); run += a
    lines.append(f"| Own survey / licensed feed for: {k} | +{a:.1f} | {run:.1f} |")
if len(rest):
    a = rest[wc].sum(); run += a
    lines.append(f"| + UNCLASSIFIED items ({', '.join(rest.item_id)}) | +{a:.1f} | {run:.1f} |")
big = ", ".join(f"{k} ({v:.1f}%)" for k, _, v in by_block[:3] if v > 0)
lines += ["", f"Reading: no *automatable, permitted, real* feed remains for any large block; the weight still on official stand-ins sits in "
          f"{big}. Reaching 100% is possible only through data we collect ourselves (own surveys, licences or RTI), because every "
          f"remaining block is blocked by a mechanism (captcha, bot challenge, ToS, or no publication at all) rather than by effort."]
open("data/official/coverage_ceiling.md", "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
