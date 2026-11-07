## About

Retirement Financial Tracking and Action System is a retirement-planning workspace for:

- modeling household retirement inputs and account structure
- running yearly retirement forecasts
- reviewing warnings, assumptions, and recommended actions
- generating a presentable report and an updated Excel workbook for your own records
- does not store your data or any information on the server(s)
- exporting input data, updated data, and forecasts as an Excel workbook

## What This App Does

- Imports a workbook or loads a sample case
- Lets you edit household, tax, people, account, bucket, cash-flow, holding, and balance inputs
- Runs deterministic or Monte Carlo forecast scenarios
- Supports `effective_rate` and `bracket_based` tax modeling
- Produces:
  - forecast tables
  - a report in the UI
  - a downloadable PDF report
  - a downloadable Excel workbook with forecast sheets

## Recommended Flow

1. Start in `Case Setup`
2. Load a sample case or import your workbook
3. Review and edit inputs
4. Go to `Forecast` and run the forecast
5. Review the results and summary
6. Open `Report` to read or download the report PDF
7. Go to `Export` to download the updated workbook
8. Make offline updates to the numbers in the exported Excel file
9. Load the previously exported or updated workbook to perform another forecast

## Important Notes

- The app does not permanently store your case data on the server
- Workbook exports and report PDFs are generated as transient downloads
- The workbook remains the portable artifact you keep
- This is a planning tool, not tax, legal, or investment advice

## Forecast Highlights

Current forecast behavior includes:

- actual-balance overrides
- Social Security and pension modeling
- healthcare and HSA handling
- RMD handling
- bucket replenishment
- withdrawal-priority policies
- simple, scenario-based, and Monte Carlo return models

## Tax Modeling

- `effective_rate`: simple federal + state effective-rate planning
- `bracket_based`: progressive bracket modeling
- current bracket-based state support is focused on `CT`
- bracket-based forecasts can run in `static` or `inflation_adjusted` mode
