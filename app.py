from __future__ import annotations

import io
import html
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st


APP_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = APP_DIR.parent
for import_path in (APP_DIR, WORKSPACE_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

try:
    from revenue_filing_tool import run_lookup
except Exception:  # pragma: no cover - app still works with built-in anchors
    run_lookup = None


st.set_page_config(
    page_title="ToxiGuard Revenue Forecast",
    page_icon="TG",
    layout="wide",
    initial_sidebar_state="expanded",
)


SCENARIOS: dict[str, dict[str, Any]] = {
    "Custom project": {
        "company": "Example Pharma",
        "product": "TG-001",
        "indication": "Target indication",
        "reported_sales": 1200.0,
        "anchor_year": 2025,
        "current_share": 18.0,
        "market_cagr": 7.5,
        "initial_share": 0.8,
        "peak_share": 16.0,
        "uptake_speed": 0.55,
        "payer_access": 78.0,
        "competition_drag": 4.0,
        "patients": 420000,
        "patient_growth": 2.5,
        "diagnosis_rate": 72.0,
        "treatment_rate": 64.0,
        "eligible_rate": 42.0,
        "annual_price": 28500.0,
        "adherence": 76.0,
        "market_weight": 60.0,
    },
    "Immunology follow-on entrant": {
        "company": "Example Pharma",
        "product": "TG-Inflam",
        "indication": "Moderate-to-severe immune disease",
        "reported_sales": 2600.0,
        "anchor_year": 2025,
        "current_share": 22.0,
        "market_cagr": 6.2,
        "initial_share": 1.2,
        "peak_share": 13.0,
        "uptake_speed": 0.48,
        "payer_access": 72.0,
        "competition_drag": 6.0,
        "patients": 680000,
        "patient_growth": 1.8,
        "diagnosis_rate": 78.0,
        "treatment_rate": 58.0,
        "eligible_rate": 36.0,
        "annual_price": 34000.0,
        "adherence": 72.0,
        "market_weight": 65.0,
    },
    "Oncology label-expansion asset": {
        "company": "Example Pharma",
        "product": "TG-Onco",
        "indication": "Second-line solid tumor segment",
        "reported_sales": 4100.0,
        "anchor_year": 2025,
        "current_share": 28.0,
        "market_cagr": 9.8,
        "initial_share": 0.7,
        "peak_share": 18.0,
        "uptake_speed": 0.68,
        "payer_access": 86.0,
        "competition_drag": 5.0,
        "patients": 124000,
        "patient_growth": 3.1,
        "diagnosis_rate": 82.0,
        "treatment_rate": 70.0,
        "eligible_rate": 44.0,
        "annual_price": 112000.0,
        "adherence": 62.0,
        "market_weight": 55.0,
    },
    "Rare disease premium therapy": {
        "company": "Example Pharma",
        "product": "TG-Rare",
        "indication": "Genetically defined rare disease",
        "reported_sales": 420.0,
        "anchor_year": 2025,
        "current_share": 12.0,
        "market_cagr": 11.5,
        "initial_share": 2.2,
        "peak_share": 24.0,
        "uptake_speed": 0.82,
        "payer_access": 69.0,
        "competition_drag": 2.0,
        "patients": 18500,
        "patient_growth": 2.1,
        "diagnosis_rate": 54.0,
        "treatment_rate": 48.0,
        "eligible_rate": 62.0,
        "annual_price": 285000.0,
        "adherence": 81.0,
        "market_weight": 45.0,
    },
    "Metabolic chronic-use asset": {
        "company": "Example Pharma",
        "product": "TG-Metabo",
        "indication": "Large chronic metabolic disease",
        "reported_sales": 5200.0,
        "anchor_year": 2025,
        "current_share": 31.0,
        "market_cagr": 13.5,
        "initial_share": 1.6,
        "peak_share": 21.0,
        "uptake_speed": 0.72,
        "payer_access": 64.0,
        "competition_drag": 7.0,
        "patients": 7200000,
        "patient_growth": 3.4,
        "diagnosis_rate": 62.0,
        "treatment_rate": 44.0,
        "eligible_rate": 18.0,
        "annual_price": 9800.0,
        "adherence": 68.0,
        "market_weight": 70.0,
    },
}


VERIFIED_REVENUE_ANCHORS: dict[str, dict[str, Any]] = {
    "MRK": {
        "ticker": "MRK",
        "name": "Merck & Co., Inc.",
        "value_millions": 65011.0,
        "fiscal_year": 2025,
        "filed": "2026-02-03",
        "concept": "Total Sales",
        "unit": "USD millions",
        "source_type": "Company Annual Report",
        "source_url": "https://www.merck.com/news/merck-highlights-progress-advancing-broad-diverse-pipeline/",
        "accession": "official-fy2025-results",
        "note": "Built-in official anchor from the existing Revenue Forecast workspace. Confirm the original filing or annual report table before external use.",
    },
    "LLY": {
        "ticker": "LLY",
        "name": "Eli Lilly and Company",
        "value_millions": 65179.0,
        "fiscal_year": 2025,
        "filed": "2026-02-12",
        "concept": "Revenue",
        "unit": "USD millions",
        "source_type": "Company Annual Report",
        "source_url": "https://www.lilly.com/about/key-facts",
        "accession": "official-fy2025-key-facts",
        "note": "Company-level revenue is not product-level or indication-level market size.",
    },
    "PFE": {
        "ticker": "PFE",
        "name": "Pfizer Inc.",
        "value_millions": 62579.0,
        "fiscal_year": 2025,
        "filed": "2026",
        "concept": "Revenues",
        "unit": "USD millions",
        "source_type": "Company Annual Report",
        "source_url": "https://annualreview.pfizer.com/",
        "accession": "official-fy2025-annual-review",
        "note": "Use the official annual review or SEC filing table for final footnote review.",
    },
    "JNJ": {
        "ticker": "JNJ",
        "name": "Johnson & Johnson",
        "value_millions": 94200.0,
        "fiscal_year": 2025,
        "filed": "2026-01-21",
        "concept": "Full-Year reported sales",
        "unit": "USD millions",
        "source_type": "Company Annual Report",
        "source_url": "https://www.investor.jnj.com/investor-news/news-details/2026/Johnson--Johnson-reports-Q4-and-Full-Year-2025-results/default.aspx",
        "accession": "official-fy2025-results",
        "note": "Confirm segment/product split before using as an indication market anchor.",
    },
    "ABBV": {
        "ticker": "ABBV",
        "name": "AbbVie Inc.",
        "value_millions": 61200.0,
        "fiscal_year": 2025,
        "filed": "2026-02-20",
        "concept": "Worldwide net revenues",
        "unit": "USD millions",
        "source_type": "SEC EDGAR 10-K / 20-F",
        "source_url": "https://www.sec.gov/Archives/edgar/data/1551152/000155115226000008/abbv-20251231.htm",
        "accession": "0001551152-26-000008",
        "note": "Entered at one-decimal-billion precision from the existing workspace anchor.",
    },
    "GSK": {
        "ticker": "GSK",
        "name": "GSK plc",
        "value_millions": 32667.0,
        "fiscal_year": 2025,
        "filed": "2026-02-04",
        "concept": "Group turnover",
        "unit": "GBP millions",
        "source_type": "Company Annual Report",
        "source_url": "https://www.gsk.com/en-gb/investors/financial-reports/annual-report-2025/",
        "accession": "official-fy2025-annual-report",
        "note": "Values are GBP. Keep model inputs in one currency unless an explicit FX conversion is documented.",
    },
}


COMPANY_ALIASES = {
    "ABBVIE": "ABBV",
    "BMS": "BMY",
    "BRISTOL MYERS SQUIBB": "BMY",
    "BRISTOL-MYERS SQUIBB": "BMY",
    "ELI LILLY": "LLY",
    "LILLY": "LLY",
    "MERCK": "MRK",
    "MERCK & CO": "MRK",
    "PFIZER": "PFE",
    "JOHNSON & JOHNSON": "JNJ",
    "JOHNSON JOHNSON": "JNJ",
    "GLAXOSMITHKLINE": "GSK",
    "GSK PLC": "GSK",
}


PHASE_POS = {
    "Preclinical": 3.0,
    "Phase 1": 7.9,
    "Phase 2": 15.0,
    "Phase 3": 50.0,
    "Filing / Review": 90.0,
    "Approved": 100.0,
}


@dataclass
class ForecastInput:
    company: str
    product: str
    indication: str
    reported_sales: float
    anchor_year: int
    current_share: float
    market_cagr: float
    initial_share: float
    peak_share: float
    uptake_speed: float
    payer_access: float
    competition_drag: float
    patients: float
    patient_growth: float
    diagnosis_rate: float
    treatment_rate: float
    eligible_rate: float
    annual_price: float
    adherence: float
    market_weight: float
    source_type: str
    evidence_url: str
    filing_date: str
    accession: str
    reviewer_note: str
    currency_label: str


@dataclass
class PipelineInput:
    asset: str
    indication: str
    phase: str
    launch_year: int
    probability: float
    label_factor: float
    economics: float
    nct: str
    source_type: str
    evidence_url: str
    note: str


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fmt_money(value: float, currency: str = "USD") -> str:
    if not math.isfinite(value):
        return "-"
    prefix = "$" if currency.upper() == "USD" else f"{currency} "
    return f"{prefix}{value:,.0f}M"


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def normalise_company_query(query: str) -> str:
    return " ".join("".join(ch if ch.isalnum() or ch in {"&", " "} else " " for ch in query.upper()).split())


def resolve_builtin_anchor(query: str) -> dict[str, Any] | None:
    cleaned = normalise_company_query(query)
    ticker = COMPANY_ALIASES.get(cleaned, cleaned)
    return VERIFIED_REVENUE_ANCHORS.get(ticker)


@st.cache_data(show_spinner=False, ttl=60 * 60)
def sec_lookup_cached(query: str, year: int | None, product: str | None) -> dict[str, Any]:
    if run_lookup is None:
        raise RuntimeError("revenue_filing_tool.run_lookup is not available.")
    return run_lookup(query=query, year=year, product=product or None, max_tables=3)


def calculate_forecast(input_data: ForecastInput) -> pd.DataFrame:
    current_share = clamp(input_data.current_share / 100, 0.001, 1)
    market_cagr = input_data.market_cagr / 100
    initial_share = clamp(input_data.initial_share / 100, 0, 1)
    peak_share = clamp(input_data.peak_share / 100, 0, 1)
    uptake_speed = clamp(input_data.uptake_speed, 0.05, 2)
    payer_access = clamp(input_data.payer_access / 100, 0, 1)
    competition_drag = clamp(input_data.competition_drag / 100, 0, 1)
    patient_growth = input_data.patient_growth / 100
    diagnosis_rate = clamp(input_data.diagnosis_rate / 100, 0, 1)
    treatment_rate = clamp(input_data.treatment_rate / 100, 0, 1)
    eligible_rate = clamp(input_data.eligible_rate / 100, 0, 1)
    adherence = clamp(input_data.adherence / 100, 0, 1)
    market_weight = clamp(input_data.market_weight / 100, 0, 1)

    base_tam = input_data.reported_sales / current_share
    rows: list[dict[str, float | int]] = []
    for index in range(8):
        forecast_year = index + 1
        year = input_data.anchor_year + forecast_year
        market_tam = base_tam * (1 + market_cagr) ** forecast_year
        ramp = 1 - math.exp(-uptake_speed * forecast_year)
        target_share = initial_share + (peak_share - initial_share) * ramp
        erosion = max(0, 1 - competition_drag * index)
        adjusted_share = clamp(target_share * erosion, 0, 1)
        market_model = market_tam * adjusted_share * payer_access

        patient_pool = input_data.patients * (1 + patient_growth) ** forecast_year
        addressable_patients = patient_pool * diagnosis_rate * treatment_rate * eligible_rate
        treated_patients = addressable_patients * adjusted_share * adherence
        patient_model = treated_patients * input_data.annual_price / 1_000_000
        triangulated = market_model * market_weight + patient_model * (1 - market_weight)

        rows.append(
            {
                "Year": year,
                "Forecast Year": forecast_year,
                "Base TAM": base_tam,
                "Market TAM": market_tam,
                "Adjusted Share": adjusted_share,
                "Market Model": market_model,
                "Patient Pool": patient_pool,
                "Addressable Patients": addressable_patients,
                "Treated Patients": treated_patients,
                "Patient Model": patient_model,
                "Triangulated Forecast": triangulated,
            }
        )
    return pd.DataFrame(rows)


def calculate_pipeline(input_data: ForecastInput, pipeline: PipelineInput, forecast: pd.DataFrame) -> pd.DataFrame:
    risk_factor = (
        clamp(pipeline.probability / 100, 0, 1)
        * clamp(pipeline.label_factor / 100, 0, 1)
        * clamp(pipeline.economics / 100, 0, 1)
    )
    rows = []
    for _, row in forecast.iterrows():
        commercial_year = int(row["Year"]) - pipeline.launch_year + 1
        unadjusted = float(row["Triangulated Forecast"]) if commercial_year >= 1 else 0.0
        rows.append(
            {
                "Year": int(row["Year"]),
                "Commercial Year": max(0, commercial_year),
                "Unadjusted Revenue": unadjusted,
                "Risk Factor": risk_factor,
                "Risk-Adjusted Revenue": unadjusted * risk_factor,
            }
        )
    return pd.DataFrame(rows)


def calculate_confidence(input_data: ForecastInput, lookup_matched: bool) -> tuple[int, str]:
    score = 0
    notes: list[str] = []
    source = input_data.source_type.lower()
    if "sec" in source or "annual" in source or "dart" in source:
        score += 35
        notes.append("Tier A source")
    elif "cms" in source or "hira" in source:
        score += 24
        notes.append("Tier B cross-check")
    else:
        score += 12
        notes.append("Manual source")
    if input_data.evidence_url.startswith("http"):
        score += 18
    if input_data.accession and input_data.accession != "manual-review-needed":
        score += 12
    if input_data.reported_sales > 0 and input_data.current_share > 0:
        score += 15
    if input_data.patients > 0 and input_data.annual_price > 0:
        score += 10
    if len(input_data.reviewer_note.strip()) > 40:
        score += 10
    if lookup_matched:
        score += 8
    return min(score, 100), ", ".join(notes)


def validation_checks(
    input_data: ForecastInput,
    pipeline: PipelineInput,
    forecast: pd.DataFrame,
    pipeline_forecast: pd.DataFrame,
    confidence: int,
) -> pd.DataFrame:
    current_share = clamp(input_data.current_share / 100, 0.001, 1)
    base_tam = input_data.reported_sales / current_share
    risk_factor = (
        clamp(pipeline.probability / 100, 0, 1)
        * clamp(pipeline.label_factor / 100, 0, 1)
        * clamp(pipeline.economics / 100, 0, 1)
    )

    checks = [
        (
            "Evidence",
            "Primary revenue source",
            "Pass" if any(x in input_data.source_type for x in ["SEC", "Annual", "DART"]) else "Review",
            input_data.source_type,
            "Use SEC 10-K/20-F, annual report, or DART as the final primary source.",
        ),
        (
            "Evidence",
            "Evidence URL",
            "Pass" if input_data.evidence_url.startswith("http") else "Fix",
            input_data.evidence_url or "missing",
            "Keep the source URL in the final memo.",
        ),
        (
            "Evidence",
            "Accession / report ID",
            "Pass" if input_data.accession and input_data.accession != "manual-review-needed" else "Review",
            input_data.accession or "missing",
            "Add SEC accession, annual report ID, or official report reference.",
        ),
        (
            "Calculation",
            "Base TAM",
            "Pass" if math.isfinite(base_tam) and base_tam > 0 else "Fix",
            f"{fmt_money(input_data.reported_sales, input_data.currency_label)} / {input_data.current_share:.1f}% = {fmt_money(base_tam, input_data.currency_label)}",
            "Confirm that company-level sales are appropriate for this product/indication market.",
        ),
        (
            "Calculation",
            "Year sequence",
            "Pass" if forecast["Year"].is_monotonic_increasing else "Fix",
            f"FY {forecast['Year'].min()}-{forecast['Year'].max()}",
            "Forecast years should be continuous.",
        ),
        (
            "Calculation",
            "Patient model",
            "Pass" if input_data.patients > 0 and input_data.annual_price > 0 else "Fix",
            f"{input_data.patients:,.0f} patients x net annual price {input_data.annual_price:,.0f}",
            "Confirm epidemiology, treated population, eligibility, and price.",
        ),
        (
            "Pipeline",
            "Risk factor",
            "Pass" if risk_factor > 0 else "Fix",
            f"{pipeline.probability:.1f}% x {pipeline.label_factor:.1f}% x {pipeline.economics:.1f}% = {fmt_pct(risk_factor)}",
            "PoS, label factor, and economics should have traceable assumptions.",
        ),
        (
            "Pipeline",
            "Launch window",
            "Pass" if pipeline.launch_year in set(forecast["Year"].astype(int)) else "Review",
            f"Launch FY {pipeline.launch_year}",
            "If launch is outside the model horizon, extend forecast or revise timing.",
        ),
        (
            "Overall",
            "Evidence confidence",
            "Pass" if confidence >= 85 else "Review" if confidence >= 70 else "Fix",
            f"{confidence}%",
            "Strengthen source ID, URL, memo, and official lookup before external use.",
        ),
    ]
    return pd.DataFrame(checks, columns=["Group", "Check", "Status", "Basis", "Next action"])


def markdown_memo(
    input_data: ForecastInput,
    pipeline: PipelineInput,
    forecast: pd.DataFrame,
    pipeline_forecast: pd.DataFrame,
    confidence: int,
    checks: pd.DataFrame,
) -> str:
    peak = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    year5 = forecast.iloc[min(4, len(forecast) - 1)]
    base_tam = forecast.iloc[0]["Base TAM"]
    pipeline_peak = pipeline_forecast.loc[pipeline_forecast["Risk-Adjusted Revenue"].idxmax()]
    open_items = checks[checks["Status"] != "Pass"]

    lines = [
        "# Revenue Forecast Evidence Memo",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Company: {input_data.company}",
        f"Product / asset: {input_data.product}",
        f"Indication market: {input_data.indication}",
        "",
        "## Official Sales Anchor",
        "",
        f"- Source type: {input_data.source_type}",
        f"- Source URL: {input_data.evidence_url or 'review needed'}",
        f"- Filing / report date: {input_data.filing_date or 'review needed'}",
        f"- Accession / report ID: {input_data.accession or 'review needed'}",
        f"- Reported sales anchor: {fmt_money(input_data.reported_sales, input_data.currency_label)}",
        f"- Current share assumption: {input_data.current_share:.1f}%",
        f"- Implied base TAM: {fmt_money(base_tam, input_data.currency_label)}",
        f"- Evidence confidence: {confidence}%",
        "",
        "## Forecast Result",
        "",
        f"- Year 5 forecast: {fmt_money(float(year5['Triangulated Forecast']), input_data.currency_label)} in FY {int(year5['Year'])}",
        f"- Peak sales: {fmt_money(float(peak['Triangulated Forecast']), input_data.currency_label)} in FY {int(peak['Year'])}",
        f"- Market CAGR: {input_data.market_cagr:.1f}%",
        f"- Peak share assumption: {input_data.peak_share:.1f}%",
        f"- Payer access: {input_data.payer_access:.1f}%",
        f"- Competition drag: {input_data.competition_drag:.1f}% per year",
        "",
        "## Patient-Based Cross-Check",
        "",
        f"- Patients: {input_data.patients:,.0f}",
        f"- Diagnosis / treatment / eligible: {input_data.diagnosis_rate:.1f}% / {input_data.treatment_rate:.1f}% / {input_data.eligible_rate:.1f}%",
        f"- Net annual price: {input_data.annual_price:,.0f}",
        f"- Adherence / persistence: {input_data.adherence:.1f}%",
        f"- Peak patient model: {fmt_money(float(forecast['Patient Model'].max()), input_data.currency_label)}",
        "",
        "## Pipeline Risk Adjustment",
        "",
        f"- Asset: {pipeline.asset}",
        f"- Phase: {pipeline.phase}",
        f"- Expected launch year: FY {pipeline.launch_year}",
        f"- Risk factor: {pipeline.probability:.1f}% x {pipeline.label_factor:.1f}% x {pipeline.economics:.1f}%",
        f"- Risk-adjusted peak: {fmt_money(float(pipeline_peak['Risk-Adjusted Revenue']), input_data.currency_label)} in FY {int(pipeline_peak['Year'])}",
        f"- Clinical evidence: {pipeline.source_type}; {pipeline.evidence_url}",
        "",
        "## Open Review Items",
        "",
    ]
    if open_items.empty:
        lines.append("- No major open item from the current automated checks. Confirm source table units and footnotes before external use.")
    else:
        for _, row in open_items.iterrows():
            lines.append(f"- {row['Check']}: {row['Status']} - {row['Next action']}")
    lines.extend(
        [
            "",
            "## Reviewer Note",
            "",
            input_data.reviewer_note.strip() or "Review official source table, unit, footnotes, product/indication scope, and sensitivity assumptions before final use.",
        ]
    )
    return "\n".join(lines)


def build_csv_bytes(forecast: pd.DataFrame, pipeline_forecast: pd.DataFrame) -> bytes:
    merged = forecast.merge(pipeline_forecast, on="Year", how="left")
    return merged.to_csv(index=False).encode("utf-8-sig")


def apply_anchor_to_session(anchor: dict[str, Any]) -> None:
    st.session_state["company"] = anchor["name"]
    st.session_state["reported_sales"] = float(anchor["value_millions"])
    st.session_state["anchor_year"] = int(anchor["fiscal_year"])
    st.session_state["source_type"] = anchor["source_type"]
    st.session_state["evidence_url"] = anchor["source_url"]
    st.session_state["filing_date"] = anchor["filed"]
    st.session_state["accession"] = anchor["accession"]
    if anchor.get("unit", "").upper().startswith("GBP"):
        st.session_state["currency_label"] = "GBP"
    else:
        st.session_state["currency_label"] = "USD"


def ensure_session_defaults(defaults: dict[str, Any]) -> None:
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault("currency_label", "USD")
    st.session_state.setdefault("source_type", "Manual review needed")
    st.session_state.setdefault("evidence_url", "")
    st.session_state.setdefault("filing_date", "")
    st.session_state.setdefault("accession", "manual-review-needed")
    st.session_state.setdefault(
        "reviewer_note",
        "Company-level revenue must be separated from product-level or indication-level market assumptions before external use.",
    )
    st.session_state.setdefault("pipeline_asset", st.session_state.get("product", defaults["product"]))
    st.session_state.setdefault("pipeline_indication", st.session_state.get("indication", defaults["indication"]))
    st.session_state.setdefault("pipeline_phase", "Phase 2")
    st.session_state.setdefault("pipeline_launch_year", int(st.session_state.get("anchor_year", defaults["anchor_year"])) + 3)
    st.session_state.setdefault("pipeline_probability", PHASE_POS["Phase 2"])
    st.session_state.setdefault("pipeline_label_factor", 65.0)
    st.session_state.setdefault("pipeline_economics", 100.0)
    st.session_state.setdefault("pipeline_nct", "NCT review needed")
    st.session_state.setdefault("pipeline_source_type", "ClinicalTrials.gov / company IR")
    st.session_state.setdefault("pipeline_evidence_url", "https://clinicaltrials.gov/")
    st.session_state.setdefault("pipeline_note", "")


def render_header() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #f5f8fa; }
        section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #d9e3df; }
        .tg-hero {
          border: 1px solid #d9e3df;
          border-radius: 8px;
          padding: 24px 26px;
          background: linear-gradient(135deg, #ffffff 0%, #eef7f6 58%, #edf4fa 100%);
          box-shadow: 0 14px 34px rgba(31, 45, 41, 0.06);
          margin-bottom: 18px;
        }
        .tg-hero small {
          display: block; color: #0f766e; font-weight: 800; letter-spacing: .04em;
          text-transform: uppercase; margin-bottom: 6px;
        }
        .tg-hero h1 { color: #102f43; margin: 0 0 6px; font-size: 2.25rem; }
        .tg-hero p { color: #536776; margin: 0; max-width: 920px; }
        .block-note {
          border-left: 4px solid #0f766e; background: #ffffff; padding: 12px 14px;
          border-radius: 6px; color: #354852; margin: 10px 0 16px;
        }
        </style>
        <div class="tg-hero">
          <small>Business Evidence Module</small>
          <h1>ToxiGuard Revenue Forecast Intelligence</h1>
          <p>공식 매출 anchor를 기준으로 시장 점유율, 환자 수, 순가격, payer access, 경쟁 강도, 임상 risk를 연결해 partner-ready revenue evidence memo를 만듭니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_inputs() -> tuple[ForecastInput, PipelineInput, bool]:
    scenario = st.sidebar.selectbox("Scenario template", list(SCENARIOS.keys()))
    defaults = SCENARIOS[scenario]
    pending_anchor = st.session_state.pop("pending_anchor", None)
    if pending_anchor:
        apply_anchor_to_session(pending_anchor)
    ensure_session_defaults(defaults)
    if st.sidebar.button("시나리오 값 불러오기", width="stretch"):
        for key, value in SCENARIOS[scenario].items():
            st.session_state[key] = value

    st.sidebar.markdown("### 01 공식 매출 Anchor")
    company = st.sidebar.text_input("Company", key="company")
    product = st.sidebar.text_input("Product / asset", key="product")
    indication = st.sidebar.text_input("Indication market", key="indication")
    currency_label = st.sidebar.selectbox("Currency label", ["USD", "GBP", "EUR", "JPY", "KRW"], key="currency_label")
    reported_sales = st.sidebar.number_input(
        "Official sales anchor, million",
        min_value=0.0,
        step=10.0,
        key="reported_sales",
    )
    anchor_year = st.sidebar.number_input(
        "Anchor year",
        min_value=2000,
        max_value=2100,
        step=1,
        key="anchor_year",
    )
    current_share = st.sidebar.number_input(
        "Current product share, %",
        min_value=0.1,
        max_value=100.0,
        step=0.1,
        key="current_share",
    )

    st.sidebar.markdown("### 02 시장 가정")
    market_cagr = st.sidebar.number_input("Market CAGR, %", step=0.1, key="market_cagr")
    initial_share = st.sidebar.number_input("Initial share, %", min_value=0.0, max_value=100.0, step=0.1, key="initial_share")
    peak_share = st.sidebar.number_input("Peak share, %", min_value=0.0, max_value=100.0, step=0.1, key="peak_share")
    uptake_speed = st.sidebar.slider("Uptake speed", min_value=0.15, max_value=1.25, step=0.05, key="uptake_speed")
    payer_access = st.sidebar.number_input("Payer access, %", min_value=0.0, max_value=100.0, step=1.0, key="payer_access")
    competition_drag = st.sidebar.number_input("Competition drag, % per year", min_value=0.0, max_value=40.0, step=0.5, key="competition_drag")

    st.sidebar.markdown("### 03 환자 기반 검증")
    patients = st.sidebar.number_input("Prevalent / incident patients", min_value=0, step=1000, key="patients")
    patient_growth = st.sidebar.number_input("Patient growth, %", step=0.1, key="patient_growth")
    diagnosis_rate = st.sidebar.number_input("Diagnosis rate, %", min_value=0.0, max_value=100.0, step=1.0, key="diagnosis_rate")
    treatment_rate = st.sidebar.number_input("Treatment rate, %", min_value=0.0, max_value=100.0, step=1.0, key="treatment_rate")
    eligible_rate = st.sidebar.number_input("Eligible rate, %", min_value=0.0, max_value=100.0, step=1.0, key="eligible_rate")
    annual_price = st.sidebar.number_input("Net annual price per patient", min_value=0.0, step=100.0, key="annual_price")
    adherence = st.sidebar.number_input("Adherence / persistence, %", min_value=0.0, max_value=100.0, step=1.0, key="adherence")
    market_weight = st.sidebar.slider("Market model weight, %", min_value=0.0, max_value=100.0, step=5.0, key="market_weight")

    st.sidebar.markdown("### 04 근거 기록")
    source_type = st.sidebar.selectbox(
        "Primary source type",
        ["SEC EDGAR 10-K / 20-F", "Company Annual Report", "DART / OpenDART", "CMS / HIRA cross-check", "Manual review needed"],
        key="source_type",
    )
    evidence_url = st.sidebar.text_input("Evidence URL", key="evidence_url")
    filing_date = st.sidebar.text_input("Filing / report date", key="filing_date")
    accession = st.sidebar.text_input("Accession / report ID", key="accession")
    reviewer_note = st.sidebar.text_area("Reviewer note", height=110, key="reviewer_note")

    st.sidebar.markdown("### 05 Pipeline risk")
    phase = st.sidebar.selectbox("Clinical phase", list(PHASE_POS.keys()), key="pipeline_phase")
    probability_default = PHASE_POS[phase]
    pipeline = PipelineInput(
        asset=st.sidebar.text_input("Pipeline asset", key="pipeline_asset"),
        indication=st.sidebar.text_input("Pipeline indication", key="pipeline_indication"),
        phase=phase,
        launch_year=st.sidebar.number_input("Expected launch year", min_value=anchor_year, max_value=anchor_year + 15, step=1, key="pipeline_launch_year"),
        probability=st.sidebar.number_input("Probability of success, %", min_value=0.0, max_value=100.0, step=0.5, key="pipeline_probability"),
        label_factor=st.sidebar.number_input("Expected label scope, %", min_value=0.0, max_value=100.0, step=1.0, key="pipeline_label_factor"),
        economics=st.sidebar.number_input("Company economics, %", min_value=0.0, max_value=100.0, step=1.0, key="pipeline_economics"),
        nct=st.sidebar.text_input("NCT / clinical ID", key="pipeline_nct"),
        source_type=st.sidebar.text_input("Clinical source type", key="pipeline_source_type"),
        evidence_url=st.sidebar.text_input("Clinical evidence URL", key="pipeline_evidence_url"),
        note=st.sidebar.text_area("Clinical evidence note", height=80, key="pipeline_note"),
    )

    input_data = ForecastInput(
        company=company,
        product=product,
        indication=indication,
        reported_sales=float(reported_sales),
        anchor_year=int(anchor_year),
        current_share=float(current_share),
        market_cagr=float(market_cagr),
        initial_share=float(initial_share),
        peak_share=float(peak_share),
        uptake_speed=float(uptake_speed),
        payer_access=float(payer_access),
        competition_drag=float(competition_drag),
        patients=float(patients),
        patient_growth=float(patient_growth),
        diagnosis_rate=float(diagnosis_rate),
        treatment_rate=float(treatment_rate),
        eligible_rate=float(eligible_rate),
        annual_price=float(annual_price),
        adherence=float(adherence),
        market_weight=float(market_weight),
        source_type=source_type,
        evidence_url=evidence_url,
        filing_date=filing_date,
        accession=accession,
        reviewer_note=reviewer_note,
        currency_label=currency_label,
    )
    lookup_matched = bool(st.session_state.get("lookup_matched", False))
    return input_data, pipeline, lookup_matched


def render_lookup_panel(input_data: ForecastInput) -> None:
    with st.expander("Official revenue lookup", expanded=True):
        cols = st.columns([2, 1, 1])
        query = cols[0].text_input("Company name, ticker, or CIK", value=input_data.company or "LLY", key="lookup_query")
        year = cols[1].number_input("FY", min_value=2000, max_value=2100, value=int(input_data.anchor_year), step=1, key="lookup_year")
        product = cols[2].text_input("Product row keyword", value=input_data.product, key="lookup_product")
        lookup_mode = st.radio("Lookup mode", ["Built-in verified anchors first", "Live SEC lookup"], horizontal=True)

        if st.button("공식 매출 근거 조회", type="primary", width="stretch"):
            st.session_state["lookup_matched"] = False
            anchor = resolve_builtin_anchor(query)
            if anchor and lookup_mode == "Built-in verified anchors first":
                st.session_state["latest_anchor"] = anchor
                st.session_state["pending_anchor"] = anchor
                st.session_state["lookup_matched"] = True
                st.success(f"{anchor['name']} FY {anchor['fiscal_year']} anchor를 forecast에 반영했습니다.")
                st.rerun()
            else:
                try:
                    with st.spinner("SEC EDGAR / Company Facts 근거를 확인하는 중입니다."):
                        result = sec_lookup_cached(query, int(year) if year else None, product)
                    facts = result.get("total_revenue_facts", [])
                    if facts:
                        fact = facts[0]
                        company = result.get("company", {})
                        anchor = {
                            "ticker": company.get("ticker") or "",
                            "name": company.get("name") or query,
                            "value_millions": float(fact["value"]) / 1_000_000,
                            "fiscal_year": int(fact["fiscal_year"]),
                            "filed": fact.get("filed", ""),
                            "concept": fact.get("concept", "Revenue"),
                            "unit": f"{fact.get('unit', 'USD')} millions",
                            "source_type": "SEC EDGAR 10-K / 20-F",
                            "source_url": fact.get("source_url", ""),
                            "accession": fact.get("accession", ""),
                            "note": "SEC Company Facts lookup. Confirm source table and unit before external use.",
                        }
                        st.session_state["latest_anchor"] = anchor
                        st.session_state["pending_anchor"] = anchor
                        st.session_state["lookup_matched"] = True
                        st.success(f"{anchor['name']} FY {anchor['fiscal_year']} SEC anchor를 forecast에 반영했습니다.")
                        st.rerun()
                    st.warning("SEC structured revenue fact를 찾지 못했습니다. 후보 filing table을 수동 검토하세요.")
                    st.json(result, expanded=False)
                except Exception as exc:
                    if anchor:
                        st.session_state["latest_anchor"] = anchor
                        st.session_state["pending_anchor"] = anchor
                        st.session_state["lookup_matched"] = True
                        st.warning(f"Live SEC 조회는 실패했지만 built-in anchor를 반영했습니다: {type(exc).__name__}")
                        st.rerun()
                    st.error(f"조회 실패: {type(exc).__name__}: {exc}")
                    st.code(
                        f'SEC_USER_AGENT="Your Name your@email.com" python3 revenue_filing_tool.py lookup {query} --year {year} --product "{product}"',
                        language="bash",
                    )

        anchor = st.session_state.get("latest_anchor")
        if anchor:
            st.markdown("#### Latest anchor")
            c1, c2, c3 = st.columns(3)
            c1.metric("Company", anchor["name"])
            c2.metric("Revenue", fmt_money(float(anchor["value_millions"]), input_data.currency_label))
            c3.metric("FY / Source", f"{anchor['fiscal_year']} / {anchor['source_type']}")
            st.caption(anchor.get("note", ""))


def safe_filename(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.strip())
    return "_".join(part for part in cleaned.split("_") if part) or "toxiguard_report"


def strategic_readout(input_data: ForecastInput, pipeline: PipelineInput, pipeline_peak_value: float) -> tuple[str, str]:
    contribution = pipeline_peak_value / input_data.reported_sales if input_data.reported_sales else 0
    risk_factor = (
        clamp(pipeline.probability / 100, 0, 1)
        * clamp(pipeline.label_factor / 100, 0, 1)
        * clamp(pipeline.economics / 100, 0, 1)
    )

    if contribution >= 0.15:
        thesis = "Company-scale growth option"
        watch = "The asset can be financially meaningful, but the thesis depends on label breadth, payer access, and durable differentiation."
    elif contribution >= 0.05:
        thesis = "Portfolio contributor"
        watch = "The asset can matter to portfolio growth, while sensitivity remains concentrated in clinical success and commercial access."
    else:
        thesis = "Optionality / validation case"
        watch = "The asset is best viewed as an option until evidence, label, and economics move closer to approval-ready confidence."

    if risk_factor < 0.2:
        watch += " Current risk adjustment is low, so clinical failure sensitivity is material."
    elif risk_factor < 0.5:
        watch += " Risk adjustment is moderate; stage progression should be tied to updated PoS and evidence quality."
    else:
        watch += " Risk adjustment is relatively high, so execution assumptions become the next diligence focus."
    return thesis, watch


def render_visual_dashboard(
    input_data: ForecastInput,
    pipeline: PipelineInput,
    forecast: pd.DataFrame,
    pipeline_forecast: pd.DataFrame,
) -> None:
    peak = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    pipeline_peak = pipeline_forecast.loc[pipeline_forecast["Risk-Adjusted Revenue"].idxmax()]
    peak_market = float(forecast["Market Model"].max())
    peak_patient = float(forecast["Patient Model"].max())
    base_tam = float(forecast.iloc[0]["Base TAM"])
    risk_factor = float(pipeline_forecast["Risk Factor"].iloc[0])

    st.markdown("### Visual Evidence Dashboard")
    st.caption("회사 매출 anchor, implied TAM, market model, patient model, pipeline risk를 한 화면에서 비교합니다.")

    bridge_fig = go.Figure(
        go.Bar(
            x=["Sales anchor", "Implied TAM", "Market peak", "Patient peak", "Triangulated peak", "Risk-adjusted peak"],
            y=[
                input_data.reported_sales,
                base_tam,
                peak_market,
                peak_patient,
                float(peak["Triangulated Forecast"]),
                float(pipeline_peak["Risk-Adjusted Revenue"]),
            ],
            marker_color=["#0f766e", "#1f9d8f", "#2563eb", "#60a5fa", "#f59e0b", "#6d4bc3"],
            text=[
                fmt_money(input_data.reported_sales, input_data.currency_label),
                fmt_money(base_tam, input_data.currency_label),
                fmt_money(peak_market, input_data.currency_label),
                fmt_money(peak_patient, input_data.currency_label),
                fmt_money(float(peak["Triangulated Forecast"]), input_data.currency_label),
                fmt_money(float(pipeline_peak["Risk-Adjusted Revenue"]), input_data.currency_label),
            ],
            textposition="outside",
        )
    )
    bridge_fig.update_layout(
        height=370,
        margin=dict(l=10, r=10, t=28, b=10),
        yaxis_title=f"Revenue ({input_data.currency_label} million)",
        showlegend=False,
    )

    patient_row = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    patient_pool = float(patient_row["Patient Pool"])
    diagnosed = patient_pool * clamp(input_data.diagnosis_rate / 100, 0, 1)
    treated = diagnosed * clamp(input_data.treatment_rate / 100, 0, 1)
    eligible = treated * clamp(input_data.eligible_rate / 100, 0, 1)
    captured = float(patient_row["Treated Patients"])
    funnel_fig = go.Figure(
        go.Funnel(
            y=["Patient pool", "Diagnosed", "Treated", "Eligible", "Captured / adherent"],
            x=[patient_pool, diagnosed, treated, eligible, captured],
            marker={"color": ["#1d4ed8", "#0f766e", "#168f86", "#6d4bc3", "#f59e0b"]},
            textinfo="value+percent initial",
        )
    )
    funnel_fig.update_layout(height=370, margin=dict(l=10, r=10, t=28, b=10))

    mix_fig = go.Figure(
        go.Pie(
            labels=["Market analog", "Patient model"],
            values=[input_data.market_weight, 100 - input_data.market_weight],
            hole=0.62,
            marker_colors=["#0f766e", "#2563eb"],
            textinfo="label+percent",
        )
    )
    mix_fig.update_layout(height=300, margin=dict(l=10, r=10, t=24, b=10), showlegend=False)

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.plotly_chart(bridge_fig, width="stretch")
    with c2:
        st.plotly_chart(funnel_fig, width="stretch")

    c3, c4, c5 = st.columns([1, 1, 1])
    c3.plotly_chart(mix_fig, width="stretch")
    c4.metric("Pipeline risk factor", fmt_pct(risk_factor), "PoS x label x economics")
    c5.metric(
        "Contribution vs anchor",
        fmt_pct(float(pipeline_peak["Risk-Adjusted Revenue"]) / input_data.reported_sales if input_data.reported_sales else 0),
        "Risk-adjusted peak / official anchor",
    )


def formula_table(input_data: ForecastInput, forecast: pd.DataFrame) -> pd.DataFrame:
    market_weight = clamp(input_data.market_weight / 100, 0, 1)
    payer_access = clamp(input_data.payer_access / 100, 0, 1)
    adherence = clamp(input_data.adherence / 100, 0, 1)
    rows = []
    for _, row in forecast.iterrows():
        rows.append(
            {
                "Year": f"FY {int(row['Year'])}",
                "TAM build": f"{fmt_money(float(row['Base TAM']), input_data.currency_label)} x CAGR path",
                "Market model": (
                    f"{fmt_money(float(row['Market TAM']), input_data.currency_label)} x "
                    f"{float(row['Adjusted Share']) * 100:.1f}% x {payer_access * 100:.1f}%"
                ),
                "Patient model": (
                    f"{float(row['Addressable Patients']):,.0f} eligible x "
                    f"{float(row['Adjusted Share']) * 100:.1f}% x {adherence * 100:.1f}% x "
                    f"{input_data.annual_price:,.0f}"
                ),
                "Triangulated": (
                    f"{market_weight * 100:.0f}% market + {(1 - market_weight) * 100:.0f}% patient = "
                    f"{fmt_money(float(row['Triangulated Forecast']), input_data.currency_label)}"
                ),
            }
        )
    return pd.DataFrame(rows)


def render_calculation_basis(input_data: ForecastInput, forecast: pd.DataFrame, pipeline: PipelineInput) -> None:
    base_tam = float(forecast.iloc[0]["Base TAM"])
    peak = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    risk_factor = (
        clamp(pipeline.probability / 100, 0, 1)
        * clamp(pipeline.label_factor / 100, 0, 1)
        * clamp(pipeline.economics / 100, 0, 1)
    )

    st.markdown("### Calculation Basis")
    st.caption("예측값이 어떤 공식에서 나왔는지 검증할 수 있도록 핵심 산식을 분리했습니다.")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Base TAM", fmt_money(base_tam, input_data.currency_label), "Sales / current share")
    f2.metric("Peak TAM", fmt_money(float(peak["Market TAM"]), input_data.currency_label), f"FY {int(peak['Year'])}")
    f3.metric("Model weighting", f"{input_data.market_weight:.0f}% / {100 - input_data.market_weight:.0f}%", "Market / patient")
    f4.metric("Pipeline risk", fmt_pct(risk_factor), "PoS x label x economics")

    st.markdown(
        f"""
        - **Base TAM** = {fmt_money(input_data.reported_sales, input_data.currency_label)} / {input_data.current_share:.1f}%
        - **Market model** = TAM x adjusted share x payer access
        - **Patient model** = addressable patients x adjusted share x adherence x net annual price
        - **Triangulated forecast** = market model x {input_data.market_weight:.0f}% + patient model x {100 - input_data.market_weight:.0f}%
        - **Risk-adjusted pipeline revenue** = triangulated forecast x {pipeline.probability:.1f}% x {pipeline.label_factor:.1f}% x {pipeline.economics:.1f}%
        """
    )
    st.dataframe(formula_table(input_data, forecast), width="stretch", hide_index=True)


def render_insight_report(
    input_data: ForecastInput,
    pipeline: PipelineInput,
    forecast: pd.DataFrame,
    pipeline_forecast: pd.DataFrame,
    confidence: int,
    checks: pd.DataFrame,
) -> None:
    peak = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    year5 = forecast.iloc[min(4, len(forecast) - 1)]
    pipeline_peak = pipeline_forecast.loc[pipeline_forecast["Risk-Adjusted Revenue"].idxmax()]
    thesis, watch = strategic_readout(input_data, pipeline, float(pipeline_peak["Risk-Adjusted Revenue"]))

    st.markdown("### Insight Report")
    st.caption("회사 현재 매출, 중점 임상, 미래 타겟 시장, risk-adjusted 매출을 한 문장 논리로 연결합니다.")
    st.markdown(
        f"""
        **Strategic readout: {thesis}**

        Using {input_data.company}'s official sales anchor of **{fmt_money(input_data.reported_sales, input_data.currency_label)}**
        and implied current TAM of **{fmt_money(float(forecast.iloc[0]['Base TAM']), input_data.currency_label)}**, the model estimates
        **Year 5 forecast of {fmt_money(float(year5['Triangulated Forecast']), input_data.currency_label)}** and
        **commercial peak of {fmt_money(float(peak['Triangulated Forecast']), input_data.currency_label)} in FY {int(peak['Year'])}**.

        The linked pipeline case, **{pipeline.asset} / {pipeline.indication}**, produces a
        **risk-adjusted peak of {fmt_money(float(pipeline_peak['Risk-Adjusted Revenue']), input_data.currency_label)}** after applying
        PoS, label scope, and company economics.

        **Watch point:** {watch}
        """
    )

    insight_rows = pd.DataFrame(
        [
            {
                "Question": "What is anchored?",
                "Current answer": f"{input_data.company} official revenue: {fmt_money(input_data.reported_sales, input_data.currency_label)}",
                "Review focus": "Confirm source table, units, footnotes, and whether the number is company-, segment-, product-, or indication-level.",
            },
            {
                "Question": "What drives future sales?",
                "Current answer": f"Peak share {input_data.peak_share:.1f}%, payer access {input_data.payer_access:.1f}%, CAGR {input_data.market_cagr:.1f}%",
                "Review focus": "Run sensitivity on peak share, payer access, net price, diagnosis/treatment/eligibility, and competition drag.",
            },
            {
                "Question": "Why the clinical program matters",
                "Current answer": f"{pipeline.phase}, launch FY {pipeline.launch_year}, risk factor {fmt_pct(float(pipeline_forecast['Risk Factor'].iloc[0]))}",
                "Review focus": "Tie PoS to clinical stage, endpoint strength, label scope, safety, and commercial economics.",
            },
            {
                "Question": "Can this be shared externally?",
                "Current answer": f"Evidence confidence {confidence}%; open checks {(checks['Status'] != 'Pass').sum()}",
                "Review focus": "Add accession/report ID and cite official source before presenting as evidence-backed analysis.",
            },
        ]
    )
    st.dataframe(insight_rows, width="stretch", hide_index=True)


def build_html_report(
    input_data: ForecastInput,
    pipeline: PipelineInput,
    forecast: pd.DataFrame,
    pipeline_forecast: pd.DataFrame,
    confidence: int,
    checks: pd.DataFrame,
) -> bytes:
    peak = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    year5 = forecast.iloc[min(4, len(forecast) - 1)]
    pipeline_peak = pipeline_forecast.loc[pipeline_forecast["Risk-Adjusted Revenue"].idxmax()]
    thesis, watch = strategic_readout(input_data, pipeline, float(pipeline_peak["Risk-Adjusted Revenue"]))
    display_forecast = forecast[
        ["Year", "Market TAM", "Adjusted Share", "Market Model", "Patient Model", "Triangulated Forecast"]
    ].copy()
    display_forecast["Adjusted Share"] = display_forecast["Adjusted Share"].map(lambda value: f"{value * 100:.1f}%")
    display_pipeline = pipeline_forecast[["Year", "Unadjusted Revenue", "Risk Factor", "Risk-Adjusted Revenue"]].copy()
    display_pipeline["Risk Factor"] = display_pipeline["Risk Factor"].map(fmt_pct)

    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    report = f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>ToxiGuard Revenue Forecast Report</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color:#102f43; margin:32px; }}
        h1 {{ font-size: 34px; margin-bottom: 4px; }}
        h2 {{ margin-top: 28px; color:#0f766e; }}
        .kicker {{ color:#0f766e; font-weight:800; letter-spacing:.04em; text-transform:uppercase; }}
        .grid {{ display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin:18px 0; }}
        .metric {{ border:1px solid #d9e3df; border-radius:10px; padding:14px; background:#f8fbfb; }}
        .metric span {{ display:block; color:#667; font-size:12px; font-weight:700; text-transform:uppercase; }}
        .metric strong {{ display:block; font-size:24px; margin-top:4px; }}
        .box {{ border:1px solid #d9e3df; border-radius:10px; padding:18px; margin:14px 0; }}
        table {{ border-collapse:collapse; width:100%; font-size:13px; }}
        th, td {{ border:1px solid #d9e3df; padding:8px; text-align:left; }}
        th {{ background:#eef7f6; }}
        .note {{ color:#5a6872; font-size:12px; margin-top:24px; }}
      </style>
    </head>
    <body>
      <div class="kicker">ToxiGuard Revenue Forecast Intelligence</div>
      <h1>{esc(input_data.company)} · {esc(input_data.product)}</h1>
      <p>{esc(input_data.indication)} · Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
      <div class="grid">
        <div class="metric"><span>Official anchor</span><strong>{esc(fmt_money(input_data.reported_sales, input_data.currency_label))}</strong><small>FY {input_data.anchor_year}</small></div>
        <div class="metric"><span>Year 5 forecast</span><strong>{esc(fmt_money(float(year5['Triangulated Forecast']), input_data.currency_label))}</strong><small>FY {int(year5['Year'])}</small></div>
        <div class="metric"><span>Commercial peak</span><strong>{esc(fmt_money(float(peak['Triangulated Forecast']), input_data.currency_label))}</strong><small>FY {int(peak['Year'])}</small></div>
        <div class="metric"><span>Risk-adjusted peak</span><strong>{esc(fmt_money(float(pipeline_peak['Risk-Adjusted Revenue']), input_data.currency_label))}</strong><small>confidence {confidence}%</small></div>
      </div>
      <div class="box">
        <h2>Conclusion</h2>
        <p><strong>{esc(thesis)}</strong></p>
        <p>{esc(watch)}</p>
      </div>
      <h2>Calculation Basis</h2>
      <p>Base TAM = official sales anchor / current share. Market and patient models are triangulated by evidence weighting, then adjusted by clinical PoS, label scope, and company economics.</p>
      <h2>Annual Forecast</h2>
      {display_forecast.to_html(index=False)}
      <h2>Pipeline Risk Adjustment</h2>
      {display_pipeline.to_html(index=False)}
      <h2>Evidence Validation</h2>
      {checks.to_html(index=False)}
      <p class="note">Educational analysis only. Confirm source URL, accession/report ID, source table units, footnotes, product scope, and all assumptions before external use.</p>
    </body>
    </html>
    """
    return report.encode("utf-8")


def main() -> None:
    render_header()
    input_data, pipeline, lookup_matched = sidebar_inputs()
    forecast = calculate_forecast(input_data)
    pipeline_forecast = calculate_pipeline(input_data, pipeline, forecast)
    confidence, confidence_note = calculate_confidence(input_data, lookup_matched)
    checks = validation_checks(input_data, pipeline, forecast, pipeline_forecast, confidence)
    memo = markdown_memo(input_data, pipeline, forecast, pipeline_forecast, confidence, checks)

    peak = forecast.loc[forecast["Triangulated Forecast"].idxmax()]
    year5 = forecast.iloc[min(4, len(forecast) - 1)]
    base_tam = forecast.iloc[0]["Base TAM"]
    pipeline_peak = pipeline_forecast.loc[pipeline_forecast["Risk-Adjusted Revenue"].idxmax()]

    metric_cols = st.columns(5)
    metric_cols[0].metric("Peak sales", fmt_money(float(peak["Triangulated Forecast"]), input_data.currency_label), f"FY {int(peak['Year'])}")
    metric_cols[1].metric("Year 5 forecast", fmt_money(float(year5["Triangulated Forecast"]), input_data.currency_label), "Triangulated")
    metric_cols[2].metric("Current TAM", fmt_money(float(base_tam), input_data.currency_label), "Sales / current share")
    metric_cols[3].metric("Risk-adjusted peak", fmt_money(float(pipeline_peak["Risk-Adjusted Revenue"]), input_data.currency_label), f"FY {int(pipeline_peak['Year'])}")
    metric_cols[4].metric("Evidence confidence", f"{confidence}%", confidence_note or "review needed")

    st.markdown(
        '<div class="block-note">Business Evidence 모듈은 CMC RA 판단을 대체하지 않습니다. Partner 또는 investor appendix에서 매출 anchor와 가정을 분리해 설명하기 위한 보조 근거입니다.</div>',
        unsafe_allow_html=True,
    )

    render_lookup_panel(input_data)

    tab_forecast, tab_calculation, tab_pipeline, tab_insight, tab_validation, tab_export = st.tabs(
        ["Forecast", "Calculation basis", "Pipeline risk", "Insight report", "Evidence validation", "Export memo"]
    )

    with tab_forecast:
        render_visual_dashboard(input_data, pipeline, forecast, pipeline_forecast)

        st.markdown("### Annual Revenue Forecast")
        chart_df = forecast.melt(
            id_vars=["Year"],
            value_vars=["Market Model", "Patient Model", "Triangulated Forecast"],
            var_name="Model",
            value_name="Revenue",
        )
        fig = px.line(chart_df, x="Year", y="Revenue", color="Model", markers=True)
        fig.update_layout(height=420, yaxis_title=f"Revenue ({input_data.currency_label} million)", legend_title="")
        st.plotly_chart(fig, width="stretch")

        table = forecast[
            [
                "Year",
                "Market TAM",
                "Adjusted Share",
                "Market Model",
                "Patient Model",
                "Triangulated Forecast",
                "Treated Patients",
            ]
        ].copy()
        table["Adjusted Share"] = table["Adjusted Share"].map(lambda x: f"{x * 100:.1f}%")
        st.dataframe(table, width="stretch", hide_index=True)

    with tab_calculation:
        render_calculation_basis(input_data, forecast, pipeline)

    with tab_pipeline:
        c1, c2, c3, c4 = st.columns(4)
        risk_factor = float(pipeline_forecast["Risk Factor"].iloc[0])
        c1.metric("PoS", f"{pipeline.probability:.1f}%")
        c2.metric("Label scope", f"{pipeline.label_factor:.1f}%")
        c3.metric("Economics", f"{pipeline.economics:.1f}%")
        c4.metric("Total risk factor", fmt_pct(risk_factor))

        plot = pipeline_forecast.melt(
            id_vars=["Year"],
            value_vars=["Unadjusted Revenue", "Risk-Adjusted Revenue"],
            var_name="Revenue type",
            value_name="Revenue",
        )
        fig = px.bar(plot, x="Year", y="Revenue", color="Revenue type", barmode="group")
        fig.update_layout(height=390, yaxis_title=f"Revenue ({input_data.currency_label} million)", legend_title="")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(pipeline_forecast, width="stretch", hide_index=True)

    with tab_insight:
        render_insight_report(input_data, pipeline, forecast, pipeline_forecast, confidence, checks)

    with tab_validation:
        score_cols = st.columns(3)
        pass_count = int((checks["Status"] == "Pass").sum())
        score_cols[0].metric("Passed checks", f"{pass_count}/{len(checks)}")
        score_cols[1].metric("Evidence confidence", f"{confidence}%")
        score_cols[2].metric("Open items", int((checks["Status"] != "Pass").sum()))
        st.dataframe(checks, width="stretch", hide_index=True)
        st.markdown("#### Source policy")
        st.markdown(
            "- Tier A: SEC EDGAR / XBRL, official annual report, DART official filing\n"
            "- Tier B: CMS, HIRA, payer/utilization public data used as cross-check\n"
            "- Avoid using news/blog/third-party summaries as the primary revenue anchor"
        )

    with tab_export:
        st.download_button(
            "Markdown memo 다운로드",
            data=memo.encode("utf-8"),
            file_name=f"{input_data.company.replace(' ', '_')}_{input_data.product}_revenue_forecast_memo.md",
            mime="text/markdown",
            width="stretch",
        )
        st.download_button(
            "Forecast CSV 다운로드",
            data=build_csv_bytes(forecast, pipeline_forecast),
            file_name=f"{input_data.company.replace(' ', '_')}_{input_data.product}_forecast.csv",
            mime="text/csv",
            width="stretch",
        )
        st.download_button(
            "HTML report 다운로드",
            data=build_html_report(input_data, pipeline, forecast, pipeline_forecast, confidence, checks),
            file_name=f"{safe_filename(input_data.company)}_{safe_filename(input_data.product)}_revenue_forecast_report.html",
            mime="text/html",
            width="stretch",
        )
        st.markdown("#### Memo preview")
        st.text_area("Markdown", memo, height=520)


if __name__ == "__main__":
    main()
