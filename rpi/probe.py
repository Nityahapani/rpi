"""`python -m rpi probe` - run this from YOUR network. Checks every source in data/sources.csv that has a probe_url.
The build sandbox could not reach data.gov.in / agmarknet.gov.in, so those collectors are fixture-tested only until you run this."""
from __future__ import annotations
import os
import pandas as pd
from .http_compat import session


def run_probe(root, timeout: float = 20.0) -> pd.DataFrame:
    src = pd.read_csv(root / "data/sources.csv", keep_default_na=False)
    s = session()
    rows = []
    for r in src[src["probe_url"] != ""].itertuples():
        url = os.path.expandvars(r.probe_url)
        if "$" in url:
            rows.append((r.source_id, "SKIPPED", "env var missing (set DATA_GOV_API_KEY)")); continue
        try:
            resp = s.get(url, timeout=timeout)
            ok = resp.status_code == 200 and (not r.probe_expect or r.probe_expect.lower() in resp.text.lower())
            rows.append((r.source_id, "OK" if ok else "FAIL", f"HTTP {resp.status_code}, {len(resp.content)} bytes"))
        except Exception as e:                                           # noqa: BLE001 - report, don't crash
            rows.append((r.source_id, "UNREACHABLE", type(e).__name__))
    return pd.DataFrame(rows, columns=["source_id", "result", "detail"])
