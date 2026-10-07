"""Partial pooling of the national DoCA proxy across states (rpi/pooling.py; inventory AK).  Rules fixed in advance: no-intercept slope on monthly log changes, tau^2 by method of
moments, leave-one-state-out and leave-future-out, test months 2025-07..2025-12 (coefficients from months before the target only).  Items: the wired national-panel items that also
have an official state index in 2025: rice (F002), tur (F003), chana dal (F005), banana (F024).
Run: PYTHONPATH=. python3 scripts/national_pooling_test.py"""
import json, sqlite3
import numpy as np, pandas as pd
from rpi import pooling as P, pooled_checks as pc

ITEM = {"F002": ("Rice", "01.1.1.1.1.01"), "F003": ("Tur dal", "01.1.7.6.1.01"), "F005": ("Chana dal", "01.1.7.6.1.05"), "F024": ("Banana", "01.1.6.1.1.01")}
conn = sqlite3.connect("data/rpi.sqlite")
nat = pd.read_sql("select p.item_id, substr(o.obs_date,1,7) m, avg(o.unit_price) v from observations o join products p on p.sku_id=o.sku_id where p.source_id='doca_national' group by 1,2", conn)
nat = nat[nat.item_id.isin(ITEM)].rename(columns={"m": "month", "v": "level"})
nat.to_csv("data/official/national_proxy_monthly.csv", index=False)
off = pd.read_csv("data/official/mospi_states_food_items_2025.csv", dtype={"code": str})
off["state"] = off.state.map(pc.norm_state)
frames = []
for it, (name, code) in ITEM.items():
    n = nat[nat.item_id == it].set_index("month").level.sort_index()
    dn = (np.log(n).diff()).dropna()
    for st, g in off[off.code == code].groupby("state"):
        if st == "all india":
            continue
        lv = g.drop_duplicates("period").set_index("period").index_value.sort_index()
        do = np.log(lv).diff().dropna()
        for t in do.index:
            if t in dn.index:
                frames.append(dict(item=name, state=st, t=t, dn=float(dn[t]), do=float(do[t])))
df = pd.DataFrame(frames)
res = pd.concat([P.loso_lfo(df, name, "2025-07") for name, _ in ITEM.values()])
summ = P.summarise(res)
guj = res[res.state == "gujarat"]
out = dict(n_states=int(df.state.nunique()), n_pairs=len(df), summary=summ.to_dict("records"), gujarat_only=P.summarise(guj).to_dict("records"),
           pooled_b_all_states={n: round(P.pooled_slope(df[df.item == n])[0], 3) for n, _ in ITEM.values()},
           gujarat_own_b={n: round(P.slope(df[(df.item == n) & (df.state == "gujarat")].dn.values, df[(df.item == n) & (df.state == "gujarat")]["do"].values)[0], 3) for n, _ in ITEM.values()},
           tau2={n: round(P.tau2_mom(df[df.item == n]), 4) for n, _ in ITEM.values()})
df.to_csv("data/official/national_pooling_panel.csv", index=False)
res.to_csv("data/official/national_pooling_errors.csv", index=False)
json.dump(out, open("data/official/national_pooling_summary.json", "w"), indent=1)
print(summ.to_string()); print("Gujarat only"); print(P.summarise(guj).to_string()); print(out["pooled_b_all_states"], out["gujarat_own_b"], out["tau2"], out["n_states"], out["n_pairs"])
