"""Pre-specified gate for OEA Wholesale Price Index (WPI) items as proxies for CPI basket items.

Thresholds fixed BEFORE looking at the numbers (written into this file first):
    corr  >= 0.5   Pearson correlation of month-on-month log changes, WPI item vs official Gujarat-urban CPI item
    drift <= 0.05  annualised |cum log change(WPI) - cum log change(official)| per year over the overlap
    n     >= 24    overlapping months for the long-history gate
Long gate: old-base WPI (2011-12=100, eaindustry.nic.in/indx_download_1112/monthly_index_202606.xls) against the
CPI-2012 Gujarat-urban item series (2014-01..2025-12).
Also reported (not gating): 3-month-change correlation and best lag, because wholesale leads retail.
"""
from __future__ import annotations
import sys
import numpy as np, pandas as pd

MIN_CORR, MAX_DRIFT_PA, MIN_N = 0.5, 0.05, 24
CAND = {  # basket item -> (CPI2012 item name, [WPI old-base codes])
    "C001": ("Shirts, T-shirts (no.)", ["1305010001"]),
    "C002": ("Shorts, Trousers, Bermudas (no.)", ["1305010002", "1305010000", "1305000000"]),
    "C003": ("Leather Sandals, Chappals, etc.", ["1306030004", "1306030001", "1306030000"]),
    "T006": ("Tyres & Tubes", ["1312010003", "1312010000"]),
    "K002": ("Mobile Handset", ["1316030001"]),
    "S003": ("Newspapers, Periodicals", ["1309010001", "1308010001"]),
    "E003": ("Books, Journals: First Hand", ["1309010005"]),
    "E004": ("Stationery, Photocopying Charges", ["1308010002"]),
}

def load_wpi(path):
    x = pd.read_excel(path, header=0)
    x["COMM_CODE"] = x["COMM_CODE"].astype(str)
    cols = [c for c in x.columns if str(c).startswith("INDX")]
    per = [f"{str(c)[6:10]}-{str(c)[4:6]}" for c in cols]
    t = x.set_index("COMM_CODE")[cols]; t.columns = per
    return t.apply(pd.to_numeric, errors="coerce"), x.set_index("COMM_CODE")["COMM_NAME"]

def stats(p, o):
    b = pd.concat([p.rename("p"), o.rename("o")], axis=1).dropna().sort_index()
    if len(b) < MIN_N: return dict(n=len(b))
    lg = np.log(b); d = lg.diff().dropna()
    c1 = d.p.corr(d.o)
    q = lg.diff(3).dropna(); c3 = q.p.corr(q.o)
    lag = {k: d.p.shift(k).corr(d.o) for k in (0, 1, 2, 3)}
    yrs = (len(b) - 1) / 12
    drift = abs((lg.p.iloc[-1] - lg.p.iloc[0]) - (lg.o.iloc[-1] - lg.o.iloc[0])) / yrs
    verdict = "pass" if (c1 >= MIN_CORR and drift <= MAX_DRIFT_PA) else "fail"
    return dict(n=len(b), start=b.index[0], end=b.index[-1], corr1=round(c1, 2), corr3=round(c3, 2),
                best_lag=max(lag, key=lambda k: lag[k] if lag[k] == lag[k] else -9), drift_pa=round(drift, 3), verdict=verdict)

def main(wpi_xls, cpi2012_csv):
    w, names = load_wpi(wpi_xls)
    o = pd.read_csv(cpi2012_csv)
    o = o.pivot_table(index="period", columns="item", values="index_value", aggfunc="first")
    rows = []
    for it, (cpi_name, codes) in CAND.items():
        if cpi_name not in o.columns: rows.append(dict(item=it, note="cpi name missing")); continue
        for c in codes:
            if c not in w.index: continue
            rows.append(dict(item=it, cpi=cpi_name, wpi_code=c, wpi=names[c].strip()[:45], **stats(w.loc[c].dropna(), o[cpi_name].dropna().loc[:"2025-12"])))
    df = pd.DataFrame(rows)
    return df

if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 30)
    df = main(sys.argv[1], sys.argv[2]); print(df.to_string())
    if len(sys.argv) > 3: df.to_csv(sys.argv[3], index=False)
