# ToxiGuard Revenue Forecast Streamlit

Streamlit migration of the Revenue Forecast Intelligence workspace.

This version keeps the original web app logic but reorganizes it as a Streamlit evidence dashboard with forecast, calculation basis, pipeline risk, insight report, validation, and export tabs.

## Positioning

This module is the Business Evidence appendix for ToxiGuard-Platform. It does not replace CMC RA, regulatory, clinical, financial, or investment judgment. It helps a reviewer separate:

- official revenue anchor
- market-share assumptions
- patient-based cross-check
- payer access and competition assumptions
- pipeline probability / label / economics risk adjustment
- evidence traceability and open review items

## Run Locally

```bash
cd /Users/leeyoung-nam/Desktop/ToxiGuard
python3 -m streamlit run ToxiGuard-Revenue-Forecast/app.py --server.port 8511
```

Then open:

```text
http://localhost:8511
```

Streamlit Cloud entrypoint when deployed as the standalone `ToxiGuard-RF` repository:

```text
streamlit_app.py
```

## Core Outputs

- Peak sales and Year 5 forecast
- Market model vs patient model triangulation
- Pipeline risk-adjusted revenue bridge
- Visual evidence dashboard: sales anchor -> TAM -> market model -> patient model -> risk-adjusted peak
- Calculation basis table with year-by-year formulas
- Insight report connecting company revenue, clinical program, future target market, and risk-adjusted contribution
- Evidence validation checklist
- Markdown evidence memo
- HTML report
- Forecast CSV

## Evidence Policy

Use SEC EDGAR, SEC XBRL Company Facts, DART, and official company annual reports as primary revenue evidence. Use CMS/HIRA or other public payer/utilization data as cross-checks, not direct substitutes for company-reported net sales.

Built-in official anchors are demo/reference anchors copied from the existing local Revenue Forecast workspace. Before external use, confirm the source table, unit, fiscal year, accession/report ID, footnotes, product scope, collaboration/royalty treatment, and whether the number is company-level, product-level, or indication-level.
