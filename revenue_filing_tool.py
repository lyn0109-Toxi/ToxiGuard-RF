from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests


SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_plain}/{accession}/{document}"

DEFAULT_FORMS = ("10-K", "20-F")
DEFAULT_USER_AGENT = "ToxiGuardRevenueTool/1.0 (set SEC_USER_AGENT with contact email)"


SOURCE_REGISTRY = [
    {
        "name": "SEC EDGAR Company Filings",
        "url": "https://www.sec.gov/edgar/search/",
        "coverage": "US-listed companies and many foreign issuers through 10-K, 10-Q, 20-F, and 6-K filings.",
        "best_for": "Audited company revenue, segment revenue, and disclosed product revenue tables.",
        "evidence_tier": "A",
        "limitation": "Product-by-indication splits are only available when the company discloses them.",
    },
    {
        "name": "SEC XBRL Company Facts API",
        "url": "https://data.sec.gov/api/xbrl/companyfacts/",
        "coverage": "Structured XBRL facts for SEC filers.",
        "best_for": "Machine-checkable total revenue and standardized financial statement facts.",
        "evidence_tier": "A",
        "limitation": "Product-level revenue is often not standardized in XBRL.",
    },
    {
        "name": "Company Annual Report / Investor Relations",
        "url": "Company investor-relations pages",
        "coverage": "Global pharma issuers including Roche, Novo Nordisk, Novartis, Sanofi, GSK, AstraZeneca.",
        "best_for": "Official annual reports, finance reports, and product sales presentations.",
        "evidence_tier": "A/B",
        "limitation": "Formats vary by company and year; automated extraction may need manual review.",
    },
    {
        "name": "DART / OpenDART",
        "url": "https://dart.fss.or.kr/",
        "coverage": "Korean listed companies and Korean regulatory filings.",
        "best_for": "Korean official filings and annual reports.",
        "evidence_tier": "A",
        "limitation": "OpenDART automated access requires an API key.",
    },
    {
        "name": "CMS Drug Spending / Medicare Part D",
        "url": "https://www.cms.gov/data-research/statistics-trends-and-reports/cms-drug-spending",
        "coverage": "US public payer drug spending and utilization.",
        "best_for": "Spend and utilization cross-checks for marketed products.",
        "evidence_tier": "B",
        "limitation": "Not company-reported net sales; payer population and rebate treatment differ.",
    },
    {
        "name": "HIRA Open Data",
        "url": "https://opendata.hira.or.kr/",
        "coverage": "Korean claims-based healthcare and drug-use data.",
        "best_for": "Korean utilization and claims-based market cross-checks.",
        "evidence_tier": "B",
        "limitation": "Claims basis; non-covered use can be missing.",
    },
]


KNOWN_PHARMA_COMPANIES = {
    "ABBV": {"ticker": "ABBV", "cik": "0001551152", "name": "AbbVie Inc."},
    "AMGN": {"ticker": "AMGN", "cik": "0000318154", "name": "Amgen Inc."},
    "AZN": {"ticker": "AZN", "cik": "0000901832", "name": "AstraZeneca PLC"},
    "BIIB": {"ticker": "BIIB", "cik": "0000875045", "name": "Biogen Inc."},
    "BMY": {"ticker": "BMY", "cik": "0000014272", "name": "Bristol-Myers Squibb Company"},
    "GILD": {"ticker": "GILD", "cik": "0000882095", "name": "Gilead Sciences, Inc."},
    "GSK": {"ticker": "GSK", "cik": "0001131399", "name": "GSK plc"},
    "JNJ": {"ticker": "JNJ", "cik": "0000200406", "name": "Johnson & Johnson"},
    "LLY": {"ticker": "LLY", "cik": "0000059478", "name": "Eli Lilly and Company"},
    "MRK": {"ticker": "MRK", "cik": "0000310158", "name": "Merck & Co., Inc."},
    "MRNA": {"ticker": "MRNA", "cik": "0001682852", "name": "Moderna, Inc."},
    "NVO": {"ticker": "NVO", "cik": "0000353278", "name": "Novo Nordisk A/S"},
    "NVS": {"ticker": "NVS", "cik": "0001114448", "name": "Novartis AG"},
    "PFE": {"ticker": "PFE", "cik": "0000078003", "name": "Pfizer Inc."},
    "REGN": {"ticker": "REGN", "cik": "0000872589", "name": "Regeneron Pharmaceuticals, Inc."},
    "SNY": {"ticker": "SNY", "cik": "0001121404", "name": "Sanofi"},
    "TAK": {"ticker": "TAK", "cik": "0001395064", "name": "Takeda Pharmaceutical Company Limited"},
    "VRTX": {"ticker": "VRTX", "cik": "0000875320", "name": "Vertex Pharmaceuticals Incorporated"},
}

COMPANY_ALIASES = {
    "ABBVIE": "ABBV",
    "AMGEN": "AMGN",
    "ASTRAZENECA": "AZN",
    "BIOGEN": "BIIB",
    "BMS": "BMY",
    "BRISTOL MYERS SQUIBB": "BMY",
    "BRISTOL-MYERS SQUIBB": "BMY",
    "ELI LILLY": "LLY",
    "GILEAD": "GILD",
    "GLAXO": "GSK",
    "GLAXOSMITHKLINE": "GSK",
    "GLAXOSMITHKLINE PLC": "GSK",
    "GLAXO SMITH KLINE": "GSK",
    "GLAXO SMITHKLINE": "GSK",
    "GSK": "GSK",
    "GSK PLC": "GSK",
    "JOHNSON & JOHNSON": "JNJ",
    "JOHNSON JOHNSON": "JNJ",
    "LILLY": "LLY",
    "MERCK": "MRK",
    "MERCK & CO": "MRK",
    "MODERNA": "MRNA",
    "NOVARTIS": "NVS",
    "NOVO NORDISK": "NVO",
    "PFIZER": "PFE",
    "REGENERON": "REGN",
    "SANOFI": "SNY",
    "TAKEDA": "TAK",
    "VERTEX": "VRTX",
}

REVENUE_CONCEPTS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "ProductRevenue",
    "ProductSalesRevenue",
)

PRODUCT_TABLE_KEYWORDS = (
    "product",
    "net product revenue",
    "product sales",
    "product revenues",
    "sales by product",
    "revenue by product",
    "major products",
    "disaggregation of revenue",
    "net revenues by product",
    "significant products",
)

REVENUE_TABLE_KEYWORDS = (
    "revenue",
    "revenues",
    "sales",
    "net sales",
    "net revenue",
    "net revenues",
)

NEGATIVE_TABLE_KEYWORDS = (
    "cash flow",
    "cash flows",
    "balance sheet",
    "debt",
    "lease",
    "tax",
    "pension",
    "compensation",
    "share-based",
    "stock-based",
    "derivative",
    "fair value",
)


@dataclass
class Company:
    query: str
    name: str
    ticker: str
    cik: str
    source: str


@dataclass
class Filing:
    cik: str
    company_name: str
    ticker: str
    form: str
    accession: str
    filed: str
    fiscal_year: str
    primary_document: str
    source_url: str


@dataclass
class RevenueFact:
    concept: str
    fiscal_year: int
    fiscal_period: str
    value: float
    unit: str
    form: str
    filed: str
    accession: str
    source_url: str
    evidence_tier: str = "A"


@dataclass
class CandidateTable:
    rank: int
    score: int
    rows: int
    columns: int
    reason: str
    source_url: str
    evidence_tier: str
    data: list[dict[str, str]]


def normalize_cik(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        raise ValueError("CIK is empty.")
    return digits.zfill(10)


def cik_without_padding(cik: str) -> str:
    return str(int(normalize_cik(cik)))


def normalize_query(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9& ]+", " ", value or "")
    return re.sub(r"\s+", " ", cleaned).strip().upper()


def compact_query(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", normalize_query(value))


def resolve_known_pharma_company(query: str) -> Company | None:
    raw = str(query or "").strip()
    key = normalize_query(raw)
    if not key:
        return None
    ticker = COMPANY_ALIASES.get(key, key)
    if ticker in KNOWN_PHARMA_COMPANIES:
        item = KNOWN_PHARMA_COMPANIES[ticker]
        return Company(query=raw, name=item["name"], ticker=item["ticker"], cik=item["cik"], source="local pharma registry")

    compact = compact_query(key)
    if len(key) < 3 and len(compact) < 3:
        return None
    for item in KNOWN_PHARMA_COMPANIES.values():
        item_ticker = normalize_query(item["ticker"])
        item_name = normalize_query(item["name"])
        item_compact = compact_query(item_name)
        if (
            item_ticker == key
            or item_name == key
            or item_compact == compact
            or (len(key) >= 4 and (key in item_name or item_name in key))
            or (len(compact) >= 5 and (compact in item_compact or item_compact in compact))
        ):
            return Company(query=raw, name=item["name"], ticker=item["ticker"], cik=item["cik"], source="local pharma registry name match")
    return None


def make_sec_source_url(cik: str, accession: str, document: str) -> str:
    return SEC_ARCHIVE_URL.format(
        cik_plain=cik_without_padding(cik),
        accession=accession.replace("-", ""),
        document=document,
    )


def parse_money(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if cleaned in {"", "-", ".", "-."}:
        return None
    try:
        number = float(cleaned)
    except ValueError:
        return None
    return -number if negative and number > 0 else number


def is_monetary_unit(unit: str) -> bool:
    normalized = str(unit or "").strip()
    lower = normalized.lower()
    if not normalized or "share" in lower or "/" in normalized:
        return False
    return bool(re.fullmatch(r"[A-Z]{3}(m|M| millions| Millions)?", normalized))


def flatten_columns(columns: Any) -> list[str]:
    names = []
    for col in columns:
        if isinstance(col, tuple):
            parts = [str(part).strip() for part in col if str(part).strip() and not str(part).startswith("Unnamed")]
            name = " ".join(parts)
        else:
            name = str(col).strip()
        name = re.sub(r"\s+", " ", name.replace("\n", " "))
        names.append(name or "Column")
    deduped: list[str] = []
    seen: dict[str, int] = {}
    for name in names:
        count = seen.get(name, 0)
        seen[name] = count + 1
        deduped.append(f"{name}_{count + 1}" if count else name)
    return deduped


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df.copy()
    cleaned.columns = flatten_columns(cleaned.columns)
    cleaned = cleaned.dropna(how="all").dropna(axis=1, how="all")
    cleaned = cleaned.fillna("")
    for column in cleaned.columns:
        cleaned[column] = cleaned[column].map(lambda value: re.sub(r"\s+", " ", str(value)).strip())
    return cleaned


def dataframe_text(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    pieces = list(df.columns)
    pieces.extend(str(value) for value in df.astype(str).to_numpy().ravel().tolist())
    return " ".join(pieces)


def find_product_matches(text: str, product: str | None) -> list[str]:
    if not product:
        return []
    product_norm = normalize_query(product)
    text_norm = normalize_query(text)
    if product_norm and product_norm in text_norm:
        return [product]
    return []


def score_revenue_table(df: pd.DataFrame, product: str | None = None) -> tuple[int, str]:
    text = dataframe_text(df).lower()
    score = 0
    reasons = []

    product_hits = [keyword for keyword in PRODUCT_TABLE_KEYWORDS if keyword in text]
    revenue_hits = [keyword for keyword in REVENUE_TABLE_KEYWORDS if keyword in text]
    negative_hits = [keyword for keyword in NEGATIVE_TABLE_KEYWORDS if keyword in text]
    year_hits = re.findall(r"\b20\d{2}\b", text)
    moneyish_cells = 0
    for value in df.astype(str).to_numpy().ravel().tolist():
        if parse_money(value) is not None and re.search(r"\d", str(value)):
            moneyish_cells += 1

    if product_hits:
        score += min(len(product_hits), 4) * 4
        reasons.append(f"product terms: {', '.join(product_hits[:4])}")
    if revenue_hits:
        score += min(len(revenue_hits), 4) * 2
        reasons.append(f"revenue terms: {', '.join(revenue_hits[:4])}")
    if year_hits:
        score += min(len(set(year_hits)), 4)
        reasons.append(f"year columns/text: {', '.join(sorted(set(year_hits))[:4])}")
    if moneyish_cells >= 3:
        score += 3
        reasons.append(f"numeric cells: {moneyish_cells}")
    if find_product_matches(text, product):
        score += 10
        reasons.append(f"matched product: {product}")
    if negative_hits:
        score -= min(len(negative_hits), 4) * 3
        reasons.append(f"penalty: {', '.join(negative_hits[:4])}")
    if df.shape[0] < 2 or df.shape[1] < 2:
        score -= 5
        reasons.append("too small")

    return score, "; ".join(reasons) or "low-signal revenue table"


def records_from_dataframe(df: pd.DataFrame, max_rows: int = 40) -> list[dict[str, str]]:
    records = []
    for row in df.head(max_rows).to_dict(orient="records"):
        records.append({str(key): str(value) for key, value in row.items()})
    return records


def extract_candidate_tables(html: str, source_url: str, product: str | None = None, limit: int = 5) -> list[CandidateTable]:
    tables = []
    for flavor in ("lxml", "html5lib"):
        try:
            tables = pd.read_html(StringIO(html), flavor=flavor)
            break
        except (ImportError, ValueError):
            continue
    if not tables:
        return []

    candidates: list[tuple[int, str, pd.DataFrame]] = []
    for table in tables:
        df = clean_dataframe(table)
        score, reason = score_revenue_table(df, product)
        if score >= 6:
            candidates.append((score, reason, df))

    candidates.sort(key=lambda item: item[0], reverse=True)
    output = []
    for rank, (score, reason, df) in enumerate(candidates[:limit], start=1):
        output.append(
            CandidateTable(
                rank=rank,
                score=score,
                rows=int(df.shape[0]),
                columns=int(df.shape[1]),
                reason=reason,
                source_url=source_url,
                evidence_tier="A",
                data=records_from_dataframe(df),
            )
        )
    return output


def format_currency(value: float, unit: str = "USD") -> str:
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.1f}B {unit}"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.1f}M {unit}"
    return f"{value:,.0f} {unit}"


class SecClient:
    def __init__(self, user_agent: str | None = None, timeout: int = 30) -> None:
        self.user_agent = user_agent or os.getenv("SEC_USER_AGENT") or DEFAULT_USER_AGENT
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept": "application/json, text/html, text/plain;q=0.9, */*;q=0.8",
            }
        )

    def get_json(self, url: str) -> dict[str, Any]:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str) -> str:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def resolve_company(self, query: str) -> Company:
        raw = query.strip()
        if not raw:
            raise ValueError("Provide a company name, ticker, or CIK.")
        if re.fullmatch(r"\d{1,10}", raw):
            cik = normalize_cik(raw)
            return Company(query=raw, name=f"CIK {cik}", ticker="", cik=cik, source="user-provided CIK")

        key = normalize_query(raw)
        known = resolve_known_pharma_company(raw)
        if known:
            return known
        ticker = COMPANY_ALIASES.get(key, key)

        ticker_map = self.get_json(SEC_TICKER_URL)
        for item in ticker_map.values():
            if normalize_query(item.get("ticker", "")) == ticker or normalize_query(item.get("title", "")) == key:
                return Company(
                    query=raw,
                    name=item.get("title") or raw,
                    ticker=item.get("ticker") or "",
                    cik=normalize_cik(item.get("cik_str")),
                    source="SEC company_tickers.json",
                )
        raise ValueError(f"Could not resolve company from SEC ticker map: {query}")

    def latest_filing(self, company: Company, forms: tuple[str, ...] = DEFAULT_FORMS, fiscal_year: int | None = None) -> Filing:
        submissions = self.get_json(SEC_SUBMISSIONS_URL.format(cik=company.cik))
        recent = submissions.get("filings", {}).get("recent", {})
        entries = []
        for i, form in enumerate(recent.get("form", [])):
            if form not in forms:
                continue
            report_date = str((recent.get("reportDate") or [""])[i] or "")
            filing_date = str((recent.get("filingDate") or [""])[i] or "")
            fy = report_date[:4] or filing_date[:4]
            if fiscal_year and fy != str(fiscal_year):
                continue
            entries.append(
                {
                    "form": form,
                    "accession": recent.get("accessionNumber", [""])[i],
                    "filed": filing_date,
                    "fiscal_year": fy,
                    "primary_document": recent.get("primaryDocument", [""])[i],
                }
            )
        if not entries:
            target = f" for fiscal year {fiscal_year}" if fiscal_year else ""
            raise ValueError(f"No filing found for {company.name} with forms {', '.join(forms)}{target}.")
        chosen = entries[0]
        url = make_sec_source_url(company.cik, chosen["accession"], chosen["primary_document"])
        return Filing(
            cik=company.cik,
            company_name=company.name,
            ticker=company.ticker,
            form=chosen["form"],
            accession=chosen["accession"],
            filed=chosen["filed"],
            fiscal_year=chosen["fiscal_year"],
            primary_document=chosen["primary_document"],
            source_url=url,
        )

    def fetch_filing_html(self, filing: Filing) -> str:
        return self.get_text(filing.source_url)

    def company_facts(self, company: Company) -> dict[str, Any]:
        return self.get_json(SEC_COMPANY_FACTS_URL.format(cik=company.cik))


def extract_total_revenue_facts(
    facts_payload: dict[str, Any],
    company: Company,
    fiscal_year: int | None = None,
) -> list[RevenueFact]:
    facts = facts_payload.get("facts", {})
    output: list[RevenueFact] = []
    for taxonomy, concepts in facts.items():
        for concept, concept_payload in concepts.items():
            if taxonomy == "us-gaap" and concept not in REVENUE_CONCEPTS:
                continue
            if taxonomy != "us-gaap" and "revenue" not in concept.lower() and "sales" not in concept.lower():
                continue
            units = concept_payload.get("units", {})
            for unit, rows in units.items():
                if not is_monetary_unit(unit):
                    continue
                for row in rows:
                    fy = row.get("fy")
                    if fiscal_year and fy != fiscal_year:
                        continue
                    if row.get("fp") != "FY":
                        continue
                    form = row.get("form") or ""
                    if form not in {"10-K", "20-F"}:
                        continue
                    accession = row.get("accn") or ""
                    source_url = make_sec_source_url(company.cik, accession, "")
                    value = row.get("val")
                    if value is None:
                        continue
                    output.append(
                        RevenueFact(
                            concept=concept,
                            fiscal_year=int(fy),
                            fiscal_period=row.get("fp") or "",
                            value=float(value),
                            unit=unit,
                            form=form,
                            filed=row.get("filed") or "",
                            accession=accession,
                            source_url=source_url.rstrip("/"),
                        )
                    )
    output.sort(key=lambda fact: (fact.fiscal_year, fact.filed, fact.concept), reverse=True)
    deduped = []
    seen = set()
    for fact in output:
        key = (fact.concept, fact.fiscal_year, fact.value, fact.accession)
        if key not in seen:
            seen.add(key)
            deduped.append(fact)
    return deduped[:10]


def run_lookup(
    query: str,
    year: int | None = None,
    product: str | None = None,
    forms: tuple[str, ...] = DEFAULT_FORMS,
    max_tables: int = 5,
    user_agent: str | None = None,
) -> dict[str, Any]:
    client = SecClient(user_agent=user_agent)
    company = client.resolve_company(query)
    filing = client.latest_filing(company, forms=forms, fiscal_year=year)
    html = client.fetch_filing_html(filing)
    table_product = product or None
    tables = extract_candidate_tables(html, filing.source_url, product=table_product, limit=max_tables)

    facts = []
    try:
        facts_payload = client.company_facts(company)
        facts = extract_total_revenue_facts(facts_payload, company, fiscal_year=year)
    except Exception as exc:
        facts = []
        facts_error = f"{type(exc).__name__}: {exc}"
    else:
        facts_error = ""

    return {
        "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "company": asdict(company),
        "filing": asdict(filing),
        "source_policy": {
            "primary_source": "SEC EDGAR filing and SEC XBRL Company Facts API",
            "evidence_tier": "A",
            "review_note": "Use candidate product tables as official disclosed tables; manually confirm row labels and footnotes in the source filing.",
        },
        "total_revenue_facts": [asdict(fact) for fact in facts],
        "total_revenue_facts_error": facts_error,
        "candidate_product_revenue_tables": [asdict(table) for table in tables],
    }


def render_sources_markdown() -> str:
    lines = ["# Official Revenue Source Registry", ""]
    for source in SOURCE_REGISTRY:
        lines.extend(
            [
                f"## {source['name']}",
                "",
                f"- Evidence tier: {source['evidence_tier']}",
                f"- URL: {source['url']}",
                f"- Coverage: {source['coverage']}",
                f"- Best for: {source['best_for']}",
                f"- Limitation: {source['limitation']}",
                "",
            ]
        )
    return "\n".join(lines)


def render_lookup_markdown(result: dict[str, Any]) -> str:
    company = result["company"]
    filing = result["filing"]
    lines = [
        "# Official Revenue Lookup",
        "",
        f"Generated: {result['generated_at']}",
        f"Company: {company['name']} ({company.get('ticker') or 'no ticker'}, CIK {company['cik']})",
        f"Filing: {filing['form']} filed {filing['filed']} for FY {filing['fiscal_year']}",
        f"Accession: {filing['accession']}",
        f"Source: {filing['source_url']}",
        f"Evidence tier: {result['source_policy']['evidence_tier']}",
        "",
        "## Total Revenue Facts",
        "",
    ]
    facts = result.get("total_revenue_facts", [])
    if facts:
        for fact in facts[:5]:
            lines.append(
                f"- FY {fact['fiscal_year']} {fact['concept']}: {format_currency(fact['value'], fact['unit'])} "
                f"({fact['form']}, filed {fact['filed']}, accession {fact['accession']})"
            )
    else:
        error = result.get("total_revenue_facts_error")
        lines.append(f"- No structured total revenue fact extracted.{f' Error: {error}' if error else ''}")

    lines.extend(["", "## Candidate Product / Revenue Tables", ""])
    tables = result.get("candidate_product_revenue_tables", [])
    if not tables:
        lines.append("- No candidate product revenue table found by the automated screen.")
    for table in tables:
        lines.extend(
            [
                f"### Table {table['rank']} - score {table['score']}",
                "",
                f"Reason: {table['reason']}",
                f"Rows/columns: {table['rows']} x {table['columns']}",
                f"Source: {table['source_url']}",
                "",
            ]
        )
        data = table["data"]
        if data:
            columns = list(data[0].keys())
            lines.append("| " + " | ".join(columns) + " |")
            lines.append("| " + " | ".join("---" for _ in columns) + " |")
            for row in data[:12]:
                lines.append("| " + " | ".join(str(row.get(col, "")).replace("|", "/") for col in columns) + " |")
            lines.append("")

    lines.extend(
        [
            "## Review Notes",
            "",
            "- Treat SEC/company annual reports as the primary evidence for reported sales.",
            "- Treat automated table extraction as a screen; confirm the source table title, row label, units, and footnotes before final use.",
            "- Product sales are not the same as indication-level market sales when a product has multiple indications.",
            "",
        ]
    )
    return "\n".join(lines)


def save_result(result: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    company = result["company"].get("ticker") or result["company"]["cik"]
    fiscal_year = result["filing"].get("fiscal_year") or "latest"
    stem = f"{company.lower()}-revenue-{fiscal_year}"

    (output_dir / f"{stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output_dir / f"{stem}.md").write_text(render_lookup_markdown(result), encoding="utf-8")

    for table in result.get("candidate_product_revenue_tables", []):
        data = table.get("data") or []
        if not data:
            continue
        path = output_dir / f"{stem}-table-{table['rank']}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0].keys()))
            writer.writeheader()
            writer.writerows(data)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify pharma revenue from official filings and source databases.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    sources = subparsers.add_parser("sources", help="List vetted official data sources.")
    sources.add_argument("--json", action="store_true", help="Print source registry as JSON.")

    lookup = subparsers.add_parser("lookup", help="Lookup official revenue evidence for a company.")
    lookup.add_argument("company", help="Company name, ticker, or CIK. Examples: LLY, Pfizer, 0000078003")
    lookup.add_argument("--year", type=int, help="Fiscal year to retrieve, for example 2025.")
    lookup.add_argument("--product", help="Optional product name to prioritize in product revenue tables.")
    lookup.add_argument("--form", action="append", choices=["10-K", "20-F", "10-Q", "6-K"], help="SEC form type. Repeatable.")
    lookup.add_argument("--max-tables", type=int, default=5, help="Maximum candidate tables to return.")
    lookup.add_argument("--save-dir", type=Path, help="Save JSON, Markdown, and CSV table extracts to this directory.")
    lookup.add_argument("--json", action="store_true", help="Print lookup result as JSON instead of Markdown.")
    lookup.add_argument("--sec-user-agent", help="SEC-compliant User-Agent with contact email. Can also set SEC_USER_AGENT.")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.command == "sources":
        if args.json:
            print(json.dumps(SOURCE_REGISTRY, indent=2))
        else:
            print(render_sources_markdown())
        return 0

    if args.command == "lookup":
        forms = tuple(args.form) if args.form else DEFAULT_FORMS
        result = run_lookup(
            args.company,
            year=args.year,
            product=args.product,
            forms=forms,
            max_tables=args.max_tables,
            user_agent=args.sec_user_agent,
        )
        if args.save_dir:
            save_result(result, args.save_dir)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(render_lookup_markdown(result))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
