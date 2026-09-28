"""Deterministic regression fixtures; amounts are synthetic test values."""

import unittest
from unittest.mock import patch

import pandas as pd
import requests

from nora_data import (
    COMPANY_REGISTRY,
    RevenueDataError,
    build_comparison,
    extract_annual_revenue,
    fetch_company_revenue,
    search_companies,
)


CONCEPT = "RevenueFromContractWithCustomerExcludingAssessedTax"
A2023 = "0000078003-24-000001"
A2024 = "0000078003-25-000001"
A2025 = "0000078003-26-000001"


def observation(start="2023-01-01", end="2023-12-31", val=100, *, accn=A2023, filed="2024-02-01", fy=2023, **extra):
    return dict(start=start, end=end, val=val, accn=accn, filed=filed, fy=fy, fp="FY", form="10-K", **extra)


def payload(observations, *, taxonomy="us-gaap", concept=CONCEPT, currency="USD", cik=78003):
    return {"cik": cik, "entityName": "Fixture company", "facts": {taxonomy: {concept: {"units": {currency: observations}}}}}


def comparison_record(year, amount=100, **changes):
    return dict({
        "ticker": "PFE", "company": "Pfizer Inc.", "fiscal_year": year,
        "period_start": f"{year}-01-01", "period_end": f"{year}-12-31",
        "revenue": amount, "currency": "USD", "concept": CONCEPT,
        "taxonomy": "us-gaap", "filed": "2026-02-01", "accession": A2025,
        "source_url": "https://www.sec.gov/Archives/edgar/data/78003/fixture.htm",
        "year_basis": "issuer_calendar_year", "source_kind": "SEC Company Facts",
    }, **changes)


class CompanySearchTests(unittest.TestCase):
    def test_korean_english_aliases_and_case(self):
        for query in ("화이자", "pfizer", " pFe ", "78003", "0000078003"):
            with self.subTest(query=query):
                self.assertEqual(search_companies(query)[0]["ticker"], "PFE")
        self.assertEqual(search_companies("노보 노디스크")[0]["ticker"], "NVO")
        self.assertEqual(search_companies("Glaxo Smith Kline")[0]["ticker"], "GSK")
        self.assertEqual(search_companies("일라이 릴리")[0]["ticker"], "LLY")

    def test_no_arbitrary_ambiguous_resolution(self):
        self.assertGreater(len(search_companies("pharma")), 1)
        self.assertEqual(search_companies("P"), [])
        self.assertEqual(search_companies("unrecognized company"), [])
        with self.assertRaises(ValueError):
            fetch_company_revenue("pharma")

    def test_results_do_not_mutate_registry(self):
        result = search_companies("PFE")[0]
        result["aliases"].append("new alias")
        self.assertNotIn("new alias", COMPANY_REGISTRY["PFE"]["aliases"])


class AnnualExtractionTests(unittest.TestCase):
    def test_quarter_in_annual_filing_and_instant_facts_excluded(self):
        annual = observation(val=100)
        quarter = observation("2023-10-01", "2023-12-31", 30)
        instant = observation(val=200)
        instant.pop("start")
        short_transition = observation("2023-07-01", "2023-12-31", 60)
        long_transition = observation("2022-10-01", "2023-12-31", 150)
        rows = extract_annual_revenue(payload([annual, quarter, instant, short_transition, long_transition]), COMPANY_REGISTRY["PFE"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revenue"], 100)

    def test_comparative_year_uses_dates_not_filing_fy(self):
        rows = [observation(val=100, fy=2024, filed="2025-02-01", accn=A2024), observation("2024-01-01", "2024-12-31", 110, fy=2024, filed="2025-02-01", accn=A2024)]
        extracted = extract_annual_revenue(payload(rows), COMPANY_REGISTRY["PFE"])
        self.assertEqual([row["fiscal_year"] for row in extracted], [2023, 2024])
        self.assertEqual([row["revenue"] for row in extracted], [100, 110])
        self.assertAlmostEqual(build_comparison(extracted).iloc[-1]["yoy_pct"], 10)

    def test_latest_restatement_retains_old_values_and_direct_source(self):
        rows = [observation(val=100), observation(val=90, accn=A2024, filed="2025-02-01", fy=2024)]
        submissions = {"filings": {"recent": {"accessionNumber": [A2024], "reportDate": ["2024-12-31"], "primaryDocument": ["annual2024.htm"]}}}
        extracted = extract_annual_revenue(payload(rows), COMPANY_REGISTRY["PFE"], submissions)
        self.assertEqual(extracted[0]["revenue"], 90)
        self.assertEqual(extracted[0]["fiscal_year"], 2023)
        self.assertTrue(extracted[0]["has_revisions"])
        self.assertEqual(len(extracted[0]["observed_versions"]), 2)
        self.assertTrue(extracted[0]["source_url"].endswith("/annual2024.htm"))

    def test_consolidated_allowlist_excludes_custom_and_product_tags(self):
        data = payload([observation()])
        data["facts"]["us-gaap"]["ProductRevenue"] = {"units": {"USD": [observation(val=50)]}}
        data["facts"]["pfe"] = {"TotalSalesLikeName": {"units": {"USD": [observation(val=999)]}}}
        rows = extract_annual_revenue(data, COMPANY_REGISTRY["PFE"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["concept"], CONCEPT)
        self.assertEqual(rows[0]["revenue"], 100)

    def test_same_filing_conflicting_values_are_not_guessed(self):
        rows = extract_annual_revenue(payload([observation(val=100), observation(val=101)]), COMPANY_REGISTRY["PFE"])
        self.assertEqual(rows, [])

    def test_preferred_consolidated_concept_breaks_same_filing_tie(self):
        data = payload([observation()])
        data["facts"]["us-gaap"]["Revenues"] = {"units": {"USD": [observation(val=101)]}}
        rows = extract_annual_revenue(data, COMPANY_REGISTRY["PFE"])
        self.assertEqual(rows[0]["concept"], CONCEPT)
        self.assertEqual(rows[0]["revenue"], 100)

    def test_foreign_reporting_currency_and_takeda_start_year(self):
        annual = observation("2024-04-01", "2025-03-31", 4_000_000_000_000, accn="0001395064-25-000100", filed="2025-06-25", fy=2025)
        annual["form"] = "20-F"
        data = payload([annual], taxonomy="ifrs-full", concept="Revenue", currency="JPY", cik=1395064)
        data["facts"]["ifrs-full"]["Revenue"]["units"]["USD"] = [{**annual, "val": 25_000_000_000}]
        rows = extract_annual_revenue(data, COMPANY_REGISTRY["TAK"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fiscal_year"], 2024)
        self.assertEqual(rows[0]["currency"], "JPY")
        self.assertEqual(rows[0]["year_basis"], "issuer_start_year")
        self.assertEqual(rows[0]["revenue"], 4_000_000_000_000)

    def test_december_52_week_year_ending_january_not_mislabeled(self):
        data = payload([observation("2022-01-03", "2023-01-01", fy=2022, filed="2023-02-10")], cik=200406)
        rows = extract_annual_revenue(data, COMPANY_REGISTRY["JNJ"])
        self.assertEqual(rows[0]["fiscal_year"], 2022)

    def test_unknown_issuer_has_explicit_derived_year(self):
        unknown = {"ticker": "FIX", "name": "Fixture", "cik": "123"}
        data = payload([observation("2023-07-01", "2024-06-30", filed="2024-08-01")], cik=123)
        row = extract_annual_revenue(data, unknown)[0]
        self.assertEqual(row["fiscal_year"], 2024)
        self.assertEqual(row["year_basis"], "derived_period_end_year")
        data["facts"]["us-gaap"][CONCEPT]["units"]["EUR"] = data["facts"]["us-gaap"][CONCEPT]["units"]["USD"]
        self.assertEqual(extract_annual_revenue(data, unknown), [])

    def test_identity_mismatch_rejected(self):
        with self.assertRaises(RevenueDataError):
            extract_annual_revenue(payload([observation()], cik=1395064), COMPANY_REGISTRY["PFE"])

    def test_invalid_numeric_values_do_not_create_revenue(self):
        for value in (True, "100", float("nan"), float("inf"), None):
            with self.subTest(value=value):
                self.assertEqual(extract_annual_revenue(payload([observation(val=value)]), COMPANY_REGISTRY["PFE"]), [])


class ComparisonTests(unittest.TestCase):
    def test_snapshot_rows_need_no_internal_metadata(self):
        rows = [comparison_record(2023, 100, taxonomy="official-report", concept="Revenue", source_kind="official_report_snapshot"), comparison_record(2024, 110, taxonomy="official-report", concept="Revenue", source_kind="official_report_snapshot")]
        result = build_comparison(rows)
        self.assertAlmostEqual(result.iloc[1]["yoy_pct"], 10)
        self.assertEqual(result.iloc[1]["comparability_note"], "same_filing_comparative")

    def test_missing_year_does_not_produce_multiyear_yoy(self):
        result = build_comparison([comparison_record(2022), comparison_record(2024, 150)])
        self.assertTrue(pd.isna(result.iloc[-1]["yoy_pct"]))
        self.assertEqual(result.iloc[-1]["comparability_note"], "nonconsecutive_periods")

    def test_currency_or_concept_change_suppresses_growth(self):
        for changes in ({"currency": "EUR"}, {"concept": "Revenues"}, {"taxonomy": "ifrs-full"}):
            with self.subTest(changes=changes):
                result = build_comparison([comparison_record(2023), comparison_record(2024, 200, **changes)])
                self.assertTrue(pd.isna(result.iloc[-1]["yoy_pct"]))
                self.assertEqual(result.iloc[-1]["comparability_note"], "currency_or_concept_changed")

    def test_zero_or_negative_base_suppresses_growth(self):
        for base in (0, -100):
            result = build_comparison([comparison_record(2023, base), comparison_record(2024, 110)])
            self.assertTrue(pd.isna(result.iloc[-1]["yoy_pct"]))

    def test_unique_period_uses_latest_and_does_not_mutate_inputs(self):
        old = comparison_record(2023, 100, accession=A2023, filed="2024-02-01")
        new = comparison_record(2023, 90, accession=A2024, filed="2025-02-01")
        result = build_comparison([old, new])
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["revenue"], 90)
        self.assertNotIn("observed_versions", new)

    def test_same_filing_comparative_avoids_spurious_growth(self):
        original_prior = comparison_record(2023, 100, accession=A2024, filed="2025-02-01")
        latest_prior = comparison_record(2023, 80, accession=A2025, observed_versions=[original_prior], has_revisions=True)
        current = comparison_record(2024, 110, accession=A2024, filed="2025-02-01")
        result = build_comparison([latest_prior, current])
        # The current report compares 110 against 100, not a later 80 restatement.
        self.assertAlmostEqual(result.iloc[-1]["yoy_pct"], 10)
        self.assertEqual(result.iloc[-1]["yoy_prior_revenue"], 100)
        self.assertEqual(result.iloc[-1]["yoy_prior_accession"], A2024)

    def test_incompatible_restatement_bases_suppress_growth(self):
        prior = comparison_record(2023, 80, accession=A2025, has_revisions=True)
        current = comparison_record(2024, 110, accession=A2024, filed="2025-02-01")
        result = build_comparison([prior, current])
        self.assertTrue(pd.isna(result.iloc[-1]["yoy_pct"]))
        self.assertEqual(result.iloc[-1]["comparability_note"], "incompatible_restatement_basis")

    def test_empty_result_has_ui_columns(self):
        result = build_comparison([])
        self.assertTrue(result.empty)
        self.assertIn("yoy_pct", result.columns)
        self.assertIn("revenue_billions", result.columns)


class FetchTests(unittest.TestCase):
    @patch("nora_data.SecClient")
    def test_fetch_failure_is_explicit_no_sample_substitution(self, client_class):
        response = requests.Response()
        response.status_code = 403
        client_class.return_value.company_facts.side_effect = requests.HTTPError(response=response)
        with self.assertRaisesRegex(RevenueDataError, "403"):
            fetch_company_revenue("PFE")

    @patch("nora_data.SecClient")
    def test_submissions_failure_retains_facts_with_warning(self, client_class):
        client = client_class.return_value
        client.company_facts.return_value = payload([observation()])
        client.get_json.side_effect = requests.Timeout()
        rows = fetch_company_revenue("PFE")
        self.assertEqual(len(rows), 1)
        self.assertIn("metadata_warning", rows[0])
        self.assertTrue(rows[0]["source_url"].endswith("-index.html"))


if __name__ == "__main__":
    unittest.main()
