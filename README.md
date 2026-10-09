# Retirement Financial Tracking

This repository is the first technical foundation for a retirement planning and tracking system with:

- a configurable product/display name
- typed domain models for household data
- a deterministic yearly forecast engine
- an in-memory session store
- workbook import/export scaffolding for user-owned data files

## Initial module layout

- `src/retirement_financial_tracking/config/`
  - app metadata and configurable display name
- `src/retirement_financial_tracking/domain/`
  - typed domain models for people, accounts, recurring cash flows, and forecast output
- `src/retirement_financial_tracking/services/`
  - deterministic yearly forecast logic
- `src/retirement_financial_tracking/storage/`
  - ephemeral in-memory case/session storage
- `src/retirement_financial_tracking/io/`
  - workbook import/export helpers

## Data ownership model

The code is structured around an internal validated model, while allowing user data to move in and out through workbooks. The workbook is the portable artifact. It is not the internal runtime model.

## Running tests

```bash
python -m pytest
```

