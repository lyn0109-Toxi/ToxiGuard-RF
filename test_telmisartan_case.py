import copy
import unittest
from telmisartan_case import load_case, compare_strategies, sensitivity, build_handoff, validate_handoff

class TelmisartanModelTests(unittest.TestCase):
    def test_zero_before_launch_and_exact_first_year_units(self):
        r=compare_strategies()
        rows=[v for v in r['annual'] if v['strategy_id']=='generic']
        self.assertEqual(rows[0]['revenue_krw_m'],0)
        self.assertAlmostEqual(rows[1]['revenue_krw_m'],460.8)
        self.assertAlmostEqual(rows[1]['risk_adjusted_revenue_krw_m'],391.68)
        self.assertEqual(len(r['annual']),24)

    def test_zero_success_and_economics(self):
        r=compare_strategies({'dual':{'success_pct':0}})
        s=next(v for v in r['summary'] if v['strategy_id']=='dual')
        self.assertEqual(s['total_risk_adjusted_krw_m'],0)
        self.assertEqual(s['net_contribution_krw_m'],-5000)
        r=compare_strategies({'generic':{'economics_pct':50}})
        b=compare_strategies()
        self.assertAlmostEqual(r['summary'][0]['total_risk_adjusted_krw_m'],b['summary'][0]['total_risk_adjusted_krw_m']/2)

    def test_delay_price_and_upper_bound_sensitivity(self):
        rows=sensitivity()
        for sid in ['generic','dual','triple']:
            values={r['scenario']:r for r in rows if r['strategy_id']==sid}
            base=values['기본 가정']['total_risk_adjusted_krw_m']
            self.assertLess(values['출시 2년 지연']['total_risk_adjusted_krw_m'],base)
            self.assertAlmostEqual(values['순가격 −20%']['total_risk_adjusted_krw_m'],base*.8)
        self.assertEqual(len(sensitivity({'triple':{'launch_year':2040,'development_cost_krw_m':1_000_000}})),15)

    def test_handoff_recomputes_and_rejects_wrong_scope(self):
        a=compare_strategies()['assumptions']['dual']
        packet=build_handoff('dual',a)
        packet['summary']['peak_revenue_krw_m']=999999999
        self.assertNotEqual(validate_handoff(packet)['summary']['peak_revenue_krw_m'],999999999)
        for key,value in [('market','US'),('currency','USD'),('evidence_type','reported'),('horizon',20),('schema_version',True)]:
            bad=copy.deepcopy(packet);bad[key]=value
            with self.assertRaises(ValueError):validate_handoff(bad)

    def test_invalid_assumptions_and_no_source_mutation(self):
        before=load_case()
        for patch in [{'initial_share_pct':20,'peak_share_pct':10},{'success_pct':float('nan')},{'launch_year':2028.5},{'access_pct':True}]:
            with self.assertRaises(ValueError):compare_strategies({'generic':patch})
        compare_strategies({'generic':{'success_pct':1}})
        self.assertEqual(load_case(),before)

if __name__=='__main__':unittest.main()
