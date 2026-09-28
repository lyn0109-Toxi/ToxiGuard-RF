"""Interaction regressions for company selection, bilingual state and sources."""
import copy
import unittest
from unittest.mock import patch

import requests
from streamlit.testing.v1 import AppTest

from nora_ui import load_snapshot


class NoraInteractionTests(unittest.TestCase):
    def app(self):
        app=AppTest.from_file('streamlit_app.py',default_timeout=15).run()
        self.assertEqual(list(app.exception),[])
        return app

    def test_default_is_company_comparison_with_real_source_rows(self):
        app=self.app()
        self.assertEqual(app.radio(key='nora_mode').value,'companies')
        self.assertEqual(app.radio(key='rf_lang').value,'ko')
        self.assertEqual(app.multiselect(key='nora_selected').value,['LLY','PFE','MRK'])
        self.assertEqual(app.selectbox(key='nora_year').value,2025)
        self.assertTrue(any('실시간 조회 결과가 아닙니다' in element.value for element in app.info))
        self.assertEqual(len(app.dataframe[1].value),9)

    def test_korean_search_add_remove_and_language_retains_selection(self):
        app=self.app()
        app.text_input(key='nora_query').set_value('다케다').run()
        self.assertEqual(app.selectbox(key='nora_candidate').value,'TAK')
        app.button(key='nora_add').click().run()
        self.assertIn('TAK',app.multiselect(key='nora_selected').value)
        self.assertTrue(any('TAK' in element.value for element in app.warning))
        app.radio(key='rf_lang').set_value('en').run()
        self.assertIn('TAK',app.multiselect(key='nora_selected').value)
        self.assertEqual(list(app.exception),[])
        app.multiselect(key='nora_selected').set_value(['PFE']).run()
        self.assertEqual(set(app.dataframe[1].value.Ticker),{'PFE'})

    def test_unsupported_search_does_not_change_company(self):
        app=self.app()
        app.text_input(key='nora_query').set_value('삼성바이오로직스').run()
        self.assertEqual(app.multiselect(key='nora_selected').value,['LLY','PFE','MRK'])
        self.assertTrue(any('DART' in element.value for element in app.info))
        self.assertEqual(list(app.exception),[])

    def test_no_selection_renders_empty_state(self):
        app=self.app()
        app.multiselect(key='nora_selected').set_value([]).run()
        self.assertTrue(app.button(key='nora_refresh').disabled)
        self.assertEqual(len(app.dataframe),0)
        self.assertEqual(list(app.exception),[])

    def test_failed_refresh_keeps_snapshot_with_visible_failure(self):
        app=self.app()
        original=copy.deepcopy(app.session_state.nora_records)
        response=requests.Response();response.status_code=403
        with patch('nora_ui.cached_fetch',side_effect=requests.HTTPError('Forbidden',response=response)):
            app.button(key='nora_refresh').click().run()
        self.assertEqual(app.session_state.nora_records,original)
        self.assertEqual(len(app.warning),3)
        self.assertTrue(all('403' in message.value for message in app.warning))
        self.assertTrue(any('실시간 조회 결과가 아닙니다' in message.value for message in app.info))
        self.assertEqual(list(app.exception),[])

    def test_successful_refresh_replaces_only_requested_company(self):
        app=self.app()
        app.multiselect(key='nora_selected').set_value(['PFE']).run()
        rows=[dict(row,source_kind='sec_companyfacts') for row in load_snapshot()['records'] if row['ticker']=='PFE']
        with patch('nora_ui.cached_fetch',return_value={'records':rows,'retrieved_at':'2026-09-28T12:00:00+00:00'}):
            app.button(key='nora_refresh').click().run()
        self.assertEqual(app.session_state.nora_records['PFE'],rows)
        self.assertTrue(app.session_state.nora_records['LLY'])
        self.assertFalse(app.session_state.nora_errors)
        self.assertEqual(app.session_state.nora_retrieved['PFE'],'2026-09-28T12:00:00+00:00')
        self.assertFalse(any('저장 자료' in message.value for message in app.info))
        self.assertEqual(list(app.exception),[])

    def test_workspace_switch_retains_company_data(self):
        app=self.app()
        app.multiselect(key='nora_selected').set_value(['PFE']).run()
        app.radio(key='nora_mode').set_value('forecast').run()
        self.assertEqual(list(app.exception),[])
        app.number_input(key='reported_sales').set_value(6789.0).run()
        app.radio(key='nora_mode').set_value('companies').run()
        self.assertEqual(list(app.exception),[])
        self.assertEqual(app.multiselect(key='nora_selected').value,['PFE'])
        app.radio(key='nora_mode').set_value('forecast').run()
        self.assertEqual(app.number_input(key='reported_sales').value,6789.0)


if __name__=='__main__':
    unittest.main()
