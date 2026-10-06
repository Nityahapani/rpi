"""Harvest Gujarat Fee Regulatory Committee (FRC) APPROVED private-school fees for Rajkot (public regulator database, frcgujarat.org).

The site (no robots.txt, no login, no captcha) lists every regulated private school with its FRC-approved annual fee per standard for each
academic year 2017-18 .. 2026-27 ("Know Fee Structure" > Search School > view fee).  We read the same JSON the page's own "view fee" button reads
(POST /Home/GetFeesList), 1.5 s between requests, for the districts "Rajkot Corporation" (the city) and "RAJKOT" (rest of district, not used by default).
Output: data/frc/rajkot_fees.csv  (district, school_id, school, board, medium, standard, ay, fee).
Run: python3 scripts/frc_rajkot_fees.py [--district "Rajkot Corporation"]
"""
import csv, json, sys, time
from pathlib import Path
import requests

UA = {"User-Agent": "rpi-research/1.0 (+https://github.com/Nityahapani/rpi; public regulator data, 1.5 s spacing)"}
BASE = "https://frcgujarat.org"
DISTRICTS = {"Rajkot Corporation": "JDmmQZSmxjtpMUNp7Ay2ZQ==", "RAJKOT": "4gKpfoEUA4mfzpSOdf2rmQ=="}
AYS = {"Fee201920": "2019-20", "Fee202021": "2020-21", "Fee202122": "2021-22", "Fee202223": "2022-23", "Fee202324": "2023-24",
       "Fee202425": "2024-25", "Fee202526": "2025-26", "Fee202627": "2026-27", "PastPreviousYearFee": "2017-18?", "PreviousYearFee": "2018-19?"}
OUT = Path("data/frc/rajkot_fees.csv")


def models(html):
    i = html.find("var jsonModel=")
    if i < 0:
        return []
    j = html.find("];", i)
    return json.loads(html[i + len("var jsonModel="):j + 1])


def main(district="Rajkot Corporation"):
    from urllib.parse import quote
    s = requests.Session(); s.headers.update(UA)
    code = DISTRICTS[district]
    r = s.get(f"{BASE}/Home/SearchSchool?currentDistrict={quote(code)}&fisrtLoad=1", timeout=60)
    first = models(r.text)
    import re
    n = int(re.search(r"Showing\s+1\s+to\s+\d+\s+of\s+(\d+)\s+Entries", re.sub(r"<[^>]+>", " ", r.text)).group(1))
    pages = (n + 9) // 10
    rows, seen = [], set()
    for p in range(1, pages + 1):
        ms = first if p == 1 else models(s.get(f"{BASE}/Home/SearchSchool?page={p}&currentDistrict={quote(code)}", timeout=60).text)
        for m in ms:
            key = (m["Id"], m["Medium"])
            if key in seen:
                continue
            seen.add(key)
            time.sleep(1.5)
            fr = s.post(f"{BASE}/Home/GetFeesList", json={"schholdetails": m}, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=60)
            if fr.status_code != 200:
                print("skip", m["SchoolName"], fr.status_code); continue
            for f in fr.json():
                for k, ay in AYS.items():
                    if k.startswith("Fee") and f.get(k) not in (None, 0, 0.0):
                        rows.append([district, m["Id"], m["SchoolName"], m["Board"], m["Medium"], f["SanctionName"], ay, f[k]])
        print("page", p, "of", pages, "rows", len(rows), flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as fh:                      # full snapshot each run (the regulator's table is the record)
        w = csv.writer(fh)
        w.writerow(["district", "school_id", "school", "board", "medium", "standard", "ay", "fee"])
        w.writerows(rows)
    print("wrote", len(rows))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--district") + 1] if "--district" in sys.argv else "Rajkot Corporation")
