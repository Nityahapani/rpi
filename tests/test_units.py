from rpi.units import parse_quantity, unit_price

def test_parse():
    assert parse_quantity("Aashirvaad Atta 5 kg") == (5000.0, "g")
    assert parse_quantity("Oil 1.5 L pouch") == (1500.0, "ml")
    assert parse_quantity("Biscuits 6 x 100 g") == (600.0, "g")
    assert parse_quantity("Soap pack of 4") == (4.0, "pc")
    assert parse_quantity("Bananas 1 dozen") == (12.0, "pc")
    assert parse_quantity("Tea 250gm") == (250.0, "g")
    assert parse_quantity("nothing here") is None

def test_unit_price_shrinkflation_shows_as_increase():
    before = unit_price(100, 500, "g")      # Rs 200/kg
    after = unit_price(100, 450, "g")       # same sticker, smaller pack
    assert abs(before - 200) < 1e-9
    assert after > before
    assert unit_price(50, None, None) == 50
