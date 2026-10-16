from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rpi.proxy_check import official_series
from rpi.refresh import build_official_item_splice
from scripts.build_official_spliced import build

ROOT = Path(__file__).resolve().parent.parent


def test_checked_in_splice_rebuilds_from_cpi2012_and_cpi2024_inputs():
    rebuilt, offsets = build(ROOT)
    saved = pd.read_csv(ROOT / "data/official/official_item_spliced.csv", dtype={"item_id": str, "period": str})
    assert rebuilt.item_id.nunique() >= 66
    assert rebuilt.period.min() == "2014-01"
    current_cpi2024 = pd.read_csv(ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", dtype={"period": str})
    assert rebuilt.period.max() == current_cpi2024.period.max()
    assert len(offsets) >= 60 and (offsets.overlap_months >= 6).all()
    assert len(saved) == len(rebuilt)
    assert saved[["item_id", "period", "segment"]].equals(rebuilt[["item_id", "period", "segment"]])
    assert np.allclose(saved.index_value, rebuilt.index_value, rtol=1e-12, atol=1e-12)


def test_proxy_comparator_requires_the_spliced_file(tmp_path):
    raw = ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv"
    with pytest.raises(FileNotFoundError, match="long official comparator missing"):
        official_series(raw, spliced_csv=tmp_path / "missing.csv")


def test_refresh_builder_recreates_splice_in_a_clean_data_root(tmp_path):
    (tmp_path / "data/official").mkdir(parents=True)
    for src, rel in (
        (ROOT / "data/basket_official_map.csv", "data/basket_official_map.csv"),
        (ROOT / "data/official/basket_to_cpi2012_map.csv", "data/official/basket_to_cpi2012_map.csv"),
        (ROOT / "data/official/mospi_cpi2012_gujarat_urban_items.csv", "data/official/mospi_cpi2012_gujarat_urban_items.csv"),
        (ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv", "data/official/mospi_cpi2024_gujarat_urban.csv"),
    ):
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    msg = build_official_item_splice(tmp_path)
    out = tmp_path / "data/official/official_item_spliced.csv"
    result = pd.read_csv(out, dtype={"item_id": str, "period": str})
    assert "2014-01" in msg and result.period.min() == "2014-01"
    assert result.period.max() == pd.read_csv(ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv").period.max()


def test_long_comparator_is_indexed_by_basket_item():
    off = official_series(
        ROOT / "data/official/mospi_cpi2024_gujarat_urban.csv",
        spliced_csv=ROOT / "data/official/official_item_spliced.csv",
    )
    assert {"F002", "F003", "F005", "F008", "F021", "F022", "F023"} <= set(off.columns)
    assert off.index.min() == "2014-01"
    assert off.index.max() == pd.read_csv(ROOT / "data/official/official_item_spliced.csv").period.max()
