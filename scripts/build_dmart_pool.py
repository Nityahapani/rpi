"""Build the FIXED DMart SKU pool (data/dmart/pool.csv) from data/dmart/candidates.csv.

Selection rules, fixed on 2026-10-02 BEFORE any price history existed (so the pool cannot be fitted to price behaviour):
  * the SKU matches the basket spec (item name / pack size as close as DMart sells it), a plain mainstream variant (no limited editions,
    no combos, no whitening/medicated sub-variants);
  * in stock on the selection date; at least 2 distinct SKUs per item (matched-model Jevons needs >= 2);
  * brand diversity preferred (max 1 pack of the same product line, except where DMart lists a single brand);
  * the pool is never changed silently: a delisted SKU simply stops reporting, and replacing SKUs is a dated, committed edit of pool.csv.
F010 curd was added on 2026-10-03 (dated, committed edit): at the 2026-10-02 selection only one curd SKU was in stock; on 2026-10-03 two plain curds were (Amul Masti Curd 1 kg, Amul Masti Dahi 200 g). The probiotic / flavoured curds and the out-of-stock Milky Mist plain curd were left out by the same rules.
Not built for F003/F005/etc. (other sources).
Run: python3 scripts/build_dmart_pool.py
"""
import pandas as pd

PICKS = {
    "F007": [689176, 689182, 689178, 689170],                 # Gulab 870 g, Vimal 870 g, Ankur 870 g, Tirupati 910 g
    "F010": [1642067, 727088],                                # Amul Masti Curd 1 kg, Amul Masti Dahi 200 g (added 2026-10-03: the Ahmedabad store now lists two in-stock plain curds; see below)
    "F012": [11071, 848001, 11065, 11075, 11064],             # Gowardhan 905 g, Milky Mist 910 g, Amul cow ghee tin 905 g, Amul pure ghee tin 905 g, Dynamix 902 g
    "F014": [87529, 12066, 12026, 12062, 689360],             # Wagh Bakri Premium, Tata Gold, Red Label, Tata Agni, Wagh Bakri Dust (all 250 g)
    "F015": [11340, 11338],                                   # Tata Salt 1 kg, Aashirvaad iodised 1 kg
    "F016": [11222, 22001, 99516],                            # Ramdev 200 g, DMart Premia 200 g, Everest 500 g
    "F017": [11457, 11410, 11414, 11412, 438501],             # Parle-G 200 g, Marie Gold 250 g, Parle Marie 239.7 g, Vita Marie Gold 248 g, Patanjali Doodh 255 g
    "F018": [508002, 11598, 713366],                          # Maggi masala 280 g, Yippee magic masala 280 g, Top Ramen curry 280 g
    "F019": [799709, 799708, 799711],                         # Super white bread 400 g, crustless white 300 g, white 800 g
    "H001": [87534, 12948, 12969, 1698558, 12960],            # Surf Excel 1 kg, Rin 1 kg, Wheel 1 kg, Ariel 1 kg, Tide 970 g
    "H002": [13138, 861533, 814504, 1461021],                 # Vim gel 500 ml, Reflect refill 500 ml, Giffy 750 ml, Beco 750 ml
    "H003": [1565532, 65585, 546503],                         # Nippo 9 W, Eveready 9 W, Crompton Ecoglo 9 W
    "H004": [12871, 570001, 846503],                          # Hawkins Contura CB30 3 L, Hawkins Miss Mary MM30 3 L, Prestige Deluxe Plus 3 L
    "P001": [733185, 12573, 731307, 1456003, 12534],          # Lux 125 g, Pears 125 g, Dove 100 g, Dettol 4x100 g, Lifebuoy 4x125 g
    "P002": [12343, 12335, 12406, 735232, 12390],             # Dove, Clinic Plus, Sunsilk, TRESemme, Pantene (340 ml)
    "P003": [716511, 46570, 12756, 12726],                    # Colgate Strong Teeth 200 g, Patanjali Dant Kanti 200 g, Dabur Red 200 g, Closeup 150 g
    "M002": [998005, 998006, 998004],                         # Dettol antiseptic liquid 550 ml, 1 L, 250 ml
    "E003": [678502, 125502, 300502, 125501],                 # Freedom 172 pp, Tru Note 172 pp, Doms 140 pp, Tru Note 140 pp
}

c = pd.read_csv("data/dmart/candidates.csv", dtype={"sku": int})
rows = []
for it, skus in PICKS.items():
    for s in skus:
        r = c[(c.item == it) & (c.sku == s)].iloc[0]
        rows.append(dict(item_id=it, sku=int(s), cat=int(r["cat"]), brand=r.brand, name=r["name"], mrp_at_selection=r.mrp,
                         sale_at_selection=r.sale, selected_on="2026-10-03" if it == "F010" else "2026-10-02"))
pd.DataFrame(rows).to_csv("data/dmart/pool.csv", index=False)
print(len(rows), "SKUs;", pd.DataFrame(rows).groupby("item_id").size().to_dict())
