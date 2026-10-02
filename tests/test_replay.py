from pathlib import Path

import pandas as pd

from rpi.config import ROOT, load_settings
from rpi.replay import _run


def test_replay_hides_official_after_cutoff_and_keeps_history():
    s = load_settings()
    db = ROOT / "data/rpi.sqlite"
    full, _ = _run(db, s, None)
    cut, _ = _run(db, s, "2026-05")
    c = pd.Period("2026-05", "M")
    # up to the cut-off the replayed index is identical to the published one (nothing earlier was altered)
    assert abs(cut.total.loc[c] - full.total.loc[c]) < 1e-6
    # after the cut-off the official-linked weight is NOT observed any more, so the engine is nowcasting
    assert cut.coverage.loc[pd.Period("2026-06", "M")] < full.coverage.loc[pd.Period("2026-06", "M")] - 0.3
