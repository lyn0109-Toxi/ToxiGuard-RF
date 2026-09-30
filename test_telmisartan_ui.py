"""Case routing, units, persistent edits and explicit VCC handoff regressions."""
import copy
import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pandas as pd
from pandas.api.types import is_float_dtype
from streamlit.delta_generator import DeltaGenerator
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest

from telmisartan_case import build_handoff, compare_strategies, load_case, validate_handoff
from telmisartan_ui import FIELDS, reported_revenue_figure, vcc_case_url


class TelmisartanInteractionTests(unittest.TestCase):
    def app(self, **query):
        app = AppTest.from_file('streamlit_app.py', default_timeout=15)
        app.query_params.update(query)
        app.run()
        self.assertEqual(list(app.exception), [])
        return app

    def case_app(self):
        return self.app(case='telmisartan')

    def summary(self, app, language='ko'):
        column = '지표 / 단위' if language == 'ko' else 'Metric / unit'
        table = next(table.value for table in app.dataframe if column in table.value.columns)
        return table.set_index(column).apply(lambda values: pd.to_numeric(values.str.replace(',', '', regex=False)))

    def peak(self, app, language='ko'):
        metric = '기간 내 최대 매출 (억원)' if language == 'ko' else 'Peak revenue (KRW 100 million)'
        return self.summary(app, language).loc[metric].iloc[0]

    def edit(self, app, edits):
        """Send the actual data-editor frontend delta through Streamlit's runner.

        AppTest has no public DataEditor.set_value method. WidgetStates is the
        same message used by ElementTree.run; no callback or model is mocked.
        """
        editor = next(table for table in app.dataframe if 'field' in table.value)
        states = WidgetStates()
        for widget in app._tree.get_widget_states().widgets:
            if widget.id != editor.proto.id:
                states.widgets.add().CopyFrom(widget)
        value = states.widgets.add()
        value.id = editor.proto.id
        value.string_value = json.dumps({'edited_rows': edits, 'added_rows': [], 'deleted_rows': []})
        app._run(states)
        self.assertEqual(list(app.exception), [])
        return next(table for table in app.dataframe if 'field' in table.value).proto.id

    def test_case_deep_link_initializes_once_without_overriding_manual_navigation(self):
        app = self.app(case='telmisartan', strategy='dual')
        self.assertEqual(app.radio(key='nora_mode').value, 'telmisartan')
        self.assertEqual(app.selectbox(key='tel_case_strategy').value, 'dual')
        app.radio(key='nora_mode').set_value('companies').run()
        self.assertEqual(app.radio(key='nora_mode').value, 'companies')
        self.assertTrue(app.multiselect(key='nora_selected'))
        self.assertEqual(list(app.exception), [])

    def test_case_amounts_use_hundred_million_and_match_shared_model(self):
        downloads = {}
        original_download = DeltaGenerator.download_button
        def capture_download(generator, *args, **kwargs):
            if kwargs.get('key') in {'tel_case_annual_csv', 'tel_case_summary_csv'}:
                downloads[kwargs['key']] = args[1] if len(args) > 1 else kwargs['data']
            return original_download(generator, *args, **kwargs)
        with patch.object(DeltaGenerator, 'download_button', autospec=True, side_effect=capture_download):
            app = self.case_app()
        editor = next(table.value for table in app.dataframe if 'field' in table.value)
        self.assertTrue(all(is_float_dtype(editor[item['id']]) for item in load_case()['strategies']))
        comparison = compare_strategies()
        expected = comparison['summary']
        actual = self.summary(app)
        names = {item['id']: item['label_ko'] for item in load_case()['strategies']}
        self.assertEqual(actual.shape, (7, 3))  # Plus the visible metric column: four columns total.
        self.assertEqual(list(actual.columns), list(names.values()))
        metrics = {
            '기간 내 최대 매출 (억원)': 'peak_revenue_krw_m',
            '목표점유율 매출 (억원)': 'mature_revenue_at_base_population_krw_m',
            '위험조정 최대 매출 (억원)': 'peak_risk_adjusted_krw_m',
            '누적 위험조정 매출 (억원)': 'total_risk_adjusted_krw_m',
            '개발비 (억원)': 'development_cost_krw_m',
            '개발비 차감 후 기여액 (억원)': 'net_contribution_krw_m',
        }
        for row in expected:
            self.assertEqual(actual.loc['출시 연도 (년)', names[row['strategy_id']]], row['launch_year'])
            for metric, field in metrics.items():
                self.assertAlmostEqual(actual.loc[metric, names[row['strategy_id']]], round(row[field] / 100, 2))
        for key, source in [('tel_case_annual_csv', 'annual'), ('tel_case_summary_csv', 'summary')]:
            exported = pd.read_csv(io.BytesIO(downloads[key]))
            pd.testing.assert_frame_equal(exported, pd.DataFrame(comparison[source]), check_dtype=False)
        annual = next(table.value for table in app.dataframe if '매출 (억원)' in table.value)
        self.assertEqual(len(annual), load_case()['horizon'] * len(expected))
        self.assertFalse(any(str(column).endswith('_krw_m') for column in annual.columns))

    def test_sequential_frontend_edits_revert_and_survive_language_and_workspace(self):
        app = self.case_app()
        original = self.peak(app)
        values = copy.deepcopy(app.session_state.tel_case_assumptions)
        row = next(index for index, field in enumerate(FIELDS) if field[0] == 'annual_net_price_krw')
        edited_price = values['generic']['annual_net_price_krw'] * 1.5
        edits = {str(row): {'generic': edited_price}}
        initial_id = next(table for table in app.dataframe if 'field' in table.value).proto.id
        self.assertEqual(self.edit(app, edits), initial_id)
        peak_row = str(next(index for index, field in enumerate(FIELDS) if field[0] == 'peak_share_pct'))
        edits[peak_row] = {'generic': 10.25}
        self.assertEqual(self.edit(app, edits), initial_id)
        self.assertEqual(app.session_state.tel_case_assumptions['generic']['annual_net_price_krw'], edited_price)
        self.assertEqual(app.session_state.tel_case_assumptions['generic']['peak_share_pct'], 10.25)
        # The frontend removes the patch when a value returns to its baseline.
        del edits[peak_row]
        self.assertEqual(self.edit(app, edits), initial_id)
        self.assertEqual(app.session_state.tel_case_assumptions['generic']['peak_share_pct'], values['generic']['peak_share_pct'])
        self.assertAlmostEqual(self.peak(app), round(original * 1.5, 2), places=1)
        app.radio(key='rf_lang').set_value('en').run()
        self.assertAlmostEqual(self.peak(app, 'en'), round(original * 1.5, 2), places=1)
        app.radio(key='nora_mode').set_value('companies').run()
        app.radio(key='nora_mode').set_value('telmisartan').run()
        self.assertEqual(app.session_state.tel_case_assumptions['generic']['annual_net_price_krw'], edited_price)
        self.assertAlmostEqual(self.peak(app, 'en'), round(original * 1.5, 2), places=1)
        self.assertEqual(list(app.exception), [])

    def test_invalid_inputs_block_exports_and_reset_recovers(self):
        app = self.case_app()
        row = str(next(index for index, field in enumerate(FIELDS) if field[0] == 'success_pct'))
        self.edit(app, {row: {'generic': 101}})
        self.assertTrue(app.error)
        self.assertEqual(len(app.get('download_button')), 0)
        app.button(key='tel_case_reset').click().run()
        self.assertEqual(list(app.error), [])
        self.assertEqual(len(app.get('download_button')), 3)
        self.assertEqual(app.session_state.tel_case_assumptions['generic'], load_case()['strategies'][0]['assumptions'])
        self.assertEqual(list(app.exception), [])

    def test_vcc_handoff_uses_current_selected_assumptions_and_explicit_default_link(self):
        app = self.case_app()
        row = str(next(index for index, field in enumerate(FIELDS) if field[0] == 'eligible_patients'))
        self.edit(app, {row: {'dual': 123456}})
        with patch('telmisartan_ui.build_handoff', wraps=build_handoff) as export:
            app.selectbox(key='tel_case_strategy').set_value('dual').run()
        selected, assumptions = export.call_args.args
        self.assertEqual(selected, 'dual')
        self.assertEqual(assumptions['eligible_patients'], 123456)
        payload = validate_handoff(build_handoff(selected, assumptions))
        self.assertEqual(payload['assumptions']['eligible_patients'], 123456)
        links = [item.proto for item in app.get('link_button') if 'VCC' in item.proto.label]
        self.assertEqual(len(links), 1)
        self.assertIn('기본가정', links[0].label)
        self.assertEqual(parse_qs(urlsplit(links[0].url).query)['strategy'], ['dual'])
        self.assertTrue(any('자동 전송되지 않습니다' in item.value for item in app.info))

    def test_actual_revenue_chart_uses_three_reported_years_and_excludes_missing_amounts(self):
        records = load_case()['revenue_evidence']
        figure = reported_revenue_figure(records)
        trace = next(trace for trace in figure.data if '트윈스타' in trace.name)
        self.assertEqual(list(trace.x), [2023, 2024, 2025])
        self.assertEqual(list(trace.y), [816.21, 923.72, 891.11])
        reported = [row for row in records if row.get('amount_krw_m') is not None]
        self.assertEqual(sum(len(trace.y) for trace in figure.data), len(reported))
        self.assertEqual({trace.name for trace in figure.data}, {row['product'] for row in reported})

    def test_contribution_ranking_changes_with_inputs_and_names_the_comparison_period(self):
        app = self.case_app()
        case = load_case()
        names = {item['id']: item['label_ko'] for item in case['strategies']}
        def assert_ranking():
            actual = next(item.value for item in app.info if item.value.startswith('현재 입력 가정·'))
            expected = sorted(compare_strategies(app.session_state.tel_case_assumptions)['summary'],
                              key=lambda row: row['net_contribution_krw_m'], reverse=True)
            self.assertIn(f"{case['anchor_year'] + 1}–{case['anchor_year'] + case['horizon']}", actual)
            self.assertIn(' > '.join(names[row['strategy_id']] for row in expected), actual)
            return expected[0]['strategy_id']
        before = assert_ranking()
        cost_row = str(next(index for index, field in enumerate(FIELDS) if field[0] == 'development_cost_krw_m'))
        self.edit(app, {cost_row: {before: 1_000_000}})
        self.assertNotEqual(assert_ranking(), before)

    def test_saved_packet_restores_only_selected_strategy_after_explicit_apply(self):
        app = self.app()
        app.multiselect(key='nora_selected').set_value(['PFE']).run()
        app.radio(key='nora_mode').set_value('forecast').run()
        app.number_input(key='reported_sales').set_value(4321.0).run()
        app.radio(key='nora_mode').set_value('telmisartan').run()
        row = str(next(index for index, field in enumerate(FIELDS) if field[0] == 'annual_net_price_krw'))
        self.edit(app, {row: {'generic': 123000}})
        original = copy.deepcopy(app.session_state.tel_case_assumptions)
        values = copy.deepcopy(original['dual'])
        values['eligible_patients'] = 123456
        packet = build_handoff('dual', values)
        app.file_uploader(key='tel_case_restore_upload').set_value(
            ('saved-case.json', json.dumps(packet).encode(), 'application/json')).run()
        self.assertEqual(app.session_state.tel_case_assumptions, original)
        revision = app.session_state.tel_case_editor_revision
        app.button(key='tel_case_restore_apply').click().run()
        self.assertEqual(app.session_state.tel_case_editor_revision, revision + 1)
        self.assertEqual(app.session_state.tel_case_assumptions['dual'], values)
        for strategy_id in ['generic', 'triple']:
            self.assertEqual(app.session_state.tel_case_assumptions[strategy_id], original[strategy_id])
        self.assertEqual(app.selectbox(key='tel_case_strategy').value, 'dual')
        editor = next(table.value for table in app.dataframe if 'field' in table.value)
        patients = next(index for index, field in enumerate(FIELDS) if field[0] == 'eligible_patients')
        self.assertEqual(editor.loc[patients, 'dual'], 123456)
        app.radio(key='nora_mode').set_value('companies').run()
        self.assertEqual(app.multiselect(key='nora_selected').value, ['PFE'])
        app.radio(key='nora_mode').set_value('forecast').run()
        self.assertEqual(app.number_input(key='reported_sales').value, 4321.0)
        self.assertEqual(list(app.exception), [])

    def test_invalid_or_oversized_saved_packet_cannot_change_assumptions(self):
        app = self.case_app()
        original = copy.deepcopy(app.session_state.tel_case_assumptions)
        for payload in [b'not json', b' ' * 100_001, b'{"schema_version":1,"case_id":"another-case"}']:
            app.file_uploader(key='tel_case_restore_upload').set_value(
                ('invalid.json', payload, 'application/json')).run()
            self.assertTrue(app.error)
            self.assertNotIn('tel_case_restore_apply', [item.key for item in app.button])
            self.assertEqual(app.session_state.tel_case_assumptions, original)
            self.assertEqual(list(app.exception), [])

    def test_existing_forecast_inputs_survive_case_roundtrip(self):
        app = self.app()
        app.radio(key='nora_mode').set_value('forecast').run()
        app.number_input(key='reported_sales').set_value(4321.0).run()
        app.radio(key='nora_mode').set_value('telmisartan').run()
        app.radio(key='nora_mode').set_value('forecast').run()
        self.assertEqual(app.number_input(key='reported_sales').value, 4321.0)
        self.assertEqual(list(app.exception), [])

    def test_vcc_url_preserves_host_and_updates_only_case_parameters(self):
        with patch.dict(os.environ, {'VCC_APP_URL': 'http://127.0.0.1:8518/?lang=ko&page=old'}):
            url = urlsplit(vcc_case_url('triple'))
        self.assertEqual(url.netloc, '127.0.0.1:8518')
        self.assertEqual(parse_qs(url.query), {
            'lang': ['ko'], 'page': ['case'], 'case': ['telmisartan'], 'strategy': ['triple'], 'enter': ['1'],
        })


if __name__ == '__main__':
    unittest.main()
