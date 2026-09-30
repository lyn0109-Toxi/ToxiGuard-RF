"""Transparent, hypothetical Telmisartan strategy comparison shared with VCC.

Reported product sales are context only. They never become a market-size anchor.
All commercial inputs in this model are editable teaching assumptions.
"""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path

DATA_FILE = Path(__file__).parent / 'data' / 'telmisartan_case.json'
CASE_ID = 'telmisartan-kr-2026'
FIELDS = {
    'launch_year': (2027, 2040), 'eligible_patients': (0, 100_000_000),
    'annual_net_price_krw': (0, 10_000_000), 'initial_share_pct': (0, 100),
    'peak_share_pct': (0, 100), 'ramp_years': (1, 20), 'access_pct': (0, 100),
    'adherence_pct': (0, 100), 'success_pct': (0, 100), 'economics_pct': (0, 100),
    'contribution_margin_pct': (0, 100), 'development_cost_krw_m': (0, 1_000_000),
    'annual_fixed_cost_krw_m': (0, 1_000_000), 'growth_pct': (-50, 50),
}


def load_case():
    return json.loads(DATA_FILE.read_text(encoding='utf-8'))


def validate_assumptions(values):
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError('가정 항목이 누락되었거나 지원하지 않는 항목이 있습니다.')
    clean = {}
    for key, (lower, upper) in FIELDS.items():
        value = values[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{key}: 유한한 숫자를 입력하세요.')
        if not lower <= value <= upper:
            raise ValueError(f'{key}: {lower}–{upper} 범위를 확인하세요.')
        if key in {'launch_year', 'ramp_years'} and int(value) != value:
            raise ValueError(f'{key}: 정수가 필요합니다.')
        clean[key] = int(value) if key in {'launch_year', 'ramp_years'} else float(value)
    if clean['initial_share_pct'] > clean['peak_share_pct']:
        raise ValueError('초기 점유율은 최대 점유율 이하여야 합니다.')
    return clean


def _strategy_rows(strategy, values, case, *, derived=False):
    a = dict(values) if derived else validate_assumptions(values)
    annual = []
    for year in range(case['anchor_year']+1, case['anchor_year']+case['horizon']+1):
        t = year-case['anchor_year']
        commercial_year = year-a['launch_year']+1
        if commercial_year <= 0:
            revenue = 0.0
            share = 0.0
        else:
            ramp = min((commercial_year-1)/a['ramp_years'], 1.0)
            share = (a['initial_share_pct']+(a['peak_share_pct']-a['initial_share_pct'])*ramp)/100
            patients = a['eligible_patients']*(1+a['growth_pct']/100)**t
            revenue = patients*share*(a['access_pct']/100)*(a['adherence_pct']/100)*a['annual_net_price_krw']/1_000_000
        risk_adjusted = revenue*(a['success_pct']/100)*(a['economics_pct']/100)
        # Fixed costs are charged only after launch and only in the success branch.
        fixed = a['annual_fixed_cost_krw_m']*(a['success_pct']/100) if commercial_year > 0 else 0.0
        annual.append(dict(strategy_id=strategy['id'], strategy=strategy['label_ko'], year=year,
                           revenue_krw_m=revenue, risk_adjusted_revenue_krw_m=risk_adjusted,
                           share_pct=share*100, risk_adjusted_contribution_krw_m=risk_adjusted*a['contribution_margin_pct']/100-fixed))
    summary = dict(strategy_id=strategy['id'], strategy=strategy['label_ko'], launch_year=a['launch_year'],
                   peak_revenue_krw_m=max(r['revenue_krw_m'] for r in annual),
                   mature_revenue_at_base_population_krw_m=a['eligible_patients']*(a['peak_share_pct']/100)*(a['access_pct']/100)*(a['adherence_pct']/100)*a['annual_net_price_krw']/1_000_000,
                   peak_risk_adjusted_krw_m=max(r['risk_adjusted_revenue_krw_m'] for r in annual),
                   total_risk_adjusted_krw_m=sum(r['risk_adjusted_revenue_krw_m'] for r in annual),
                   development_cost_krw_m=a['development_cost_krw_m'],
                   net_contribution_krw_m=sum(r['risk_adjusted_contribution_krw_m'] for r in annual)-a['development_cost_krw_m'])
    return annual, summary


def compare_strategies(overrides=None):
    case = load_case()
    ids = {s['id'] for s in case['strategies']}
    if overrides is not None and (not isinstance(overrides, dict) or set(overrides)-ids):
        raise ValueError('지원하지 않는 개발전략입니다.')
    annual, summary, assumptions = [], [], {}
    for strategy in case['strategies']:
        values = copy.deepcopy(strategy['assumptions'])
        values.update((overrides or {}).get(strategy['id'], {}))
        assumptions[strategy['id']] = validate_assumptions(values)
        rows, total = _strategy_rows(strategy, values, case)
        annual.extend(rows)
        summary.append(total)
    return {'annual': annual, 'summary': summary, 'assumptions': assumptions}


def sensitivity(overrides=None):
    base = compare_strategies(overrides)['assumptions']
    scenarios = [
        ('기본 가정', 'Base assumptions', 1.0, 1.0, 0, 1.0),
        ('환자수 −30%', 'Eligible patients −30%', .7, 1.0, 0, 1.0),
        ('순가격 −20%', 'Net price −20%', 1.0, .8, 0, 1.0),
        ('출시 2년 지연', 'Launch delayed 2 years', 1.0, 1.0, 2, 1.0),
        ('개발비 +50%', 'Development cost +50%', 1.0, 1.0, 0, 1.5),
    ]
    result = []
    for ko, en, patients, price, delay, cost in scenarios:
        inputs = copy.deepcopy(base)
        for a in inputs.values():
            a['eligible_patients'] *= patients
            a['annual_net_price_krw'] *= price
            a['launch_year'] += delay
            a['development_cost_krw_m'] *= cost
        case = load_case()
        for strategy in case['strategies']:
            _, row = _strategy_rows(strategy, inputs[strategy['id']], case, derived=True)
            result.append(dict(row, scenario=ko, scenario_en=en))
    return result


def build_handoff(strategy_id, assumptions):
    case = load_case()
    strategy = next((s for s in case['strategies'] if s['id'] == strategy_id), None)
    if strategy is None:
        raise ValueError('지원하지 않는 개발전략입니다.')
    # Accept only one complete strategy input. VCC recalculates every result.
    a = validate_assumptions(assumptions)
    _, summary = _strategy_rows(strategy, a, case)
    return dict(schema_version=1, case_id=CASE_ID, data_as_of=case['as_of'], market='KR', currency='KRW',
                anchor_year=case['anchor_year'], horizon=case['horizon'], strategy_id=strategy_id,
                assumptions=a, summary=summary, evidence_type='hypothetical_scenario',
                source_ids=[s['id'] for s in case['sources']])


def validate_handoff(payload):
    if not isinstance(payload, dict) or type(payload.get('schema_version')) is not int or payload.get('schema_version') != 1 or payload.get('case_id') != CASE_ID:
        raise ValueError('지원하는 Telmisartan NORA 패킷이 아닙니다.')
    if payload.get('market') != 'KR' or payload.get('currency') != 'KRW' or payload.get('evidence_type') != 'hypothetical_scenario':
        raise ValueError('지역·통화·가정 구분을 확인하세요.')
    case = load_case()
    if payload.get('anchor_year') != case['anchor_year'] or payload.get('horizon') != case['horizon']:
        raise ValueError('비교 기간이 다른 패킷입니다.')
    return build_handoff(payload.get('strategy_id'), payload.get('assumptions'))
