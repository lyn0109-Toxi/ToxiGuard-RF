import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app
from streamlit.testing.v1 import AppTest


def rf_test_ui():
    import app
    from rf_ui import render
    render(app)


class ForecastRegressionTests(unittest.TestCase):
    def setUp(self):
        self.x = app.ForecastInput(
            **app.SCENARIOS['Custom project'], source_type='SEC',
            evidence_url='https://example.invalid', filing_date='2026',
            accession='fake', reviewer_note='unverified', currency_label='USD',
        )

    def test_access_zero(self):
        forecast = app.calculate_forecast(replace(self.x, payer_access=0))
        self.assertTrue((forecast[['Market Model', 'Patient Model', 'Triangulated Forecast']] == 0).all().all())

    def test_launch_clock(self):
        early = app.calculate_forecast(self.x, 2026)
        late = app.calculate_forecast(self.x, 2028)
        self.assertEqual(early.iloc[0]['Adjusted Share'], late.iloc[2]['Adjusted Share'])
        self.assertTrue((late.iloc[:2]['Triangulated Forecast'] == 0).all())

    def test_initial_share(self):
        self.assertAlmostEqual(app.calculate_forecast(self.x).iloc[0]['Adjusted Share'], .008)

    def test_company_scope(self):
        with self.assertRaises(ValueError):
            app.calculate_forecast(replace(self.x, revenue_scope='Company total'))

    def test_invalid_growth(self):
        with self.assertRaises(ValueError):
            app.calculate_forecast(replace(self.x, market_cagr=-101))

    def test_no_false_verification(self):
        pipeline = app.PipelineInput('asset', 'ind', 'Phase 2', 2028, 15, 65, 100, '', '', '', '')
        forecast = app.calculate_forecast(self.x, 2028)
        score, note = app.calculate_confidence(self.x, True)
        checks = app.validation_checks(self.x, pipeline, forecast, app.calculate_pipeline(self.x, pipeline, forecast), score)
        self.assertTrue((checks[checks['Group'] == 'Evidence']['Status'] != 'Pass').all())
        self.assertIn('Not a probability', note)

    def test_all_templates(self):
        for defaults in app.SCENARIOS.values():
            forecast = app.calculate_forecast(replace(self.x, **defaults), 2028)
            self.assertEqual(len(forecast), 8)
            self.assertTrue((forecast['Triangulated Forecast'] >= 0).all())


class RevenueLookupRegressionTests(unittest.TestCase):
    def setUp(self):
        app.sec_lookup_cached.clear()
        self.row = {
            'ticker': 'LLY', 'company': 'Eli Lilly and Company', 'fiscal_year': 2025,
            'revenue': 1234000000, 'currency': 'USD', 'filed': '2026-02-12',
            'concept': 'RevenueFromContractWithCustomerExcludingAssessedTax',
            'source_url': 'https://www.sec.gov/example', 'accession': 'example-accession',
            'period_start': '2025-01-01', 'period_end': '2025-12-31',
        }

    def tearDown(self):
        app.sec_lookup_cached.clear()

    def test_reference_year_is_required_to_match(self):
        with patch.object(app, 'sec_lookup_cached') as live:
            result = app.lookup_company_anchor('LLY', 2025, live=False)
            self.assertEqual(result['fiscal_year'], 2025)
            with self.assertRaisesRegex(ValueError, 'FY 2024'):
                app.lookup_company_anchor('LLY', 2024, live=False)
            with self.assertRaises(ValueError):
                app.lookup_company_anchor('unknown company', 2025, live=False)
            live.assert_not_called()

    def test_live_failure_does_not_return_builtin_reference(self):
        with patch.object(app, 'sec_lookup_cached', side_effect=RuntimeError('SEC unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'SEC unavailable'):
                app.lookup_company_anchor('LLY', 2025, live=True)

    def test_live_lookup_selects_exact_fiscal_year_and_preserves_period(self):
        data = SimpleNamespace(
            search_companies=Mock(return_value=[{'ticker': 'LLY'}]),
            fetch_company_revenue=Mock(return_value=[dict(self.row, fiscal_year=2024, revenue=999), self.row]),
        )
        with patch.dict('sys.modules', {'nora_data': data}):
            anchor = app.sec_lookup_cached('LLY', 2025, None)
        self.assertEqual(anchor['value_millions'], 1234)
        self.assertEqual(anchor['fiscal_year'], 2025)
        self.assertEqual(anchor['period_start'], '2025-01-01')
        self.assertEqual(anchor['period_end'], '2025-12-31')
        self.assertEqual(anchor['accession'], 'example-accession')
        data.fetch_company_revenue.assert_called_once_with('LLY')

    def test_unavailable_live_year_is_not_substituted(self):
        data = SimpleNamespace(
            search_companies=Mock(return_value=[{'ticker': 'LLY'}]),
            fetch_company_revenue=Mock(return_value=[self.row]),
        )
        with patch.dict('sys.modules', {'nora_data': data}):
            with self.assertRaisesRegex(ValueError, 'FY 2024'):
                app.sec_lookup_cached('LLY', 2024, None)

    def test_ambiguous_company_does_not_fetch_arbitrary_match(self):
        data = SimpleNamespace(
            search_companies=Mock(return_value=[{'ticker': 'LLY'}, {'ticker': 'MRK'}]),
            fetch_company_revenue=Mock(),
        )
        with patch.dict('sys.modules', {'nora_data': data}):
            with self.assertRaises(ValueError):
                app.sec_lookup_cached('pharma', 2025, None)
        data.fetch_company_revenue.assert_not_called()

    def test_anchor_keeps_non_usd_currency(self):
        anchor = dict(app.VERIFIED_REVENUE_ANCHORS['GSK'], unit='EUR millions')
        state = {}
        with patch.object(app.st, 'session_state', state):
            app.apply_anchor_to_session(anchor)
        self.assertEqual(state['currency_label'], 'EUR')
        self.assertEqual(state['revenue_scope'], 'Company total')

    def test_novo_nordisk_live_anchor_keeps_danish_krone_in_ui(self):
        anchor = dict(app.VERIFIED_REVENUE_ANCHORS['GSK'],
                      ticker='NVO', name='Novo Nordisk A/S', unit='DKK millions')
        at = AppTest.from_function(rf_test_ui).run()
        at.text_input(key='lookup_query').set_value('NVO')
        at.radio(key='rf_lookup_mode').set_value('Live SEC lookup')
        with patch.object(app, 'sec_lookup_cached', return_value=anchor):
            next(button for button in at.button if button.label == 'Lookup revenue evidence').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.selectbox(key='currency_label').value, 'DKK')
        self.assertEqual(at.session_state['company'], 'Novo Nordisk A/S')
        self.assertEqual(at.session_state['revenue_scope'], 'Company total')
        self.assertTrue(any(metric.value.startswith('DKK ') for metric in at.metric))


class ScenarioStateRegressionTests(unittest.TestCase):
    def test_explicit_load_resets_provenance_pipeline_and_lookup(self):
        defaults = app.SCENARIOS['Rare disease premium therapy']
        state = {key: 'stale' for key in app.scenario_session_defaults(defaults)}
        state.update({
            'latest_anchor': {'company': 'Previous company'}, 'pending_anchor': {'company': 'Previous company'},
            'lookup_matched': True, 'lookup_query': 'GSK', 'lookup_year': 2024,
            'rf_lookup_notice': {'kind': 'success'}, 'rf_lang': 'ko', 'nora_selected': ['LLY'],
        })
        with patch.object(app.st, 'session_state', state):
            app.load_scenario('Rare disease premium therapy')
        for key, value in app.scenario_session_defaults(defaults).items():
            self.assertEqual(state[key], value, key)
        for key in ['latest_anchor', 'pending_anchor', 'lookup_query', 'lookup_year', 'rf_lookup_notice']:
            self.assertNotIn(key, state)
        self.assertFalse(state['lookup_matched'])
        self.assertEqual(state['rf_lang'], 'ko')
        self.assertEqual(state['nora_selected'], ['LLY'])

    def test_initialization_preserves_user_inputs(self):
        state = {'reported_sales': 2345, 'evidence_url': 'https://example.invalid/report', 'currency_label': 'EUR'}
        with patch.object(app.st, 'session_state', state):
            app.ensure_session_defaults(app.SCENARIOS['Custom project'])
        self.assertEqual(state['reported_sales'], 2345)
        self.assertEqual(state['evidence_url'], 'https://example.invalid/report')
        self.assertEqual(state['currency_label'], 'EUR')

    def test_ui_reference_then_load_restores_working_scenario(self):
        at = AppTest.from_function(rf_test_ui).run()
        self.assertEqual(len(at.exception), 0)
        at.text_input(key='lookup_query').set_value('GSK')
        next(button for button in at.button if button.label == 'Lookup revenue evidence').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state['currency_label'], 'GBP')
        self.assertEqual(at.session_state['revenue_scope'], 'Company total')
        self.assertGreater(len(at.error), 0)
        at.selectbox(key='rf_scenario_template').select('Rare disease premium therapy').run()
        self.assertEqual(at.session_state['company'], 'GSK plc')
        next(button for button in at.button if button.label == 'Load scenario').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.error), 0)
        self.assertEqual(at.session_state['currency_label'], 'USD')
        self.assertEqual(at.session_state['revenue_scope'], 'Illustrative assumption')
        self.assertEqual(at.session_state['reported_sales'], 420)
        self.assertEqual(at.session_state['pipeline_asset'], 'TG-Rare')
        self.assertEqual(at.session_state['evidence_url'], '')
        self.assertEqual(at.session_state['accession'], 'manual-review-needed')

    def test_ui_live_failure_preserves_inputs_and_reports_failure(self):
        at = AppTest.from_function(rf_test_ui).run()
        keys = ['company', 'reported_sales', 'anchor_year', 'currency_label', 'evidence_url', 'revenue_scope']
        previous = {key: at.session_state[key] for key in keys}
        at.text_input(key='lookup_query').set_value('LLY')
        at.radio(key='rf_lookup_mode').set_value('Live SEC lookup')
        with patch.object(app, 'sec_lookup_cached', side_effect=RuntimeError('SEC unavailable')):
            next(button for button in at.button if button.label == 'Lookup revenue evidence').click().run()
        self.assertEqual(len(at.exception), 0)
        self.assertEqual({key: at.session_state[key] for key in keys}, previous)
        self.assertTrue(any('SEC unavailable' in error.value for error in at.error))
        self.assertFalse(at.session_state['lookup_matched'])


if __name__ == '__main__':
    unittest.main()
