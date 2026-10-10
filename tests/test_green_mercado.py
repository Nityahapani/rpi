from pathlib import Path

import pandas as pd

from rpi.collectors import green_mercado as gm

OPEN_PAGE = ('<div class="product_con"><h3 class="product-title"><a href="x" title="Potato"><span>Potato</span></a>'
             '<div class="dispQty">1 kg</div></h3><div class="price-row"><span class="now">&#8377;30</span>'
             '<span class="was">&#8377;32</span></div><a href="javascript:;" data-id="2590,L,,564,1085,RD">')
CLOSED_PAGE = OPEN_PAGE + "<p>This store is not taking any orders right now.</p>"


def test_parse_reads_sale_and_list_price_and_pack():
    info = gm.parse_product(OPEN_PAGE)
    assert info == {"price": 30.0, "mrp": 32.0, "pack": "1 kg", "product_id": "2590"}


def test_closed_store_records_nothing_even_with_a_price():
    assert gm.parse_product(CLOSED_PAGE) is None
    assert not gm.store_open(CLOSED_PAGE)


def test_missing_or_out_of_band_price_is_refused():
    assert gm.parse_product("<p>no price here</p>") is None
    assert gm.parse_product(OPEN_PAGE.replace("&#8377;30", "&#8377;0")) is None


def test_pool_covers_the_four_produce_items_and_is_shadow_only():
    root = Path(__file__).resolve().parents[1]
    pool = gm.load_pool(root)
    assert set(pool.item_id) == {"F021", "F022", "F023", "F025"}
    plan = pd.read_csv(root / "data/source_plan.csv", dtype=str, keep_default_na=False)
    assert "green_mercado" not in set(plan.primary_source)           # shadow: nothing switched
    assert gm.switched_items(root) == []
