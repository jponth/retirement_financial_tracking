# Retirement Financial Tracking

This repository contains a working retirement planning and tracking prototype with:

- a configurable product/display name
- typed domain models for retirement household data
- a local yearly forecast and calculation engine
- a Gradio-based planning UI
- workbook import/export for user-owned case files
- configurable tax modeling with either effective rates or bracket-based federal + Connecticut tables

## Module layout

- `src/retirement_financial_tracking/config/`
  - app metadata, configurable display name, and bundled tax-table JSON files
- `src/retirement_financial_tracking/domain/`
  - typed domain models for household settings, people, buckets, accounts, holdings, recurring cash flows, actual balances, withdrawal policy, and forecast output
- `src/retirement_financial_tracking/services/`
  - forecast logic, bucket replenishment, withdrawal-priority handling, deterministic return scenarios, and Monte Carlo simulation
- `src/retirement_financial_tracking/storage/`
  - ephemeral in-memory case/session storage
- `src/retirement_financial_tracking/io/`
  - workbook import/export helpers that preserve imported workbook formatting where possible

## Workbook schema

The workbook import/export layer now supports a retirement-specific case file with these sheets:

- `Household`
- `People`
- `Buckets`
- `Accounts`
- `Holdings`
- `Cash Flows`
- `Actual Balances`
- `Forecast-Sumry-*` (exported when a forecast is provided)
- `Forecast-Amts-*` (exported when a forecast is provided)
- `Forecast-Accts-*` (exported when a forecast is provided)
- `Forecast-MC-*` (exported for Monte Carlo runs)

The schema is intended to capture real retirement-planning inputs such as filing status, inflation assumptions, Social Security estimates, healthcare costs, bucket targets, custodian accounts, holdings, maturity data, and actual account balance snapshots.

## Current calculation behavior

The current forecast layer supports:

- opening balances overridden by the latest actual balance snapshot per account
- recurring explicit cash flows
- derived Social Security income from claiming-age inputs
- derived pension income from pension-start-age inputs
- derived annual healthcare expense from per-person healthcare inputs
- first-pass automatic HSA contributions with configurable limits, catch-up amount, and Medicare stop behavior
- first-pass automatic HSA withdrawals to cover modeled healthcare expenses before general bucket funding
- inflation-adjusted planned living expenses from household settings
- derived tax modeling when no explicit tax cash flow is provided:
  - `effective_rate`
  - `bracket_based`
  - `tax_projection_mode = static | inflation_adjusted` for bracket-based tables
- first-pass RMD withdrawals from tax-deferred accounts
- bucket-based shortfall funding from short-term to long-term buckets
- year-end bucket replenishment using per-bucket targets, default years-of-expense floors, and replenishment source buckets
- configurable withdrawal-priority policy within buckets:
  - tax treatment priority
  - owner priority, including age-based ordering
  - account-type priority
  - Roth last-resort handling
  - drain-one-then-next vs pro-rata allocation
- three return models:
  - `simple`
  - `scenario_based`
  - `monte_carlo`
- Monte Carlo final asset summaries and depletion probabilities by target year and/or age

The current bucket, tax, RMD, HSA, and Monte Carlo behavior is still a planning baseline. It is useful and increasingly realistic, but it is not yet a full production-grade retirement rule engine.

## Tax modeling

The forecast engine supports two tax modes through `HouseholdSettings.tax_model` and the matching Gradio UI control:

- `effective_rate`
  - keeps the original lightweight behavior
  - applies `federal_effective_tax_rate + state_effective_tax_rate` to the modeled taxable base
- `bracket_based`
  - applies bundled progressive ordinary-income tax tables
  - currently supports:
    - US federal ordinary-income brackets
    - Connecticut ordinary-income brackets

The bracket-based path also supports `HouseholdSettings.tax_projection_mode`:

- `static`
  - uses the bundled JSON thresholds, deductions, and CT exemption amounts exactly as stored
- `inflation_adjusted`
  - inflates bracket thresholds, standard deductions, and CT exemption amounts forward from each tax table's `base_year`
  - uses the household's existing `inflation_rate` setting as the indexing assumption

### Taxable base used by both modes

The current taxable base is:

- explicit modeled income
- derived pension income
- derived Social Security income
- taxable withdrawals from tax-deferred accounts, including auto-funded shortfall withdrawals
- minus modeled HSA contributions

This is intentionally still a planning approximation. It does **not** currently model:

- preferential long-term capital gains or qualified-dividend rates
- partial Social Security taxation rules
- itemized deductions
- tax credits
- AMT / NIIT / IRMAA
- Roth conversion-specific tax handling beyond normal tax-deferred withdrawal treatment
- year-by-year automatic tax law changes
- non-inflation tax policy changes unless you edit the JSON tables yourself

### JSON-backed bracket tables

The bracket-based mode loads its rules from repo-shipped JSON files:

- `src/retirement_financial_tracking/config/tax_tables_data/federal_us.json`
- `src/retirement_financial_tracking/config/tax_tables_data/state_ct.json`

These files are intended to be editable so you can update:

- table `base_year`
- bracket thresholds
- bracket rates
- federal standard deductions
- Connecticut income-based exemption amounts

The bundled files are a configurable baseline, not a live tax-law feed. If tax brackets, deductions, or exemption rules change, update the JSON files and rerun the forecast.

### State support in bracket-based mode

- Federal bracket-based tax is always available.
- State bracket-based tax is currently implemented only for `state = CT`.
- If another state is selected while `tax_model = bracket_based`, the forecast currently applies federal bracket-based tax and no additional state bracket table.

## Data ownership model

The code is structured around an internal validated model, while allowing user data to move in and out through workbooks. The workbook is the portable artifact. It is not the internal runtime model.

## UI modes

The project now has three UI entrypoints:

- `app.py`
  - the newer workspace-style UI
  - organizes the app into `Case Setup`, `Forecast`, `Report`, and `Export`
  - keeps a persistent case snapshot rail visible on the right
- `simple_spa.py`
  - the preserved single-page power-user UI
  - keeps the old "everything on one page" operator-console workflow intact
  - launches the preserved implementation in `simple_spa_app.py`
- `combined_ui.py`
  - serves both UIs from one process
  - mounts the workspace UI at `/workspace`
  - mounts the simple one-page UI at `/simple`
  - supports optional Clerk authentication in front of both mounted UIs

### Workspace UI (`app.py`)

The workspace UI currently supports:

- loading a sample case or importing a workbook
- editing the same validated plan inputs through grouped sections instead of one long page
- organizing input work into:
  - `Household`
  - `Tax & Forecast Rules`
  - `People`
  - `Accounts`
  - `Buckets`
  - `Cash Flows`
  - `Holdings`
  - `Actual Balances`
- running the forecast from a dedicated `Forecast` page
- viewing household-level forecast output in a dedicated `Household Forecast` tab
- viewing account-level forecast output in a dedicated `Account Forecast` tab
- reviewing the presentable markdown report from a dedicated `Report` page
- downloading the generated PDF report from that same `Report` page
- exporting from a dedicated `Export` page
- keeping a side snapshot rail with the current household, tax/return model, latest forecast highlights, and latest output file names
- using the same forecast/report/export engine as the simple SPA while presenting it in a friendlier workspace shell

### Simple SPA (`simple_spa.py`)

The preserved simple SPA supports:

- selecting and loading sample cases (`2-Bucket Sample`, `3-Bucket Sample`)
- importing a case workbook
- editing household settings and the main planning tables
- choosing `Tax Model = effective_rate | bracket_based`
- choosing `Tax Projection Mode = static | inflation_adjusted`
- running the forecast
- viewing both household-level and account-level forecast tables
- viewing forecast summary information including depletion timing, tax model, tax projection mode, and Monte Carlo summary lines
- opening a presentable forecast report in the app as a popup markdown view
- downloading a PDF rendition of that same forecast report from the app
- exporting a workbook using one of three modes:
  - `save_updated_copy`
  - `update_imported_workbook`
  - `new_file`
- choosing the target export folder, defaulting to the repo-local `exports/` directory
- preserving an existing `Accounts` sheet from an imported workbook instead of rewriting it
- adding forecast output as timestamped sheets such as:
  - `Forecast-Sumry-22-Oct-26-114533`
  - `Forecast-Amts-22-Oct-26-114533`
  - `Forecast-Accts-22-Oct-26-114533`
  - `Forecast-MC-22-Oct-26-114533`
  with the newest forecast sheets inserted before older forecast output sheets
  and with exported forecast amounts rounded to whole dollars and formatted in Excel

### Forecast summary sheet

When a forecast is exported, the workbook also includes a `Forecast-Sumry-*` sheet that currently stacks:

- `Forecast Headline Summary` as one summary line per row
- `Key Warnings / Observations` as one warning per row
- `Next 5 Years Preview` as a compact 5-row table with whole-number, Excel-formatted amounts
- `Recommended Actions` as a compact table of `Timing`, `Priority`, and `Action`
- `Key Assumptions` as one assumption line per row
- `Run Metadata` as one metadata line per row

The recurring recommended-action definitions are read from:

- `src/retirement_financial_tracking/config/recommended_actions_data/default_actions.json`

Forecast-triggered actions are still derived from the plan and forecast output, but they now render without hardcoded calendar years in the summary sheet.

### In-app forecast report

After a forecast run, the app now prepares a presentable report in two forms from the same underlying report model:

- a markdown report inside the UI
  - dedicated `Report` tab in `app.py`
  - popup report view in `simple_spa.py`
- a downloadable PDF report

The current report includes:

- title and run context
- executive summary
- key assumptions
- key warnings / observations
- next 5 years preview
- recommended actions
- annual cash flow and tax table
- annual account balances table
- annual balances by bucket table
- run metadata
- modeling limitations

### Workbook behavior

The `Household` sheet includes the tax-related controls that drive the forecast, including:

- `tax_model`
- `tax_projection_mode`
- `federal_effective_tax_rate`
- `state_effective_tax_rate`

Workbook import for tabular sheets is header-name-based rather than position-based, which makes edited workbooks safer to reorder by column.

When exporting from an existing workbook:

- `Accounts` is left untouched if the sheet already exists
- forecast outputs are added as new timestamped sheets:
  - `Forecast-Sumry-<DD-Mon-YY-HHMMSS>`
  - `Forecast-Amts-<DD-Mon-YY-HHMMSS>`
  - `Forecast-Accts-<DD-Mon-YY-HHMMSS>`
  - `Forecast-MC-<DD-Mon-YY-HHMMSS>` for Monte Carlo runs
- older forecast output sheets are preserved for history instead of being overwritten
- newer forecast output sheets are inserted before older forecast output sheets

Run the structured workspace UI with:

```bash
.venv/bin/python app.py
```

Run the simple SPA with:

```bash
.venv/bin/python simple_spa.py
```

Run both UIs from one server with:

```bash
.venv/bin/python combined_ui.py
```

Then open either:

- `http://127.0.0.1:7860/workspace`
- `http://127.0.0.1:7860/simple`

### Optional Clerk authentication for `combined_ui.py`

The combined launcher can protect both `/workspace` and `/simple` with Clerk.

Set these environment variables before running `combined_ui.py`:

- `CLERK_ENABLED=1`
- `CLERK_PUBLISHABLE_KEY=<your Clerk publishable key>`
- `CLERK_JWKS_URL=<your Clerk JWKS URL>`

Optional:

- `CLERK_JWT_ISSUER=<expected issuer>` if you want issuer validation
- `CLERK_JWT_AUDIENCE=<expected audience>` if you want audience validation
- `CLERK_AFTER_SIGN_IN_URL=/workspace/`
- `CLERK_SESSION_COOKIE=__session`

When enabled:

- unauthenticated requests to `/`, `/workspace`, and `/simple` redirect to `/sign-in`
- `/sign-in` renders a Clerk sign-in page and then returns users to `/workspace/` by default

Notes:

- the standalone launchers `app.py` and `simple_spa.py` remain direct local-dev entrypoints and are not wrapped by Clerk
- `combined_ui.py` is the launcher to use when you want browser auth in front of both UIs

## Tests

The test suite covers:

- forecast math and yearly balance roll-forward
- workbook export/import round-trips
- tax modeling for effective-rate, static bracket-based, and inflation-adjusted bracket-based modes
- Monte Carlo seeded behavior and depletion summaries
- HSA contribution and healthcare withdrawal behavior
- withdrawal-priority policy behavior
- bucket replenishment behavior
- export path and workbook-format preservation behavior

Run tests with:

```bash
.venv/bin/python -m pytest
```
