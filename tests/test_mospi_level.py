import math

import pandas as pd

from rpi.collectors.mospi_cpi import _level


def test_nan_fields_do_not_promote_a_row_to_item():
    # the MoSPI API omits 'item' for division rows; pandas turns the missing value into NaN, which is truthy
    df = pd.DataFrame([
        {"division": "CPI (General)", "group": None, "class": None, "sub_class": None, "item": None},
        {"division": "Food and beverages", "group": None, "class": None, "sub_class": None, "item": float("nan")},
        {"division": "Food and beverages", "group": "Cereals", "class": None, "sub_class": None, "item": ""},
        {"division": "Food and beverages", "group": "Cereals", "class": None, "sub_class": None, "item": "Wheat flour"},
    ])
    labels = [_level(r) for r in df.to_dict("records")]
    assert labels[0] == ("general", "CPI (General)")
    assert labels[1] == ("division", "Food and beverages")
    assert labels[2] == ("group", "Cereals")
    assert labels[3] == ("item", "Wheat flour")


def test_nan_handled_for_every_level():
    r = {"division": "x", "group": float("nan"), "class": float("nan"), "sub_class": float("nan"), "item": float("nan")}
    assert _level(r) == ("division", "x")
    assert not math.isnan(0.0)  # sanity
