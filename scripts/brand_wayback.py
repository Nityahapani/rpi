"""Rebuild a brand e-store price history from Internet Archive captures of its public product pages (schema.org Product JSON-LD), then gate it.
Usage: PYTHONPATH=. python3 scripts/brand_wayback.py <brand> [list|fetch|screen]      brands: campus, bata
Rules (fixed before any price was parsed): men's footwear product URLs only (slug has a 'men' token, none of women/boys/girls/kids/junior/infant);
URLs with a 200 capture in >= 5 distinct months between 2025-07 and 2026-09; the first 200 by (months desc, url); one capture (the latest) per URL per month;
SKU-month price = median JSON-LD offer price; price <= 0 dropped; matched-model Jevons chain; the unchanged gate (rpi.proxy_check.judge) against the
official 'Footwear for men' item index (C003); the partial month after the official index ends is dropped."""
import os, re, sys, json, threading, requests, pandas as pd
from concurrent.futures import ThreadPoolExecutor

BR = {"campus": "campusshoes.com/products/*", "bata": "bata.com/in/*"}
MEN = re.compile(r"(?<![a-z])(men|mens)(?![a-z])")
NOT = re.compile(r"women|boys|girls|kids|kid-|junior|infant|ladies")
S = requests.Session(); S.headers["User-Agent"] = "RajkotPriceIndex/0.1 (research; archive reader)"
lock = threading.Lock()


def list_captures(brand):
    r = S.get("http://web.archive.org/cdx/search/cdx", params=dict(url=BR[brand], output="txt", fl="timestamp,original", filter="statuscode:200", **{"from": "202507", "to": "202610"}), timeout=300)
    d = pd.DataFrame([l.split() for l in r.text.splitlines() if l.strip()], columns=["ts", "url"])
    d["url"] = d.url.str.split("?").str[0].str.replace("http://", "https://")
    d["url"] = d.url.str.replace("://campusshoes.com", "://www.campusshoes.com").str.replace("://bata.com", "://www.bata.com")
    d = d[d.url.str.contains("/products/") if brand == "campus" else d.url.str.endswith(".html")]
    slug = d.url.str.rsplit("/", n=1).str[-1].str.lower()
    d = d[slug.map(lambda s: bool(MEN.search(s)) and not NOT.search(s))].copy()
    d["month"] = d.ts.str[:6]
    nm = d.groupby("url").month.nunique()
    keep = nm[nm >= 5].reset_index().sort_values(["month", "url"], ascending=[False, True]).head(200).url
    d = d[d.url.isin(keep)].sort_values("ts").groupby(["url", "month"]).tail(1)
    d.to_csv(f"data/brands/{brand}_captures.csv", index=False)
    print(brand, d.url.nunique(), "urls", len(d), "captures", d.groupby("month").size().to_dict())


def parse(x):
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', x, re.S):
        try: j = json.loads(m.group(1))
        except Exception: continue
        for p in (j if isinstance(j, list) else [j]):
            if isinstance(p, dict) and p.get("@type") == "Product" and p.get("offers"):
                of = p["offers"]; of = of if isinstance(of, list) else [of]
                pr = []
                for o in of:
                    v = o.get("price", o.get("lowPrice"))
                    try: pr.append(float(v))
                    except Exception: pass
                pr = [v for v in pr if v > 0]
                if pr: out.append(sorted(pr)[len(pr) // 2])
    return out[0] if out else None


def fetch(brand):
    cap = pd.read_csv(f"data/brands/{brand}_captures.csv", dtype=str)
    OUT, DONE = f"data/brands/{brand}_prices.csv", f"data/brands/{brand}_fetched.csv"
    done = set()
    if os.path.exists(DONE):
        f = pd.read_csv(DONE, dtype=str); done = set(f.ts + f.url)

    def work(r):
        try: x = S.get(f"http://web.archive.org/web/{r.ts}id_/{r.url}", timeout=120)
        except Exception as e: print("ERR", r.ts, e, flush=True); return
        if x.status_code != 200: print("HTTP", x.status_code, r.ts, flush=True); return
        p = parse(x.text)
        with lock:
            if p: pd.DataFrame([dict(ts=r.ts, url=r.url, price=p)]).to_csv(OUT, mode="a", header=not os.path.exists(OUT), index=False)
            pd.DataFrame([dict(ts=r.ts, url=r.url, ok=int(p is not None))]).to_csv(DONE, mode="a", header=not os.path.exists(DONE), index=False)

    todo = [r for _, r in cap.sample(frac=1.0, random_state=7).iterrows() if r.ts + r.url not in done]
    with ThreadPoolExecutor(4) as ex: list(ex.map(work, todo))
    print("finished", brand)


def screen(brand):
    from rpi.proxy_check import chain_series, judge
    d = pd.read_csv(f"data/brands/{brand}_prices.csv", dtype={"ts": str})
    d = d[d.price > 0].copy(); d["m"] = d.ts.str[:4] + "-" + d.ts.str[4:6]
    piv = d.groupby(["url", "m"]).price.median().unstack(0).sort_index()
    off = pd.read_csv("data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"code": str})
    o = off[(off.level == "item") & (off.code == "03.2.1.1.1.01")].set_index("period").index_value
    piv = piv[piv.index <= o.index.max()]
    lvl = chain_series(piv)
    j = judge(lvl, o)
    out = pd.DataFrame({"chain": lvl.round(2), "n_urls": piv.notna().sum(axis=1), "official_rebased": (o.reindex(lvl.index) / o[lvl.index[0]] * 100).round(2)})
    out.to_csv(f"data/official/{brand}_footwear_screen.csv"); print(out.to_string()); print(brand, j)


if __name__ == "__main__":
    b, step = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "all")
    os.makedirs("data/brands", exist_ok=True)
    if step in ("list", "all"): list_captures(b)
    if step in ("fetch", "all"): fetch(b)
    if step in ("screen", "all"): screen(b)
