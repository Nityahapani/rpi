# Commands reference

Everything below is run from the repository root (`rpi/`). Last verified on Python 3.13. The lock file lists the pinned package versions.

## 1. Setup

```bash
pip install -r requirements.txt          # runtime + test dependencies
pip install -r requirements.lock.txt     # optional: exact pinned versions
```

Optional environment variable used by the daily workflow:

| Variable | Used by | Purpose |
|---|---|---|
| `DATA_GOV_API_KEY` | `refresh`, `daily`, Agmarknet collector | data.gov.in API key. Without it the Agmarknet step fails and is reported in `status.json`. |

Never put tokens or keys in committed files. Use environment variables only.

## 2. Make targets (shortcuts)

`make <target>` runs the matching command below.

| Target | Runs | Notes |
|---|---|---|
| `make test` | `python3 -m pytest -q` | Full test suite |
| `make demo` | `python3 -m rpi demo` | Synthetic data, safe offline |
| `make init` | `python3 -m rpi init` | Create the database and load the registry |
| `make daily` | `python3 -m rpi daily` | Daily publish (network) |
| `make refresh` | `python3 -m rpi refresh` | Full refresh of every source (network) |
| `make refresh-offline` | `python3 -m rpi refresh --offline` | Rebuild from stored data, no network |
| `make weights` | `python3 -m rpi.weights_build` | Rebuild weights |
| `make audit` | `python3 -m rpi audit` | Data audit |
| `make probe` | `python3 -m rpi probe` | Check that each source responds |
| `make official` | fetch MoSPI CPI | Official index only |
| `make eval` | `python3 -m rpi eval` | Backtest the index |
| `make diag` | `python3 -m rpi diag` | Diagnostics |
| `make uncertainty` | `python3 -m rpi uncertainty` | Confidence intervals |
| `make shadow` | `python3 -m rpi shadow` | Shadow-source report |
| `make replicate` | tests, then `eval`, then `diag` | Full reproduction check |
| `make lock` | writes `requirements.lock.txt` | Pin current versions |

## 3. Main pipeline (`python3 -m rpi`)

Global options (go before the subcommand): `--db PATH` (default `data/rpi.sqlite`), `--settings PATH` (default `config/settings.toml`).

| Command | What it does | Writes |
|---|---|---|
| `init [--weights FILE]` | Creates the database, loads the registry and weights | `data/rpi.sqlite` |
| `ingest {agmarknet,tariff,csv} [--path FILE]` | Loads one source | database |
| `build` | Computes the index from stored prices | database |
| `validate` | Runs the validation gates | stdout |
| `nowcast SERIES` | Nowcast for one series | stdout |
| `publish [--out DIR] [--official FILE] [--demo]` | Writes the public tables | `docs/data/`, `docs/index.html` |
| `health` | Source health summary | stdout |
| `audit` | Data audit | stdout |
| `probe` | Checks each source is reachable | stdout |
| `refresh [--offline] [--reps N]` | Runs every collector, rebuilds, publishes | database, `data/`, `docs/` |
| `daily [--out DIR] [--official CPIIW_RAJKOT] [--demo]` | The daily job the workflow runs | `docs/`, `data/` |
| `demo [--seed N]` | Synthetic demonstration run | demo database |
| `eval [--first YYYY-MM] [--horizons 1,2,3]` | Backtest | stdout / reports |
| `diag` | Diagnostics | stdout |
| `shadow` | Shadow-source report | stdout |
| `uncertainty [--reps N] [--weight-sigma X]` | Bootstrap intervals | stdout |

Examples:

```bash
python3 -m rpi init
python3 -m rpi refresh                  # network: every source
python3 -m rpi refresh --offline        # no network, rebuild from stored data
python3 -m rpi publish --out docs
python3 -m rpi eval --first 2025-01
```

**Careful:** `refresh`, `daily` and `publish` rewrite files in `docs/`, which is the live GitHub Pages site. The daily GitHub Actions workflow runs `refresh` every day and commits the result. Run these locally only when you mean to change the published output.

## 4. Dashboard (`docs/app/`)

The dashboard is static HTML and reads the files the pipeline writes. It has no build step.

```bash
python3 scripts/export_app_data.py      # rewrites docs/app/data/items.json
```

Run the export after a refresh if you want the item and weight views to show the latest run. The Index, Divisions and Refresh-health views read `docs/data/*.csv` and `status.json` directly and need no export.

To preview locally:

```bash
cd docs && python3 -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/app/
```

The public address is `https://nityahapani.github.io/rpi/app/`.

## 5. Econometrics module (`python3 -m econ`)

Shadow-only: reads pipeline outputs and writes only under `econ/outputs/` (git-ignored). Nothing here changes the published index.

| Command | Purpose |
|---|---|
| `python3 -m econ fit` | Fit the one-factor dynamic model |
| `python3 -m econ compare` | Compare variants |
| `python3 -m econ breaks` | Structural-break checks |
| `python3 -m econ report` | Write the report |
| `python3 -m econ freeze` | Freeze the prospective forecasts |
| `python3 -m econ log` | Show the forecast log |
| `python3 -m econ score` | Score forecasts whose outcome is now published |

Options: `--out DIR` (default `econ/outputs`).

The item-level model (`econ/items_model.py`) and its nested evaluation are called from Python; see its docstrings.

## 5b. Shadow report (`python3 -m shadowreport`)

Shadow-only: reads the repo data and writes only under `shadowreport/outputs/` (git-ignored). Nothing here changes the published index, a switch or a gate.

| Command | Purpose |
|---|---|
| `python3 -m shadowreport report` | Build the report, write `shadowreport/outputs/shadow_report.{json,md}`, print the summary (exit 0) |
| `python3 -m shadowreport check` | Same, exit 1 when the overall status is `fail`, `out_of_band` or `stale` |
| `python3 -m shadowreport feeds` | List the registered shadow feeds |

Options: `--as-of YYYY-MM-DD` (default: today; sets the staleness test), `--root DIR` (default: this repo), `--out DIR` (default: `shadowreport/outputs`).

Statuses, worst first: `fail`, `out_of_band`, `stale`, `no_quotes`, `pending`, `tracking`, `pass`. `inactive` is a known-closed source and does not count toward the overall status. The price band (±10%) and the 6-month overlap rule for rent are report settings in `shadowreport/feeds.py`.

## 6. Tests

```bash
python3 -m pytest -q                       # whole suite
python3 -m pytest -q tests/test_econ_dfm.py
python3 -m pytest -q tests/test_green_mercado.py
python3 -m pytest -q tests/test_shadowreport.py
python3 -m pytest -q -k rajkot_shops
```

Last full run: 320 passed, 2 skipped (the 2 skips need pdfplumber).

`pytest.ini` restricts collection to `tests/`. `tests/test_live_sources.py` checks live sources and needs network access.

## 7. Source-specific collectors

Each shadow or proxy source has a collector in `rpi/collectors/` and a pool file under `data/<source>/`. Examples:

Collectors honour `robots.txt` and the site's terms. A `RobotsDisallowed` or access-denied response is recorded as a refusal, not retried around.

Helper scripts in `scripts/` (run individually, see each file's docstring): for example `build_rajkot_shops_pool.py`, `build_vishal_pool.py`, `screen_doca_panels.py`, `ceda_all_states.py`, `mospi_all_states.py`, `pooled_accuracy.py`.

## 8. Git (safe use)

```bash
git status --short
git log --oneline -5
```

Commit identity used for this project: `Nityahapani <118457303+Nityahapani@users.noreply.github.com>`. Set it per command rather than in the config file:

```bash
git -c user.name=Nityahapani -c user.email=118457303+Nityahapani@users.noreply.github.com commit -m "message"
```

Pushing needs a token. Keep it in an environment variable and pass it through a one-shot credential helper so it is never written to disk or to `.git/config`:

```bash
export GH_TOKEN=...   # set in the shell, never committed
git -c credential.helper= -c 'credential.helper=!f(){ echo username=Nityahapani; echo "password=$GH_TOKEN"; }; f' \
  push https://github.com/Nityahapani/rpi.git HEAD:refs/heads/main
unset GH_TOKEN
```

Afterwards, check that the token is not stored: `git config --get-all credential.helper` should print nothing, and `~/.git-credentials` should not exist.

Generated outputs (`econ/outputs/`, `data/raw/`, `data/sources_raw/`, caches) are not committed unless someone asks for them.

## 9. Files you will touch most

| Path | Contents |
|---|---|
| `registry/items.csv` | Item authority: weights, sources, match quality, plan class |
| `config/settings.toml` | Settings, switches, index configuration |
| `data/rpi.sqlite` | Main database (about 45 MB, committed by the daily workflow) |
| `data/*_prices.csv` | Collected price quotes per shadow source |
| `docs/data/` | Public tables and `status.json` (written by `publish`) |
| `docs/app/` | Dashboard source (`index.html`, `data/items.json`) |
| `docs/index.html` | Old static site (regenerated by the daily job) |
| `.github/workflows/daily.yml` | Daily job definition |

## 10. Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `STALE REGISTER` error | A register's last change is older than its review cycle | Update the register with the new value and its date, then rerun |
| `RobotsDisallowed` | `robots.txt` could not be fetched or disallows the path | Leave it; do not work around it |
| `mirror unreachable` (DoCA) | The DoCA mirror did not respond | Rerun later; the feed is skipped meanwhile |
| Dashboard shows old numbers | Browser cache, or the daily job has not run | Hard-refresh; check `docs/data/status.json` `run_id` |
| Dashboard item view not updated | `items.json` is a snapshot | Run `python3 scripts/export_app_data.py` |
| Old site at `/rpi/` but no dashboard | Dashboard lives at `/rpi/app/` | Open the `/app/` address |
