# NORA — Pharma Revenue Comparison

NORA opens with company revenue comparison. Search 18 supported pharmaceutical
issuers by Korean/English name, ticker, or CIK; select up to six; compare annual
reported revenue and year-over-year growth; inspect fiscal periods and sources;
download a CSV. English and Korean are supported. The existing ToxiGuard product
revenue scenario workspace remains available through the sidebar.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run streamlit_app.py
```

The Streamlit Cloud entrypoint remains `streamlit_app.py` in the repository root.
Deploy all files together, including `nora_data.py`, `nora_ui.py`, `data/`, and
`.streamlit/config.toml`. Uploading only `app.py` is insufficient.

## What the initial screen contains

The bundled dataset contains **2023–2025** annual consolidated revenue for
**Eli Lilly, Pfizer, and Merck & Co. (US/MSD)**. These are official report
snapshots checked on **2026-09-28**, not a live feed. See
[source tables and provenance](data/SOURCES.md). Original reported precision is
preserved: whole USD millions are converted to USD units without implying
greater accuracy. Source pages, report identifiers, fiscal dates and notes are
included with the rows.

The wider registry supports SEC refresh for 18 issuers. Search availability does
not guarantee that an annual revenue tag is available for that company. Domestic
Korean companies/DART, currency conversion, quarterly/TTM comparison, and product
or indication revenue comparison are not connected in this company workspace.

## SEC refresh

`SEC_USER_AGENT` may be configured as an environment variable or a Streamlit
secret with the operator's real organization and contact email:

```toml
SEC_USER_AGENT = "Organization contact@example.org"
```

Replace the example with a real operator contact; do not commit secrets. Without
configuration, the client truthfully identifies NORA and this repository URL.
SEC may deny a deployment's network/IP even when the header is configured.
During this release validation, live Company Facts requests returned HTTP 403.
The app explicitly reports failure and retains the original source/date of any
previously loaded data. It never presents a saved snapshot as a successful live
refresh. Successful results are cached for one hour with their original retrieval
timestamp; companies are loaded sequentially.

## Comparison rules

- Annual duration facts only (330–400 days); quarter/YTD facts are excluded.
- Only an explicit allowlist of standard consolidated revenue concepts is used.
- Actual period start/end determines the observation, not the filing's `fy`
  context. Comparative columns and restatements retain their provenance.
- Takeda's April–March fiscal year is labelled by its starting year. Other
  issuer years use filing metadata or explicitly marked period-derived years.
- Reported currencies are kept separate. The app never ranks across currencies.
- Growth requires adjacent comparable annual periods, positive prior revenue,
  and a consistent currency/concept. Prior-year values from the same filing are
  preferred; incompatible restatements leave growth blank.
- Company revenue may include non-pharmaceutical divisions and collaboration
  income. Fiscal dates and corporate scope must be checked when interpreting
  comparisons. Growth is nominal, not currency/acquisition adjusted.

## Product revenue scenarios

The original scenario calculations are retained. Switching workspaces or
languages preserves input state. Loading a scenario explicitly resets its
evidence, currency and pipeline inputs. Company-total revenue remains blocked
from use as a product/indication market anchor. Live lookup never silently falls
back to unverified built-in reference data; reference lookups require a matching
fiscal year.

## Validation

```bash
python3 -m unittest discover -v
```

Tests cover annual-vs-quarterly facts, comparative years, restatements, foreign
currencies, fiscal labels, Korean aliases, growth gaps, source preservation,
failed refresh, language/workspace state, and the existing forecast model.
Fixtures and mocked UI refresh tests do not imply successful live SEC access.

## Telmisartan case study (local integration)

Open `?case=telmisartan` or select **Telmisartan 사례 연구**. The case compares
three hypothetical Korean development strategies: monotherapy generic,
telmisartan/amlodipine, and telmisartan/amlodipine/indapamide. Source records,
reported Yuhan Twynsta sales, and editable commercial assumptions are separated.
The reference product's clinical/approval status is not the hypothetical
project's development stage or probability of success.

Revenue is a patient-based scenario, not a market inferred from company sales.
All commercial defaults are teaching assumptions. Result money is displayed in
KRW 100 million; raw CSV fields ending `_krw_m` are KRW million. Peak within the
2027–2034 horizon and revenue at target share/base-year patients are distinct.
Net contribution subtracts success-weighted post-launch fixed costs and the
full development budget; it is not profit, NPV or valuation.

`telmisartan_case.py` and `data/telmisartan_case.json` are shared byte-for-byte
with VCC. The JSON handoff preserves edited assumptions; VCC validates scope
and recalculates numbers. Its link opens case defaults, not the edited values.
Set `VCC_APP_URL` to the paired local preview when testing. Defaults point to
the existing public app, which needs the matching VCC update before this case
can be opened there. Source snapshot reviewed 2026-09-28–29. No public deployment
was performed as part of creating this case.

The case assumption tab can restore a saved NORA or VCC JSON after validation.
Only the selected strategy is replaced; other case assumptions and existing
company/forecast inputs remain unchanged. Product revenue context now includes
Yuhan Twynsta domestic sales and CKD Telminuvo reported product sales for
2023–2025. CKD does not split domestic/export sales in this product row; keep
that scope difference visible and do not infer comparable market shares.
