"""One command that pulls every live source, rebuilds, audits and (if the gates pass) publishes.

    python -m rpi refresh            # network on
    python -m rpi refresh --offline  # skip network steps, rebuild from what is in the DB

Each step is isolated: a failing source is logged and skipped, never fatal. Result is appended to
data/refresh_log.csv and written to docs/data/status.json (what updated, what failed, coverage split).
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import pandas as pd

from . import db, ingest
from .collectors.base import PoliteClient, SnapshotStore
from .collectors import labour_bureau as lb
from .collectors.mospi_cpi import fetch_cpi
from .collectors.official_link import OfficialLinkCollector, independent_cutoffs, linked_items, trim_official_overlap
from .collectors.tariff_events import TariffEventCollector
from .collectors.web_sources import AcropCollector, EggCollector, MandiCollector, MetalsCollector, PngCollector, URLS, YardBoardCollector
from .fuel_events import update_file
from .http_compat import session

OFFICIAL_CSV = "data/official/mospi_cpi2024_gujarat_urban.csv"


def _step(name, fn, results):
    t = time.time()
    try:
        msg = fn()
        results.append({"step": name, "status": "ok", "seconds": round(time.time() - t, 1), "detail": str(msg)[:300]})
    except Exception as e:  # noqa: BLE001
        results.append({"step": name, "status": "error", "seconds": round(time.time() - t, 1), "detail": f"{type(e).__name__}: {e}"[:300]})


# acrop 'chana' pools desi (yellow) and kabuli (white) varieties -> not a clean chana-dal series; replaced by the named-variety yard board.
RETIRED_SERIES = (("mandi_rajkot_apmc", "F005"),)


def reset_tariff_series(conn) -> str:
    n = conn.execute("DELETE FROM observations WHERE sku_id IN (SELECT sku_id FROM products WHERE source_id='tariff')").rowcount
    conn.commit()
    return f"cleared {n} tariff observation(s) for rebuild from registers"


def run_crosscheck(conn, client) -> tuple[str, list[dict]]:
    from .crosscheck import GONDAL_URL, URL, crosscheck_apmc, crosscheck_gondal
    res: list[dict] = []
    for url, fn in ((URL, crosscheck_apmc), (GONDAL_URL, crosscheck_gondal)):
        r = client.get(url)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} for {url}")
        res += fn(conn, r.text)
    bad = [f"{x['board']}:{x['item_id']}" for x in res if x["verdict"] == "DISAGREE"]
    if bad:
        raise RuntimeError(f"APMC CROSS-CHECK DISAGREES (acrop modal outside the yard board band): {bad}")
    return ", ".join(f"{x['board']}:{x['item_id']}={x['verdict']}" for x in res), res


def run_crosscheck_ibja(conn, client) -> tuple[str, list[dict]]:
    from .crosscheck import IBJA_URL, crosscheck_ibja
    r = client.get(IBJA_URL)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} for {IBJA_URL}")
    res = crosscheck_ibja(conn, r.text)
    bad = [x["item_id"] for x in res if x["verdict"] == "DISAGREE"]
    if bad:
        raise RuntimeError(f"IBJA CROSS-CHECK DISAGREES (goodreturns outside the pre-set band around the IBJA benchmark): {bad}")
    return ", ".join(f"IBJA:{x['item_id']}={x['verdict']}" + (f" (premium {x['premium_min']:+.1%}..{x['premium_max']:+.1%}, n={x['n_days']})" if x["n_days"] else "") for x in res), res


def prune_official_link(conn, plan_csv) -> str:
    """Official-linked rows are stand-ins. When an item gets an independent source (plan changes), its old official-linked
    SKU must go, otherwise the item would carry two competing quotes. Idempotent."""
    keep = set(linked_items(pd.read_csv(plan_csv, dtype=str, keep_default_na=False)))
    rows = conn.execute("SELECT sku_id, item_id FROM products WHERE source_id='official_link'").fetchall()
    drop = [r[0] for r in rows if r[1] not in keep]
    for sku in drop:
        conn.execute("DELETE FROM observations WHERE sku_id=?", (sku,))
        conn.execute("DELETE FROM products WHERE sku_id=?", (sku,))
    # Retired independent series (kept out on purpose; see the note per entry).
    for src, item in RETIRED_SERIES:
        for (sku,) in conn.execute("SELECT sku_id FROM products WHERE source_id=? AND item_id=?", (src, item)).fetchall():
            conn.execute("DELETE FROM observations WHERE sku_id=?", (sku,))
            conn.execute("DELETE FROM products WHERE sku_id=?", (sku,))
            drop.append(sku)
    conn.commit()
    return f"pruned {len(drop)} stale/retired SKU(s)" if drop else "nothing to prune"


def _png_collector(client, store, root: Path):
    """goodreturns PNG table + curated Gujarat Gas revisions (data/png_events.csv) overlaid while goodreturns lags."""
    c = PngCollector(client, store)
    c.events_path = root / "data/png_events.csv"
    return c


def refresh_registers(root: Path) -> str:
    """Rebuild register-driven series (electricity bill model) and warn about stale curated registers."""
    from .electricity import update_events_file
    from .registry import review
    msg = update_events_file(root / "data/tariff_events.csv", root / "data/electricity_base_tariff.csv", root / "data/fppas_schedule.csv")
    warns = review(root / "data/tariff_events.csv", extra={"R005": root / "data/png_events.csv"})
    if warns:
        raise RuntimeError("STALE REGISTER: " + " | ".join(warns))     # surfaces as a visible error step, never silent
    return msg


def refresh_mospi(root: Path, sess=None) -> str:
    """Re-pull MoSPI only if the API has more records than we hold for the current/previous year."""
    sess = sess or session()
    path = root / OFFICIAL_CSV
    old = pd.read_csv(path, dtype={"code": str}) if path.exists() else pd.DataFrame()
    year = dt.date.today().year
    r = sess.get("https://api.mospi.gov.in/api/cpi/getCPIData", params=dict(
        base_year="2024", series="Current", year=str(year), state_code=10, sector_code=2, limit=10, page=1), timeout=90)
    j = r.json()
    if "data" not in j:
        raise RuntimeError(f"unexpected MoSPI response: {str(j)[:150]}")
    remote = int(j["meta_data"]["totalRecords"])
    local = int((old["period"].astype(str).str[:4] == str(year)).sum()) if len(old) else 0
    if remote == local:
        return f"up to date ({local} rows for {year}); latest {old['period'].max()}"
    new = fetch_cpi(years=(year - 1, year), raw_dir=root / "data/sources_raw/mospi_cpi", sess=sess)
    new.to_csv(path, index=False)
    return f"refreshed: {len(old)} -> {len(new)} rows; latest {new['period'].max()}"


def refresh_labour_bureau(root: Path, client) -> str:
    r = client.get(lb.HOME)
    url = lb.find_letter_url(r.text)
    if not url:
        raise RuntimeError("no CPI-IW letter link found on home page")
    period = lb.letter_period(url)
    out = root / "data/official/official_series.csv"
    cur = pd.read_csv(out)
    if ((cur.series_id == "CPIIW_RAJKOT") & (cur.period == period)).any():
        return f"{period} already loaded"
    pdf = client.get(url)
    vals = lb.parse_letter_pdf(pdf.content, period)
    if not vals:
        raise RuntimeError("Rajkot row not found in letter")
    add = pd.DataFrame([{"series_id": "CPIIW_RAJKOT", "period": p, "value": v, "source_url": url} for p, v in vals.items()])
    cur = pd.concat([cur[~((cur.series_id == "CPIIW_RAJKOT") & cur.period.isin(vals))], add]).sort_values(["series_id", "period"])
    cur.to_csv(out, index=False)
    return f"loaded Rajkot CPI-IW {vals}"


def refresh_cpi_iw_centres(root: Path, client) -> str:
    """Accrue the Labour Bureau CPI-IW centre table (Gujarat) from the home page; back-fill Rajkot months into official_series.csv.

    Informational benchmark only (different population and weights): see rpi/benchmark.py."""
    from .benchmark import load_centres, merge_centres
    r = client.get(lb.HOME)
    vals = lb.parse_state_popover(r.text, "GUJARAT")
    if not vals:
        raise RuntimeError("Gujarat centre table not found on the Labour Bureau home page")
    n = merge_centres(root, vals, lb.HOME, dt.date.today().isoformat())
    cen = load_centres(root)
    out = root / "data/official/official_series.csv"
    cur = pd.read_csv(out)
    have = set(cur.loc[cur.series_id == "CPIIW_RAJKOT", "period"].astype(str))
    add = [{"series_id": "CPIIW_RAJKOT", "period": p, "value": float(v), "source_url": lb.HOME}
           for p, v in cen["Rajkot"].dropna().items() if p not in have]
    if add:
        pd.concat([cur, pd.DataFrame(add)]).sort_values(["series_id", "period"]).to_csv(out, index=False)
    return f"{n} centre-month value(s) added/changed; Rajkot series +{len(add)} month(s) in official_series.csv; latest {cen.index.max()}"


def _post_publish(root: Path, settings: dict, out: dict, results: list) -> None:
    """Diagnostics that need the published series: CPI-IW benchmark, regulatory event checks, nowcast vintage log + scoring."""
    tot_csv = root / settings["paths"]["out"] / "data" / "rpi_total.csv"
    if not tot_csv.exists():
        return
    tot = pd.read_csv(tot_csv)
    tot["period"] = tot["period"].astype(str)
    ref = (out.get("publish") or {}).get("reference_period")
    nowc = tot[tot["nowcast"].astype(str).str.lower() == "true"]["period"] if "nowcast" in tot else pd.Series(dtype=str)
    series = tot.set_index("period")["index"].astype(float)

    def _bench():
        from .benchmark import compare
        off = pd.read_csv(root / "data/official/official_series.csv")
        gu = off[off.series_id == "CPI2024_GUJARAT_URBAN_GENERAL"].set_index("period")["value"].astype(float)
        out["benchmarks"] = {"cpi_iw_rajkot": compare(root, series[~series.index.isin(nowc)], gu, ref),
                             "note": "CPI-IW is a different population/weighting; information only, never feeds the index."}
        b = out["benchmarks"]["cpi_iw_rajkot"]
        return f"{b.get('status')}; YoY at {b.get('yoy_pct_at')}; MoM corr {b.get('mom_corr_rpi_vs_cpi_iw_rajkot')}"
    _step("benchmark:cpi_iw", _bench, results)

    def _events():
        from .event_check import check_events
        out["event_checks"] = check_events(root)
        return "; ".join(f"{e['item_id']} pass-through {e.get('pass_through_ratio')} ({e['verdict']})" for e in out["event_checks"]) or "none"
    _step("check:regulatory_events", _events, results)

    def _vint():
        from .nowcast_eval import log_vintages, score_vintages
        n = log_vintages(root, series.rename(index=lambda p: pd.Period(p, "M")), ref, out.get("run_id", ""))
        sc = score_vintages(root, series[~series.index.isin(nowc)].rename(index=lambda p: pd.Period(p, "M")))
        out["nowcast_realtime_score"] = sc
        return f"logged {n} nowcast(s); {sc.get('n_scored', 0)} month(s) scored against later official data"
    _step("log:nowcast_vintages", _vint, results)


def refresh_fuel(root: Path, client) -> str:
    pages = {}
    for item, key in (("T001", "petrol"), ("T002", "diesel"), ("R003", "lpg")):
        pages[item] = client.get(URLS[key]).text
    log = update_file(root / "data/tariff_events.csv", pages)
    return "; ".join(log) or "no price changes"


def refresh_mrp(root: Path, client) -> str:
    """Daily: read Jockey's live product JSON and add a dated event for every pool SKU whose price changed.
    Events go to the file where the series lives: data/tariff_events.csv for a promoted item, else the quarantine file data/mrp/jockey_events.csv."""
    from .collectors import mrp
    if not (root / mrp.POOL).exists() or not (root / "data/mrp/jockey_events.csv").exists():
        return "no MRP pool/quarantine yet (run scripts/build_mrp_history.py then scripts/build_mrp_register.py)"
    pool = pd.read_csv(root / mrp.POOL, dtype={"sku": str})
    products = []
    for pg in range(1, 40):
        got = json.loads(client.get(f"https://www.jockey.in/products.json?limit=250&page={pg}").text)["products"]
        if not got:
            break
        products += got
    if len(products) < 500:
        raise RuntimeError(f"Jockey feed returned only {len(products)} products; not trusting it")
    live = mrp.parse_live(products)
    qp, tp = root / "data/mrp/jockey_events.csv", root / "data/tariff_events.csv"
    q, t = pd.read_csv(qp), pd.read_csv(tp)
    for d in (q, t):
        d["series"] = d["series"].fillna("")
    today = dt.date.today()
    promoted = set(t.loc[t.series.str.startswith("jockey:"), "item_id"])
    new, warn = mrp.live_updates(q, pool, live, today)          # the quarantine file always carries the full history
    if new:
        pd.concat([q, pd.DataFrame(new)], ignore_index=True).to_csv(qp, index=False)
        mirror = [n for n in new if n["item_id"] in promoted]
        if mirror:
            pd.concat([t, pd.DataFrame(mirror)], ignore_index=True).to_csv(tp, index=False)
    if len(warn) > 0.3 * len(pool):
        raise RuntimeError(f"{len(warn)} of {len(pool)} MRP pool SKUs missing from the live feed: {warn[:5]}")
    return (f"{len(products)} products read; {len(new)} price change(s); {len(warn)} pool SKU(s) missing from feed; "
            f"promoted into index: {sorted(promoted) or 'none'}")


def run_refresh(root: Path, settings: dict, offline: bool = False, bootstrap_reps: int | None = None) -> dict:
    from .audit import run_audit
    from .index.engine import run_index
    from .publish import publish, DemoGuard, CoverageGuard
    from .quality import coverage_split

    results: list[dict] = []
    ua = settings["collectors"]["user_agent"]
    import os
    import requests
    sess = requests.Session()
    if os.path.exists("/etc/ssl/certs/ca-certificates.crt"):     # some gov sites omit an intermediate cert; system store has it
        sess.verify = "/etc/ssl/certs/ca-certificates.crt"
    client = PoliteClient(ua, min_delay=float(settings["collectors"].get("min_delay_seconds", 2.0)), session=sess)
    conn = db.connect(root / settings["paths"]["db"])
    store = SnapshotStore(conn, root / settings["paths"]["raw"])

    if not offline:
        _step("official:mospi_cpi", lambda: refresh_mospi(root), results)
        _step("official:labour_bureau", lambda: refresh_labour_bureau(root, client), results)
        _step("official:cpi_iw_centres", lambda: refresh_cpi_iw_centres(root, client), results)
        _step("tariff:fuel_lpg_update", lambda: refresh_fuel(root, client), results)
        _step("tariff:mrp_live", lambda: refresh_mrp(root, client), results)
    _step("tariff:registers", lambda: refresh_registers(root), results)

    ingest.load_basket(conn, pd.read_csv(root / settings["paths"]["basket"], dtype={"division": str}))
    ingest.load_weights(conn, pd.read_csv(root / settings["paths"]["weights"]))

    # Tariff series are a pure function of the registers: rebuild them from scratch so an edited/re-dated register row can never
    # leave orphaned months behind in the database.
    _step("reset:tariff_series", lambda: reset_tariff_series(conn), results)
    _step("prune:official_link", lambda: prune_official_link(conn, root / "data/source_plan.csv"), results)
    # Order matters: independent feeds first, so the official stand-in can be cut off where an independent series begins.
    collectors = [("tariff", TariffEventCollector(root / settings["paths"]["tariff_events"]))]
    doca_state: dict = {"ok": False, "check": []}
    if not offline:
        def _doca_check():
            from .collectors.doca import run_mirror_check
            msg, res = run_mirror_check(client)
            doca_state["check"] = res
            bad = [r for r in res if r["verdict"] != "agree"]
            if bad:
                raise RuntimeError(f"DoCA mirror NOT verified, DoCA feed skipped: {msg}; {bad[:3]}")
            doca_state["ok"] = True
            return msg
        _step("check:doca_mirror", _doca_check, results)
    if not offline:
        collectors += [("gr_metals", MetalsCollector(client, store)), ("mandi_gondal", MandiCollector(client, store)),
                       ("mandi_rajkot_apmc", AcropCollector(client, store, "mandi_rajkot_apmc")),
                       ("mandi_rajkot_veg", AcropCollector(client, store, "mandi_rajkot_veg")),
                       ("mandi_rajkot_district", AcropCollector(client, store, "mandi_rajkot_district")),
                       ("yard_rajkot_board", YardBoardCollector(client, store)),
                       ("gr_png", _png_collector(client, store, root)), ("necc_ahmedabad", EggCollector(client, store))]
        from .collectors.dmart import DmartCollector     # Ahmedabad DMart Ready shelf prices; own 4 s client (WAF rate limit), stops on first non-200
        collectors.append(("dmart_ahmedabad", DmartCollector(PoliteClient(ua, min_delay=4.0, retries=1, session=session()), store, root=root)))
        if doca_state["ok"]:
            from .collectors.doca import DocaRetailCollector
            collectors.append(("doca_rajkot", DocaRetailCollector(client, store)))
            from .collectors.doca import DocaNationalCollector
            collectors.append(("doca_national", DocaNationalCollector(client, store)))
            from .collectors.doca import DocaGujaratCollector
            collectors.append(("doca_gujarat", DocaGujaratCollector(client, store)))
    for name, col in collectors:
        _step(f"ingest:{name}", lambda col=col: ingest.run_collector(conn, col), results)
    _step("ingest:official_link", lambda: ingest.run_collector(conn, OfficialLinkCollector(
        root / OFFICIAL_CSV, root / "data/basket_official_map.csv", root / "data/source_plan.csv", cutoff=independent_cutoffs(conn))), results)
    _step("trim:official_overlap", lambda: trim_official_overlap(conn, pd.read_csv(root / "data/source_plan.csv", dtype=str, keep_default_na=False)), results)

    xchecks: list[dict] = []
    if not offline:
        def _xc():
            msg, res = run_crosscheck(conn, client)
            xchecks.extend(res)
            return msg
        _step("crosscheck:apmc", _xc, results)

        def _xi():
            msg, res = run_crosscheck_ibja(conn, client)
            xchecks.extend(res)
            return msg
        _step("crosscheck:ibja", _xi, results)

    proxies: list[dict] = []

    def _proxy_step():
        from .proxy_check import validate_proxies
        proxies.extend(validate_proxies(conn, root / OFFICIAL_CSV, root / "data/basket_official_map.csv", root / "data/source_plan.csv"))
        bad = [p["item_id"] for p in proxies if p["verdict"] == "fail"]
        pend = sum(p["verdict"] == "pending" for p in proxies)
        if bad:
            raise RuntimeError(f"PROXY FAILS VALIDATION vs official item index: {bad}")
        return f"{sum(p['verdict'] == 'pass' for p in proxies)} pass, {pend} pending (<6 overlapping months), 0 fail"
    _step("validate:proxies", _proxy_step, results)

    doca_screen: list[dict] = []
    if not offline:
        def _doca_screen():
            from .collectors.doca import screen_candidates
            doca_screen.extend(screen_candidates(client, root / OFFICIAL_CSV, root / "data/basket_official_map.csv", store))
            ok = [r["item_id"] for r in doca_screen if r.get("verdict") == "pass"]
            return f"{len(doca_screen)} unwired DoCA series screened; eligible to wire: {ok or 'none'}"
        _step("screen:doca_retail", _doca_screen, results)

        def _doca_nat_screen():
            from .collectors.doca import screen_national
            doca_screen.extend(screen_national(client, root / OFFICIAL_CSV, root / "data/basket_official_map.csv", store))
            r = [x for x in doca_screen if x.get("panel") == "all-India"]
            ok = [x["item_id"] for x in r if x.get("verdict") == "pass"]
            return "; ".join(f"{x['item_id']} {x['verdict']} (corr={x.get('corr')}, drift={x.get('drift')})" for x in r) + f"; eligible to wire: {ok or 'none'}"
        _step("screen:doca_national", _doca_nat_screen, results)

    mrp_screen: list[dict] = []
    if (root / "data/mrp/jockey_events.csv").exists():
        def _mrp_screen():
            from .collectors import mrp
            q = pd.read_csv(root / "data/mrp/jockey_events.csv")
            q["series"] = q["series"].fillna("")
            mrp_screen.extend(mrp.gate(q, root / OFFICIAL_CSV, root / "data/basket_official_map.csv", dt.date.today()))
            return "; ".join(f"{r['item_id']} {r['verdict']} (n={r['n_overlap']}, corr={r['corr']}, drift={r['drift']}, {r['n_skus']} SKUs)" for r in mrp_screen)
        _step("screen:jockey_mrp", _mrp_screen, results)

    rent_stats: list[dict] = []
    if not offline:
        def _rent_accrue():
            from .collectors.rent_listings import LIST_URLS, monthly_stats, qualifying_months, update_file
            tot_new = 0
            for u in LIST_URLS:
                n, new = update_file(root / "data/rent_listings.csv", client.get(u).text, u)
                tot_new += new
            rent_stats.extend(monthly_stats(root / "data/rent_listings.csv"))
            return (f"{tot_new} new listing(s); {qualifying_months(rent_stats)} month(s) with >=25 kept listings "
                    f"(rule: >=2 consecutive + gate before R001 can use it; diagnostic only)")
        _step("accrue:rent_listings", _rent_accrue, results)

    if not offline:
        def _mrp_diary():
            from .collectors import mrp_diary
            n, msg = mrp_diary.accrue(root / "data/mrp_diary.csv", client)
            return f"{n} SKU quote(s) today; {msg}"
        _step("accrue:mrp_diary", _mrp_diary, results)

    def _nowcast_eval():
        from .nowcast_eval import run_backtest
        r = run_backtest(root)
        m, b = r["methods"], r["band"]
        return (f"own-trend h1 RMSE {m['own_trend']['h1']['rmse_pp']}pp (zero {m['zero_change']['h1']['rmse_pp']}, old peer-fill "
                f"{m['old_division_peer_fill']['h1']['rmse_pp']}); 90% band +/-{b['h1_abs_log'] * 100:.2f}% (h1), +/-{b['h2_abs_log'] * 100:.2f}% (h2)")
    _step("evaluate:nowcast", _nowcast_eval, results)

    if bootstrap_reps:
        settings = {**settings, "index": {**settings["index"], "bootstrap_reps": bootstrap_reps}}
    out = {"steps": results}
    try:
        run = run_index(conn, settings)
        out["run_id"] = run.run_id
        results.append({"step": "build", "status": "ok", "seconds": 0, "detail": f"run {run.run_id}"})
    except Exception as e:  # noqa: BLE001
        results.append({"step": "build", "status": "error", "seconds": 0, "detail": f"{type(e).__name__}: {e}"[:300]})
        run = None

    if run is not None:
        _step("audit", lambda: json.dumps(run_audit(root)["basket"])[:200], results)
        try:
            out["publish"] = publish(conn, root / settings["paths"]["out"], "CPI2024_GUJARAT_URBAN_GENERAL", allow_demo=False)
            results.append({"step": "publish", "status": "ok", "seconds": 0, "detail": str(settings["paths"]["out"])})
        except (DemoGuard, CoverageGuard) as e:
            results.append({"step": "publish", "status": "blocked", "seconds": 0, "detail": str(e)[:300]})
    if run is not None:
        _post_publish(root, settings, out, results)
    out["coverage"] = coverage_split(conn, root / "data/source_plan.csv")
    out["proxy_validation"] = proxies
    out["cross_checks"] = xchecks
    out["doca_mirror_check"] = doca_state["check"]
    out["doca_screen"] = doca_screen
    out["rent_listings_monthly"] = rent_stats
    out["mrp_screen"] = mrp_screen
    log = pd.DataFrame(results).assign(at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    lp = root / "data/refresh_log.csv"
    log.to_csv(lp, mode="a", header=not lp.exists(), index=False)
    sp = root / settings["paths"]["out"] / "data"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / "status.json").write_text(json.dumps(out, indent=2, default=str))
    return out
