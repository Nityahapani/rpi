"""What stands between us and a higher independent share? Every official-linked / no-data item, grouped by the concrete
blocker found while probing (2026-10-02), with its weight. Writes data/official/coverage_ceiling.md."""
import pandas as pd

BLOCK = {
 "No reachable source: rent": (["R001"], "Rent. No public Rajkot rent series. Magicbricks Rental Index is listing-based, national/metro only (+14% y/y Q1 2026), not CPI-style rent. Needs own survey or licensed data."),
 "Captcha-gated (DoCA retail price monitor)": (["F001","F002","F003","F004","F005","F006","F008","F013","F014","F015","F026"], "fcainfoweb.nic.in tracks exactly these staples, but the report form requires a CAPTCHA. Not automatable without circumvention. data.gov.in/Agmarknet needs a key and was unreachable from the sandbox."),
 "Cloudflare-blocked (mandi grain pages)": (["F007"], "commodityonline /mandiprices/* pages challenge non-browser clients; kisandeals 403; napanta 502."),
 "Brand MRP, history incomplete (not safe to register)": (["F010","F011","F012","F016","F017","F018","F019","P001","P002","P003","H001","H002","H003","H004","C001","C002","C003","T006","K002"], "Packaged goods: only isolated documented steps exist (e.g. Amul butter 62->58, ghee 650->610 on 22 Sep 2025, GST cut). Official butter/ghee indices rose ~3.5% after Oct 2025, so a flat register would be wrong. ToS blocks e-commerce scraping."),
 "No machine-readable source: fares/fees/services": (["T003","E001","E002","E003","E004","M002","M003","M004","P004","S001","S003","D001","D003","R004"], "Bus/auto fares (latest press is 2022), school/tuition fees, doctor/hospital, haircut, cinema, street food, newspaper, RMC water (increase only proposed)."),
 "Judged unrepresentative (kept official-linked on purpose)": (["M001"], "NPPA paracetamol ceiling is real but one controlled drug is a worse proxy for 'medicines' than the broad official index."),
 "No revision found / unverifiable": (["K001","K003","S002"], "Telecom/broadband/OTT: last verified hike Jul 2024; no later revision found, which is not proof of none."),
 "Genuinely no data": (["T005"], "No official item and no independent source."),
}
plan = pd.read_csv("data/source_plan.csv", dtype=str)
w = pd.read_csv("data/weights_cpi2024_gujarat_urban.csv"); wc = [c for c in w.columns if "weight" in c][0]
b = pd.read_csv("data/basket.csv", dtype=str)
m = plan.merge(w[["item_id", wc]], on="item_id").merge(b[["item_id", "name"]], on="item_id")
cur = m[m["class"] == "independent"][wc].sum()
lines = ["# Coverage ceiling (2026-10-02)", "", f"Independent weight today: **{cur:.1f}%**. Target 40% needs **+{40-cur:.1f} points**.", "",
         "| Blocker | Items | Weight % | What I found |", "|---|---|---|---|"]
seen, tot = set(), 0
for k, (ids, why) in BLOCK.items():
    sub = m[m.item_id.isin(ids) & (m["class"] != "independent")]
    seen |= set(sub.item_id); wt = sub[wc].sum(); tot += wt
    lines.append(f"| {k} | {len(sub)} ({', '.join(sub.item_id)}) | {wt:.1f} | {why} |")
rest = m[(m["class"] != "independent") & ~m.item_id.isin(seen)]
if len(rest):
    lines.append(f"| UNCLASSIFIED | {len(rest)} ({', '.join(rest.item_id)}) | {rest[wc].sum():.1f} | |")
lines += ["", f"Sum of blocked weight: {tot + rest[wc].sum():.1f}% (= 100 - {cur:.1f}).", "",
          f"## Best case per unlock (cumulative, from {cur:.1f}%)",
          "| Unlock | + points | Independent % after |", "|---|---|---|"]
def add(ids): return m[m.item_id.isin(ids) & (m["class"] != "independent")][wc].sum()
steps = [("Own rent survey (R001)", ["R001"]),
         ("+ DoCA-class staples (own kirana survey or captcha-free feed)", BLOCK["Captcha-gated (DoCA retail price monitor)"][0]),
         ("+ own packaged-goods price survey (fixed brand packs)", BLOCK["Brand MRP, history incomplete (not safe to register)"][0])]
run = cur
for name, ids in steps:
    a = add(ids); run += a
    lines.append(f"| {name} | +{a:.1f} | {run:.1f} |")
lines += ["", "Reading: no *automatable, permitted, real* feed remains for any block >2%. 40% is reachable only through data we collect ourselves "
          f"(rent alone gets to ~{cur + add(['R001']):.0f}%; rent + staples to ~{cur + add(['R001']) + add(BLOCK['Captcha-gated (DoCA retail price monitor)'][0]):.0f}%)."]
open("data/official/coverage_ceiling.md", "w").write("\n".join(lines))
print("\n".join(lines))
