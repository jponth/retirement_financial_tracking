# Retirement Financial Tracking

This repository contains a working retirement planning and tracking prototype with:

- a configurable product/display name
- typed domain models for retirement household data
- a local yearly forecast and calculation engine
- a Gradio-based planning UI
- workbook import/export for user-owned case files

## Module layout

- `src/retirement_financial_tracking/config/`
  - app metadata and configurable display name
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
- `Forecast` (exported when a forecast is provided)
- `Account Forecast` (exported when a forecast is provided)
- `Monte Carlo Summary` (exported for Monte Carlo runs)

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
- effective-tax estimation when no explicit tax cash flow is provided
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

## Data ownership model

The code is structured around an internal validated model, while allowing user data to move in and out through workbooks. The workbook is the portable artifact. It is not the internal runtime model.

## Starter UI

A starter Gradio app is available in `app.py`. It supports:

- selecting and loading sample cases (`2-Bucket Sample`, `3-Bucket Sample`)
- importing a case workbook
- editing household settings and the main planning tables
- running the forecast
- viewing both household-level and account-level forecast tables
- viewing forecast summary information including depletion timing and Monte Carlo summary lines
- exporting a workbook using one of three modes:
  - `save_updated_copy`
  - `update_imported_workbook`
  - `new_file`
- choosing the target export folder, defaulting to the repo-local `exports/` directory

Run it with:

```bash
.venv/bin/python app.py
```

## Tests

The test suite covers:

- forecast math and yearly balance roll-forward
- workbook export/import round-trips
- Monte Carlo seeded behavior and depletion summaries
- HSA contribution and healthcare withdrawal behavior
- withdrawal-priority policy behavior
- bucket replenishment behavior
- export path and workbook-format preservation behavior

Run tests with:

```bash
.venv/bin/python -m pytest
```
