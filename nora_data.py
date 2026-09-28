"""Source-preserving annual company revenue for NORA.

Company Facts contains entity-wide standard taxonomy facts; ``fy`` describes
the filing context, including comparative facts, rather than each fact's year.
We therefore key every observation by its actual start and end dates. See:
https://www.sec.gov/search-filings/edgar-application-programming-interfaces
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import math
from numbers import Real
import os
import re
from typing import Any, Mapping
import unicodedata

import pandas as pd
import requests

from revenue_filing_tool import (
    Company,
    KNOWN_PHARMA_COMPANIES,
    SEC_SUBMISSIONS_URL,
    SecClient,
    make_sec_source_url,
)


DEFAULT_NORA_USER_AGENT = "NORA/1.3 (https://github.com/lyn0109-Toxi/ToxiGuard-RF)"
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}
# Deliberately excludes product, segment, geographic, royalty-only, and custom
# tags. Finding a word such as 'sales' is not evidence of consolidated revenue.
REVENUE_CONCEPTS = (
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "Revenues"),
    ("us-gaap", "SalesRevenueNet"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax"),
    ("ifrs-full", "Revenue"),
)
_CONCEPT_PRIORITY = {key: i for i, key in enumerate(REVENUE_CONCEPTS)}

_COMPANY_DETAILS = {
    "ABBV": ("애브비", "USD", ("AbbVie", "애브비")),
    "AMGN": ("암젠", "USD", ("Amgen", "암젠")),
    "AZN": ("아스트라제네카", "USD", ("AstraZeneca", "아스트라제네카", "아스트라 제네카")),
    "BIIB": ("바이오젠", "USD", ("Biogen", "바이오젠")),
    "BMY": ("브리스톨 마이어스 스퀴브", "USD", ("BMS", "Bristol Myers Squibb", "브리스톨마이어스스퀴브", "브리스톨 마이어스 스큅")),
    "GILD": ("길리어드", "USD", ("Gilead", "길리어드", "길리어드사이언스")),
    "GSK": ("GSK", "GBP", ("GlaxoSmithKline", "Glaxo Smith Kline", "글락소스미스클라인", "지에스케이")),
    "JNJ": ("존슨앤드존슨", "USD", ("Johnson & Johnson", "Johnson and Johnson", "존슨앤드존슨", "존슨앤존슨", "얀센")),
    "LLY": ("일라이 릴리", "USD", ("Lilly", "Eli Lilly", "릴리", "일라이릴리")),
    "MRK": ("머크 · MSD (미국)", "USD", ("Merck & Co", "MSD", "머크", "미국머크", "엠에스디")),
    "MRNA": ("모더나", "USD", ("Moderna", "모더나")),
    "NVO": ("노보 노디스크", "DKK", ("Novo Nordisk", "노보노디스크", "노보")),
    "NVS": ("노바티스", "USD", ("Novartis", "노바티스")),
    "PFE": ("화이자", "USD", ("Pfizer", "화이자")),
    "REGN": ("리제네론", "USD", ("Regeneron", "리제네론", "리제너론")),
    "SNY": ("사노피", "EUR", ("Sanofi", "사노피")),
    "TAK": ("다케다", "JPY", ("Takeda", "다케다", "타케다", "다케다제약")),
    "VRTX": ("버텍스", "USD", ("Vertex", "버텍스", "버텍스파마슈티컬")),
}

COMPANY_REGISTRY = {
    ticker: {
        **company,
        "name_ko": _COMPANY_DETAILS[ticker][0],
        "reporting_currency": _COMPANY_DETAILS[ticker][1],
        "aliases": list(_COMPANY_DETAILS[ticker][2]),
    }
    for ticker, company in KNOWN_PHARMA_COMPANIES.items()
    if ticker in _COMPANY_DETAILS
}

CANONICAL_COLUMNS = [
    "ticker", "company", "fiscal_year", "period_start", "period_end",
    "revenue", "currency", "concept", "taxonomy", "filed", "accession",
    "source_url", "year_basis", "source_kind",
]


class RevenueDataError(RuntimeError):
    """An upstream failure suitable for a concise UI error message."""


def _search_key(value: Any) -> str:
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^\w]", "", value, flags=re.UNICODE).replace("_", "")


def search_companies(query: str) -> list[dict[str, Any]]:
    """Return selectable registry candidates, never choose an ambiguous match.

    Blank input lists supported companies. Exact ticker/name/alias hits appear
    first; a nonexact search must have at least two characters.
    """
    key = _search_key(query)
    matches = []
    for company in COMPANY_REGISTRY.values():
        tokens = [_search_key(company[field]) for field in ("ticker", "name", "name_ko")]
        tokens.extend(_search_key(alias) for alias in company["aliases"])
        exact = bool(key and (key in tokens or (key.isdigit() and key.zfill(10) == company["cik"])))
        if not key or exact or (len(key) >= 2 and any(key in token for token in tokens)):
            matches.append((not exact, company["name"], dict(company, aliases=list(company["aliases"]))))
    return [item[2] for item in sorted(matches, key=lambda item: item[:2])]


def _as_company(company: Company | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(company, Company):
        supplied = {"ticker": company.ticker, "name": company.name, "cik": company.cik}
    elif isinstance(company, Mapping):
        supplied = dict(company)
    else:
        raise TypeError("company must be a Company or a registry mapping.")
    ticker = str(supplied.get("ticker", "")).strip().upper()
    merged = {**COMPANY_REGISTRY.get(ticker, {}), **supplied, "ticker": ticker}
    cik = str(merged.get("cik", ""))
    if not re.fullmatch(r"\d{1,10}", cik):
        raise ValueError("A valid SEC CIK is required.")
    merged["cik"] = cik.zfill(10)
    return merged


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(float(value))


def _annual_period(start: Any, end: Any) -> bool:
    start_date, end_date = _date(start), _date(end)
    return bool(start_date and end_date and 330 <= (end_date - start_date).days + 1 <= 400)


def _filings_by_accession(submissions: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    recent = (submissions or {}).get("filings", {}).get("recent", {})
    result = {}
    for i, accession in enumerate(recent.get("accessionNumber", [])):
        result[accession] = {
            key: values[i]
            for key, values in recent.items()
            if isinstance(values, list) and i < len(values)
        }
    return result


def _fiscal_year(start: str, end: str, company: Mapping[str, Any], versions: list[dict[str, Any]], filings: Mapping[str, Any]) -> tuple[int, str]:
    # Takeda explicitly calls April 2024–March 2025 FY2024. Do not label it 2025
    # merely because the SEC filing/report period ends in 2025.
    # https://www.takeda.com/investors/sec-filings-and-security-reports/
    if company["ticker"] == "TAK" and start[5:] == "04-01" and end[5:] == "03-31":
        return int(start[:4]), "issuer_start_year"
    # Only trust a filing-context FY when its reportDate matches this fact's
    # end. Comparative observations in that filing belong to earlier periods.
    for version in sorted(versions, key=_version_sort, reverse=True):
        filing = filings.get(version["accession"], {})
        fy = version.get("filing_fiscal_year")
        if filing.get("reportDate") == end and isinstance(fy, int) and not isinstance(fy, bool):
            if abs(fy - int(end[:4])) <= 1:
                return fy, "issuer_fiscal_year"
    if company["ticker"] in COMPANY_REGISTRY:
        end_date = date.fromisoformat(end)
        # Registry issuers other than Takeda use December or 52/53-week years.
        if end_date.month == 12 or (end_date.month == 1 and end_date.day <= 7):
            year = end_date.year - (end_date.month == 1)
            return year, "issuer_calendar_year"
    return int(end[:4]), "derived_period_end_year"


def _version_sort(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("filed", "")),
        str(row.get("accession", "")),
        -_CONCEPT_PRIORITY.get((row.get("taxonomy"), row.get("concept")), 99),
    )


def extract_annual_revenue(payload: Mapping[str, Any], company: Company | Mapping[str, Any], submissions: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Select latest-filed consolidated annual values, with every version kept.

    One row is returned for each actual period. Known issuer reporting currency
    is used when SEC also supplies convenience translations. Unknown issuers
    with multiple currencies require an explicit ``reporting_currency``.
    Same-filing conflicting values are omitted instead of arbitrarily chosen.
    Empty output means no supported annual fact, never a fabricated estimate.
    """
    company_info = _as_company(company)
    payload_cik = payload.get("cik")
    if payload_cik is not None and str(payload_cik).zfill(10) != company_info["cik"]:
        raise RevenueDataError("SEC company identity does not match the selected company.")
    filings = _filings_by_accession(submissions)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    facts = payload.get("facts", {})
    for taxonomy, concept in REVENUE_CONCEPTS:
        units = facts.get(taxonomy, {}).get(concept, {}).get("units", {})
        for currency, observations in units.items():
            if not re.fullmatch(r"[A-Z]{3}", currency):
                continue
            for observation in observations:
                start, end = observation.get("start"), observation.get("end")
                if observation.get("form") not in ANNUAL_FORMS or observation.get("fp") != "FY":
                    continue
                if not _annual_period(start, end) or not _number(observation.get("val")):
                    continue
                accession = str(observation.get("accn", ""))
                filed = str(observation.get("filed", ""))
                if not re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) or not _date(filed):
                    continue
                if _date(filed) < _date(end):
                    continue
                document = filings.get(accession, {}).get("primaryDocument") or f"{accession}-index.html"
                grouped[(start, end)].append({
                    "period_start": start, "period_end": end,
                    "revenue": observation["val"], "currency": currency,
                    "concept": concept, "taxonomy": taxonomy,
                    "filed": filed, "accession": accession,
                    "source_url": make_sec_source_url(company_info["cik"], accession, document),
                    "form": observation["form"],
                    "filing_fiscal_year": observation.get("fy"),
                })
    output = []
    for (start, end), observations in sorted(grouped.items()):
        expected_currency = company_info.get("reporting_currency")
        currencies = {row["currency"] for row in observations}
        if expected_currency:
            observations = [row for row in observations if row["currency"] == expected_currency]
        elif len(currencies) != 1:
            continue
        if not observations:
            continue
        observations.sort(key=_version_sort, reverse=True)
        chosen = observations[0]
        equally_ranked = [row for row in observations if _version_sort(row) == _version_sort(chosen)]
        if len({row["revenue"] for row in equally_ranked}) != 1:
            continue
        versions, seen = [], set()
        for observation in observations:
            key = tuple(observation.get(field) for field in ("taxonomy", "concept", "currency", "accession", "filed", "revenue"))
            if key not in seen:
                versions.append(observation)
                seen.add(key)
        fiscal_year, year_basis = _fiscal_year(start, end, company_info, versions, filings)
        same_basis = [row for row in versions if (row["taxonomy"], row["concept"], row["currency"]) == (chosen["taxonomy"], chosen["concept"], chosen["currency"])]
        output.append({
            "ticker": company_info["ticker"],
            "company": company_info.get("name") or payload.get("entityName", company_info["ticker"]),
            "fiscal_year": fiscal_year,
            **chosen,
            "year_basis": year_basis,
            "source_kind": "SEC Company Facts",
            "observed_versions": versions,
            "has_revisions": len({row["revenue"] for row in same_basis}) > 1,
            "selection_policy": "latest_filing_then_consolidated_concept_priority",
        })
    return output


def _request_error(exc: Exception) -> RevenueDataError:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in {403, 429}:
        return RevenueDataError(f"SEC access is limited (HTTP {status}). Retry later or configure SEC_USER_AGENT with your real contact information.")
    if isinstance(exc, requests.Timeout):
        return RevenueDataError("SEC request timed out. Please retry.")
    if status:
        return RevenueDataError(f"SEC returned HTTP {status}. Please retry later.")
    return RevenueDataError("SEC data could not be retrieved. Check your connection and retry.")


def fetch_company_revenue(ticker: str, user_agent: str | None = None) -> list[dict[str, Any]]:
    """Fetch current source data for one explicitly selected registry ticker."""
    ticker = str(ticker or "").strip().upper()
    if ticker not in COMPANY_REGISTRY:
        raise ValueError("Select a supported company ticker from the search results.")
    company_info = COMPANY_REGISTRY[ticker]
    client = SecClient(user_agent=user_agent or os.getenv("SEC_USER_AGENT") or DEFAULT_NORA_USER_AGENT)
    company = Company(query=ticker, name=company_info["name"], ticker=ticker, cik=company_info["cik"], source="NORA verified company registry")
    try:
        payload = client.company_facts(company)
    except (requests.RequestException, ValueError) as exc:
        raise _request_error(exc) from exc
    metadata_warning = ""
    try:
        submissions = client.get_json(SEC_SUBMISSIONS_URL.format(cik=company.cik))
    except (requests.RequestException, ValueError) as exc:
        submissions = None
        metadata_warning = str(_request_error(exc)) + " Filing index links and period-derived years are shown."
    if not isinstance(payload, Mapping) or not isinstance(payload.get("facts"), Mapping):
        raise RevenueDataError("SEC returned an invalid Company Facts response.")
    if submissions is not None and not isinstance(submissions, Mapping):
        raise RevenueDataError("SEC returned an invalid submissions response.")
    rows = extract_annual_revenue(payload, company_info, submissions)
    if metadata_warning:
        for row in rows:
            row["metadata_warning"] = metadata_warning
    return rows


def _same_basis(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return all(left.get(key) == right.get(key) for key in ("currency", "concept", "taxonomy"))


def build_comparison(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Return unique annual periods with cautious percentage-point YoY values.

    ``yoy_pct`` is 10.0 for 10% growth, not a fraction. An earlier comparative
    from the same filing is preferred as its denominator. Missing years,
    currency/concept changes, nonpositive bases, and incompatible restatements
    leave YoY missing with a reason. No currency conversion is performed.
    """
    columns = CANONICAL_COLUMNS + ["revenue_billions", "yoy_pct", "comparability_note", "yoy_prior_revenue", "yoy_prior_accession", "yoy_prior_source_url"]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if not record.get("ticker") or not _annual_period(record.get("period_start"), record.get("period_end")) or not _number(record.get("revenue")):
            continue
        groups[(record["ticker"], record["period_start"], record["period_end"])].append(dict(record))
    selected = []
    for key, versions in groups.items():
        currencies = {row.get("currency") for row in versions}
        if len(currencies) > 1:
            currency = COMPANY_REGISTRY.get(key[0], {}).get("reporting_currency")
            if not currency:
                continue
            versions = [row for row in versions if row.get("currency") == currency]
        if not versions:
            continue
        versions.sort(key=_version_sort, reverse=True)
        best = versions[0]
        ties = [row for row in versions if _version_sort(row) == _version_sort(best)]
        if len({row["revenue"] for row in ties}) > 1:
            continue
        history = list(best.get("observed_versions") or [])
        history.extend(row for row in versions if row is not best)
        if history:
            best["observed_versions"] = history
        best["has_revisions"] = bool(best.get("has_revisions")) or any(_same_basis(best, row) and row["revenue"] != best["revenue"] for row in history)
        selected.append(best)
    selected.sort(key=lambda row: (row["ticker"], row["period_end"], row["period_start"]))
    previous: dict[str, dict[str, Any]] = {}
    output = []
    for current in selected:
        row = dict(current, revenue_billions=float(current["revenue"]) / 1_000_000_000, yoy_pct=None, yoy_prior_revenue=None, yoy_prior_accession=None, yoy_prior_source_url=None)
        prior = previous.get(current["ticker"])
        note = "first_available_period"
        if prior:
            gap = (_date(current["period_start"]) - _date(prior["period_end"])).days
            end_gap = (_date(current["period_end"]) - _date(prior["period_end"])).days
            if gap != 1 or not 330 <= end_gap <= 400:
                note = "nonconsecutive_periods"
            elif not _same_basis(current, prior):
                note = "currency_or_concept_changed"
            else:
                matching = [version for version in (prior.get("observed_versions") or [prior]) if version.get("accession") == current.get("accession") and _same_basis(current, version)]
                matching_values = {version["revenue"] for version in matching}
                baseline = matching[0] if len(matching_values) == 1 else prior
                if len(matching_values) > 1:
                    note = "conflicting_comparative_values"
                elif not matching and (current.get("has_revisions") or prior.get("has_revisions")) and current.get("accession") != prior.get("accession"):
                    note = "incompatible_restatement_basis"
                elif baseline["revenue"] <= 0:
                    note = "nonpositive_prior_revenue"
                else:
                    row["yoy_pct"] = (current["revenue"] / baseline["revenue"] - 1) * 100
                    row["yoy_prior_revenue"] = baseline["revenue"]
                    row["yoy_prior_accession"] = baseline.get("accession")
                    row["yoy_prior_source_url"] = baseline.get("source_url")
                    note = "same_filing_comparative" if matching else "consecutive_same_basis"
        row["comparability_note"] = note
        output.append(row)
        previous[current["ticker"]] = current
    if not output:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(output)
    result["yoy_pct"] = pd.to_numeric(result["yoy_pct"], errors="coerce")
    return result
