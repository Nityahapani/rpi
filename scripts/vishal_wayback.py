"""Vishal Mega Mart men's clothing and footwear price history from Internet Archive captures of public product pages (schema.org Product JSON-LD price),
gated against the official item indices: topwear -> C001 (03.1.2.1.1.01), bottomwear -> C002 (03.1.2.1.1.02), footwear -> C003 (03.2.1.1.1.01).
Usage: PYTHONPATH=. python3 scripts/vishal_wayback.py [list|fetch|screen]
Rules fixed before any price was parsed: product pages (.../<sku>.html) under /en-in/mens-fashion/{topwear,bottomwear,footwear}/; captures with status 200 from
2025-01 to 2026-09; URLs with captures in >= 2 distinct months; one capture (the latest) per URL per month; SKU-month price = JSON-LD offer price (> 0);
matched-model Jevons chain (rpi.proxy_check.chain_series); the unchanged gate (rpi.proxy_check.judge); months after the official index ends are dropped."""
import os, re, sys, json, threading, requests, pandas as pd
from concurrent.futures import ThreadPoolExecutor

ITEMS = {"topwear": ("C001", "03.1.2.1.1.01"), "bottomwear": ("C002", "03.1.2.1.1.02"), "footwear": ("C003", "03.2.1.1.1.01")}
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; archive reader)"
lock = threading.Lock(); D = "data/vishal"
CAP, OUT, DONE = f"{D}/captures.csv", f"{D}/prices.csv", f"{D}/fetched.csv"


def list_captures():
    rows = []
    for sub in ITEMS:
        r = S.get("http://web.archive.org/cdx/search/cdx", params=dict(url=f"vishalmegamart.com/en-in/mens-fashion/{sub}/*", output="txt", fl="timestamp,original",
                  filter="statuscode:200", **{"from": "202501", "to": "202610"}), timeout=300)
        rows += [l.split(None, 1) + [sub] for l in r.text.splitlines() if l.strip()]
    d = pd.DataFrame(rows, columns=["ts", "url", "group"])
    d["url"] = d.url.str.strip().str.split("?").str[0].str.replace("http://", "https://").str.replace("://vishalmegamart", "://www.vishalmegamart")
    d = d[d.url.str.contains(r"/[0-9A-Za-z]+\.html$")].copy()
    d["month"] = d.ts.str[:6]
    keep = d.groupby("url").month.nunique(); keep = keep[keep >= 2].index
    d = d[d.url.isin(keep)].sort_values("ts").groupby(["url", "month"]).tail(1)
    os.makedirs(D, exist_ok=True); d.to_csv(CAP, index=False)
    print(d.url.nunique(), "urls", len(d), "captures", d.groupby("group").url.nunique().to_dict(), d.groupby("month").size().to_dict())


def parse(x):
    for m in re.finditer(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', x, re.S):
        try: j = json.loads(m.group(1))
        except Exception: continue
        for p in (j if isinstance(j, list) else [j]):
            if isinstance(p, dict) and p.get("@type") == "Product" and isinstance(p.get("offers"), dict):
                try:
                    v = float(p["offers"]["price"])
                    if v > 0: return v
                except Exception: pass
    return None


def fetch():
    cap = pd.read_csv(CAP, dtype=str)
    done = set()
    if os.path.exists(DONE):
        f = pd.read_csv(DONE, dtype=str); done = set(f.ts + f.url)

    def work(r):
        try: x = S.get(f"http://web.archive.org/web/{r.ts}id_/{r.url}", timeout=120)
        except Exception as e: print("ERR", r.ts, e, flush=True); return
        if x.status_code != 200: print("HTTP", x.status_code, r.ts, flush=True); return
        p = parse(x.text)
        with lock:
            if p: pd.DataFrame([dict(ts=r.ts, url=r.url, group=r.group, price=p)]).to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
            pd.DataFrame([dict(ts=r.ts, url=r.url, ok=int(p is not None))]).to_csv(DONE, mode="a", header=not os.path.exists(DONE), index=False)

    todo = [r for _, r in cap.sample(frac=1.0, random_state=7).iterrows() if r.ts + r.url not in done]
    with ThreadPoolExecutor(4) as ex: list(ex.map(work, todo))
    print("finished")


def screen():
    from rpi.proxy_check import chain_series, judge
    d = pd.read_csv(OUT, dtype={"ts": str}); d["m"] = d.ts.str[:4] + "-" + d.ts.str[4:6]
    off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    res = []
    for g, (item, code) in ITEMS.items():
        q = d[d.group == g]
        piv = q.groupby(["url", "m"]).price.median().unstack(0).sort_index()
        o = off[(off.level == "item") & (off.code == code)].set_index("period").index_value
        piv = piv[piv.index <= o.index.max()]
        lvl = chain_series(piv)
        j = judge(lvl, o)
        chg = (lvl.dropna().iloc[-1] / lvl.dropna().iloc[0] - 1) * 100 if lvl.notna().sum() > 1 else None
        oc = (o.reindex(lvl.dropna().index).iloc[-1] / o.reindex(lvl.dropna().index).iloc[0] - 1) * 100 if lvl.notna().sum() > 1 else None
        pd.DataFrame({"chain": lvl.round(2), "n_skus": piv.notna().sum(axis=1), "official_rebased": (o.reindex(lvl.index) / o[lvl.index[0]] * 100).round(2)}).to_csv(f"data/official/vishal_{item}_screen.csv")
        res.append(dict(item=item, group=g, n_urls=piv.shape[1], months=int(lvl.notna().sum()), chain_chg_pct=None if chg is None else round(float(chg), 1), official_chg_pct=None if oc is None else round(float(oc), 1), **j))
        print(res[-1])
    pd.DataFrame(res).to_csv("data/official/vishal_screen.csv", index=False)


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("list", "all"): list_captures()
    if step in ("fetch", "all"): fetch()
    if step in ("screen", "all"): screen()
