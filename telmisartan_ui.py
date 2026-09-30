"""Telmisartan strategy comparison, using the shared case model and VCC packet."""
from __future__ import annotations

import copy
import html
import json
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rf_i18n import bi
from telmisartan_case import build_handoff, compare_strategies, load_case, sensitivity, validate_handoff

VCC_URL = 'https://toxiguard-vcc-jkpjgwyuzbu5vbudizucm5.streamlit.app/'
COLORS = ['#127F82', '#4863A0', '#D78636', '#9A64A0', '#647F43']
FIELDS = [
    ('launch_year', 'Launch year', '출시 연도', 'year', '연도'),
    ('eligible_patients', 'Eligible patients', '대상 환자 수', 'patients', '명'),
    ('annual_net_price_krw', 'Annual net price per patient', '환자당 연간 순가격', 'KRW', '원'),
    ('initial_share_pct', 'Initial share', '출시 첫해 점유율', '%', '%'),
    ('peak_share_pct', 'Peak share', '목표 점유율', '%', '%'),
    ('ramp_years', 'Years to peak share', '목표 점유율 도달 기간', 'years', '년'),
    ('access_pct', 'Market access', '시장 접근성', '%', '%'),
    ('adherence_pct', 'Adherence / persistence', '복약 순응·치료 유지율', '%', '%'),
    ('success_pct', 'Development success assumption', '개발 성공확률 가정', '%', '%'),
    ('economics_pct', 'Company revenue share', '회사 귀속 매출 비율', '%', '%'),
    ('contribution_margin_pct', 'Contribution margin', '기여이익률', '%', '%'),
    ('development_cost_krw_m', 'Development cost', '개발비', 'KRW million', '백만원'),
    ('annual_fixed_cost_krw_m', 'Annual fixed cost', '연간 고정비', 'KRW million', '백만원'),
    ('growth_pct', 'Eligible population annual growth', '대상 환자 수 연간 성장률', '%', '%'),
]


def label(strategy):
    return strategy.get('label_ko' if st.session_state.get('rf_lang') == 'ko' else 'label_en', strategy['id'])


def initialize(case):
    st.session_state.setdefault('tel_case_assumptions', {
        item['id']: copy.deepcopy(item['assumptions']) for item in case['strategies']
    })
    st.session_state.setdefault('tel_case_editor_revision', 0)
    ids = [item['id'] for item in case['strategies']]
    if st.session_state.get('tel_case_strategy') not in ids:
        requested = st.query_params.get('strategy')
        st.session_state.tel_case_strategy = requested if requested in ids else ids[0]


def reset_assumptions(case):
    st.session_state.tel_case_assumptions = {
        item['id']: copy.deepcopy(item['assumptions']) for item in case['strategies']
    }
    st.session_state.tel_case_editor_revision += 1


def parse_saved_case(raw):
    if len(raw) > 100_000:
        raise ValueError(bi('The case JSON must be 100 KB or smaller.', '사례 JSON은 100KB 이하여야 합니다.'))
    return validate_handoff(json.loads(raw.decode('utf-8-sig')))


def restore_saved_case(packet):
    verified = validate_handoff(packet)
    values = copy.deepcopy(st.session_state.tel_case_assumptions)
    values[verified['strategy_id']] = verified['assumptions']
    st.session_state.tel_case_assumptions = values
    st.session_state.tel_case_strategy = verified['strategy_id']
    st.session_state.tel_case_editor_revision += 1
    st.session_state.tel_case_restore_notice = verified['strategy_id']


def render_restore(case):
    with st.expander(bi('Restore saved case assumptions', '저장한 사례 가정 불러오기')):
        st.caption(bi('Upload a Telmisartan JSON exported by NORA or VCC (up to 100 KB). Applying it replaces only the saved strategy’s assumptions.',
                      'NORA 또는 VCC에서 내보낸 Telmisartan JSON을 올리세요(최대 100KB). 적용하면 파일에 담긴 전략의 가정만 바뀝니다.'))
        uploaded = st.file_uploader(bi('Case assumptions JSON', '사례 가정 JSON'), type=['json'], key='tel_case_restore_upload')
        if uploaded is not None:
            try:
                packet = parse_saved_case(uploaded.getvalue())
            except (ValueError, TypeError, UnicodeError) as exc:
                st.error(bi('Unable to restore this file: ', '이 파일을 불러올 수 없습니다: ') + str(exc))
            else:
                item = next(item for item in case['strategies'] if item['id'] == packet['strategy_id'])
                st.write(bi('Saved strategy: ', '저장된 전략: ') + label(item))
                st.button(bi('Apply saved assumptions', '저장된 가정 적용'), key='tel_case_restore_apply',
                          on_click=restore_saved_case, args=(packet,))
        restored = st.session_state.pop('tel_case_restore_notice', None)
        if restored:
            item = next(item for item in case['strategies'] if item['id'] == restored)
            st.success(bi('Restored: ', '가정을 불러왔습니다: ') + label(item))


def apply_assumption_edits(widget_key, strategy_ids):
    """Store edits independently of the editor's visibility and language."""
    values = copy.deepcopy(st.session_state['tel_case_editor_base'])
    for row, edits in st.session_state.get(widget_key, {}).get('edited_rows', {}).items():
        position = int(row)
        if 0 <= position < len(FIELDS):
            field = FIELDS[position][0]
            for strategy_id, value in edits.items():
                if strategy_id in strategy_ids:
                    values[strategy_id][field] = value
    st.session_state['tel_case_assumptions'] = values


def vcc_case_url(strategy_id):
    url = urlsplit(os.getenv('VCC_APP_URL') or VCC_URL)
    query = dict(parse_qsl(url.query, keep_blank_values=True))
    query.update(enter='1', page='case', case='telmisartan', strategy=strategy_id)
    return urlunsplit((url.scheme, url.netloc, url.path, urlencode(query), url.fragment))


def source_frame(records, sources):
    frame = pd.DataFrame(records)
    if 'source_id' in frame:
        urls = {source['id']: source.get('url', '') for source in sources}
        frame['source_url'] = frame.source_id.map(urls).fillna('')
    return frame


def reported_revenue_figure(records):
    """Chart reported annual amounts only; missing product revenue stays missing."""
    frame = pd.DataFrame(records)
    if frame.empty or not {'product', 'period', 'amount_krw_m'}.issubset(frame.columns):
        return None
    frame['year'] = pd.to_numeric(frame.period, errors='coerce')
    frame['amount'] = pd.to_numeric(frame.amount_krw_m, errors='coerce')
    frame = frame.dropna(subset=['year', 'amount']).sort_values('year')
    if frame.empty:
        return None
    frame['year'] = frame.year.astype(int)
    fig = go.Figure()
    for index, (product, rows) in enumerate(frame.groupby('product', sort=False)):
        fig.add_trace(go.Scatter(x=rows.year.tolist(), y=(rows.amount / 100).tolist(), name=product,
                                 mode='lines+markers+text', text=[f'{amount / 100:,.2f}' for amount in rows.amount],
                                 textposition='top center', line=dict(color=COLORS[index % len(COLORS)], width=3),
                                 hovertemplate='%{x}: %{y:,.2f}<extra>%{fullData.name}</extra>'))
    fig.update_layout(template='plotly_white', height=290, margin=dict(l=16, r=16, t=45, b=20), showlegend=True,
                      yaxis_title=bi('KRW 100 million · reported', '억원 · 공개 실적'),
                      xaxis=dict(title=bi('Reported year', '실적 연도'), dtick=1),
                      legend=dict(orientation='h', y=1.2), hovermode='x unified')
    return fig


def render_evidence(case):
    st.subheader(bi('Observed products and development records', '제품·개발 현황과 출처'))
    st.caption(bi(
        'Published records provide context. Development status, population and commercial scope must be checked for each strategy.',
        '공개 기록을 바탕으로 현황을 살펴봅니다. 전략별 개발 상태·대상 환자·사업 범위를 원문에서 확인하세요.'))
    columns = {
        'product': bi('Product', '제품'), 'composition': bi('Composition', '성분 구성'),
        'status': bi('Status', '상태'), 'region': bi('Region', '지역'),
        'source_id': bi('Source ID', '출처 ID'), 'source_url': bi('Source', '원문'),
        'note': bi('Note', '주석'), 'period': bi('Period', '기간'),
        'scope': bi('Revenue scope', '매출 범위'),
    }
    pipeline = source_frame(case.get('pipeline', []), case.get('sources', []))
    if pipeline.empty:
        st.info(bi('No sourced development records are included yet.', '출처를 확인한 개발 현황 자료가 아직 없습니다.'))
    else:
        pipeline = pipeline.rename(columns=columns)
        st.dataframe(pipeline, hide_index=True, width='stretch',
                     column_config={columns['source_url']: st.column_config.LinkColumn(columns['source_url'])})
    st.subheader(bi('Reported revenue evidence', '공개 매출 근거'))
    revenue = source_frame(case.get('revenue_evidence', []), case.get('sources', []))
    if revenue.empty:
        st.info(bi('No comparable product revenue figures are included. The scenarios below use editable assumptions.',
                   '비교 가능한 제품 매출 수치가 없습니다. 아래 시나리오는 수정 가능한 가정으로 계산합니다.'))
    else:
        figure = reported_revenue_figure(case['revenue_evidence'])
        if figure is not None:
            st.plotly_chart(figure, width='stretch', key='tel_case_reported_revenue_chart')
            st.caption(bi('Chart: reported product sales only. Rows without a disclosed amount remain blank in the evidence table.',
                          '차트에는 공개된 제품 실적만 표시합니다. 매출을 확인하지 못한 제품은 아래 표에서 빈값으로 유지합니다.'))
            st.caption(bi('The reported regional and consolidation scopes may differ by product; check the revenue scope in the table.',
                          '제품별 공시의 지역·연결 범위가 다를 수 있으므로 표의 매출 범위를 함께 확인하세요.'))
        if 'amount_krw_m' in revenue:
            revenue[bi('Reported revenue (KRW 100 million)', '공개 매출 (억원)')] = pd.to_numeric(revenue.pop('amount_krw_m'), errors='coerce') / 100
        revenue = revenue.rename(columns=columns)
        st.dataframe(revenue, hide_index=True, width='stretch',
                     column_config={columns['source_url']: st.column_config.LinkColumn(columns['source_url'])})
    st.caption(bi('Reported revenue retains its source period and scope. It is not used as a product market-size anchor.',
                  '공개 매출의 기간·범위를 함께 표시합니다. 이 수치를 제품 시장규모의 기준값으로 사용하지 않습니다.'))
    with st.expander(bi('Source register', '출처 목록')):
        for source in case.get('sources', []):
            title = f"{source.get('id', '')} · {source.get('title', '')}"
            if source.get('url'):
                st.link_button(title, source['url'])
            else:
                st.write(title)
            st.caption(' · '.join(str(source[key]) for key in ('date', 'note') if source.get(key)))


def render_assumptions(case):
    st.subheader(bi('Compare strategies on explicit assumptions', '전략별 가정을 직접 비교하세요'))
    st.caption(bi('All values in this editor are planning assumptions. Development success is user-defined, not an observed probability.',
                  '이 표의 값은 모두 계획을 위한 가정입니다. 개발 성공확률도 사용자가 정하는 가정입니다.'))
    render_restore(case)
    strategies = case['strategies']
    field_label, unit_label = bi('Assumption', '가정 항목'), bi('Unit', '단위')
    widget_key = f"tel_case_editor_{st.session_state.get('rf_lang', 'ko')}_{st.session_state.tel_case_editor_revision}"
    # Keep the editor's input data stable while its frontend accumulates edits.
    # Rehydrate from durable values after reset, language or workspace changes.
    if st.session_state.get('tel_case_editor_context') != widget_key or widget_key not in st.session_state:
        st.session_state.tel_case_editor_base = copy.deepcopy(st.session_state.tel_case_assumptions)
        st.session_state.tel_case_editor_context = widget_key
    frame = pd.DataFrame({
        'field': [bi(item[1], item[2]) for item in FIELDS],
        'unit': [bi(item[3], item[4]) for item in FIELDS],
        **{item['id']: [st.session_state.tel_case_editor_base[item['id']][field[0]] for field in FIELDS]
           for item in strategies},
    })
    # Mixed-unit columns must accept fractional prices/rates even when all
    # bundled examples happen to be whole numbers.
    for item in strategies:
        frame[item['id']] = pd.to_numeric(frame[item['id']], errors='coerce').astype(float)
    config = {'field': st.column_config.TextColumn(field_label), 'unit': st.column_config.TextColumn(unit_label)}
    config.update({item['id']: st.column_config.NumberColumn(label(item), required=True, format='%.2f') for item in strategies})
    st.data_editor(frame, key=widget_key, hide_index=True, width='stretch',
                   height=563, disabled=['field', 'unit'], num_rows='fixed', column_config=config,
                   on_change=apply_assumption_edits, args=(widget_key, [item['id'] for item in strategies]))
    st.button(bi('Restore case assumptions', '사례 기본가정 복원'), key='tel_case_reset',
              on_click=reset_assumptions, args=(case,))
    st.caption(bi('Input costs use KRW million. Result charts and tables use KRW 100 million (KRW million ÷ 100).',
                  '비용 입력은 백만원, 결과 표·차트는 억원 단위입니다. 백만원 값을 100으로 나누어 억원으로 표시합니다.'))


def render_chart(annual, strategies, field, title):
    fig = go.Figure()
    for index, item in enumerate(strategies):
        rows = annual.loc[annual.strategy_id == item['id']]
        fig.add_trace(go.Scatter(x=rows.year, y=rows[field] / 100, name=label(item), mode='lines+markers',
                                 line=dict(color=COLORS[index % len(COLORS)], width=3)))
    fig.update_layout(title=title, template='plotly_white', height=360,
                      margin=dict(l=16, r=16, t=55, b=20), legend=dict(orientation='h', y=1.12),
                      yaxis_title=bi('KRW 100 million', '억원'), xaxis_title=bi('Year', '연도'), hovermode='x unified')
    st.plotly_chart(fig, width='stretch')


def render_comparison(case, comparison, sensitivity_rows):
    st.subheader(bi('Revenue and development strategy comparison', '매출·개발전략 비교'))
    annual = pd.DataFrame(comparison['annual'])
    summary = pd.DataFrame(comparison['summary'])
    strategies = case['strategies']
    left, right = st.columns(2)
    with left:
        render_chart(annual, strategies, 'revenue_krw_m', bi('Revenue scenario', '매출 시나리오'))
    with right:
        render_chart(annual, strategies, 'risk_adjusted_revenue_krw_m', bi('Risk-adjusted revenue', '위험조정 매출'))
    labels = {item['id']: label(item) for item in strategies}
    money_fields = {
        'peak_revenue_krw_m': bi('Peak revenue', '기간 내 최대 매출'),
        'mature_revenue_at_base_population_krw_m': bi('Revenue at target share', '목표점유율 매출'),
        'peak_risk_adjusted_krw_m': bi('Risk-adjusted peak', '위험조정 최대 매출'),
        'total_risk_adjusted_krw_m': bi('Cumulative risk-adjusted revenue', '누적 위험조정 매출'),
        'development_cost_krw_m': bi('Development cost', '개발비'),
        'net_contribution_krw_m': bi('Net contribution after development cost', '개발비 차감 후 기여액'),
    }
    money_fields = {field: name for field, name in money_fields.items() if field in summary}
    metric_column = bi('Metric / unit', '지표 / 단위')
    display = pd.DataFrame({metric_column: [bi('Launch year (year)', '출시 연도 (년)')]
                            + [name + bi(' (KRW 100 million)', ' (억원)') for name in money_fields.values()]})
    indexed = summary.set_index('strategy_id')
    for item in strategies:
        row = indexed.loc[item['id']]
        display[labels[item['id']]] = [str(int(row.launch_year))] + [f'{row[field] / 100:,.2f}' for field in money_fields]
    st.dataframe(display, hide_index=True, width='stretch', height=320,
                 column_config={metric_column: st.column_config.TextColumn(metric_column, width=260),
                                **{name: st.column_config.TextColumn(name, width=180) for name in labels.values()}})
    ranked = summary.assign(display_contribution=(summary.net_contribution_krw_m / 100).round(2)).sort_values(
        'display_contribution', ascending=False, kind='stable')
    groups = []
    for contribution, group in ranked.groupby('display_contribution', sort=False):
        groups.append((' = '.join(labels[strategy_id] for strategy_id in group.strategy_id), contribution))
    if groups:
        ranking = ' > '.join(group[0] for group in groups)
        start, end = int(annual.year.min()), int(annual.year.max())
        top, amount = groups[0]
        st.info(bi(
            f'Under the current inputs for {start}–{end}, the highest contribution after development costs is {top} '
            f'({amount:,.2f} in KRW 100 million); current ranking: {ranking}.',
            f'현재 입력 가정·{start}–{end}년 비교에서 개발비 차감 후 기여액이 가장 높은 전략은 {top}'
            f'({amount:,.2f}억원)이며, 현재 순위는 {ranking}입니다.'))
    st.caption(bi('Money: KRW 100 million. Cumulative values cover the displayed model horizon; later launches have fewer selling years. Net contribution is a scenario metric, not company profit, NPV or a valuation.',
                  '금액: 억원. 누적값은 모델 기간 합계이므로 출시가 늦으면 판매 기간도 짧아집니다. 기여액은 시나리오 지표이며 회사 순이익·현재가치·기업가치가 아닙니다.'))
    if 'mature_revenue_at_base_population_krw_m' in summary:
        st.caption(bi('Revenue at target share applies the target share to the anchor-year patient population; no achievement date is assigned.',
                      '목표점유율 매출은 기준연도 환자수에 목표점유율을 적용한 값이며 도달 시점은 지정하지 않습니다.'))
    with st.expander(bi('Calculation and annual values', '계산 방식과 연도별 수치')):
        st.markdown(bi(
            '**Revenue** = eligible patients × share × access × adherence × annual net price.\n\n'
            '**Risk-adjusted revenue** applies the success and company revenue share assumptions. The contribution calculation includes development and fixed costs.',
            '**매출** = 대상 환자 수 × 점유율 × 접근성 × 순응도 × 연간 순가격.\n\n'
            '**위험조정 매출**에는 성공확률과 회사 귀속 비율 가정을 적용합니다. 기여액 계산에는 개발비와 고정비를 반영합니다.'))
        annual_display = annual[['strategy_id', 'strategy', 'year', 'revenue_krw_m', 'risk_adjusted_revenue_krw_m']].copy()
        annual_display['strategy'] = annual_display.strategy_id.map(labels)
        annual_display = annual_display.drop(columns=['strategy_id'])
        annual_display['revenue_krw_m'] /= 100
        annual_display['risk_adjusted_revenue_krw_m'] /= 100
        st.dataframe(annual_display.rename(columns={
            'strategy': bi('Strategy', '전략'), 'year': bi('Year', '연도'),
            'revenue_krw_m': bi('Revenue (KRW 100 million)', '매출 (억원)'),
            'risk_adjusted_revenue_krw_m': bi('Risk-adjusted revenue (KRW 100 million)', '위험조정 매출 (억원)'),
        }), hide_index=True, width='stretch')
    st.subheader(bi('Sensitivity to assumptions', '가정 변화에 따른 민감도'))
    sens = pd.DataFrame(sensitivity_rows)
    if not sens.empty:
        if st.session_state.get('rf_lang') == 'en' and 'scenario_en' in sens:
            sens['scenario'] = sens['scenario_en']
        sens = sens[['strategy_id', 'scenario', 'net_contribution_krw_m', 'total_risk_adjusted_krw_m']].copy()
        sens['strategy_id'] = sens.strategy_id.map(labels)
        sens['scenario'] = sens.scenario.map(lambda value: {
            'low': bi('Low', '낮은 가정'), 'base': bi('Base', '기본'), 'high': bi('High', '높은 가정'),
        }.get(value, value))
        for field in ('net_contribution_krw_m', 'total_risk_adjusted_krw_m'):
            sens[field] /= 100
        st.dataframe(sens.rename(columns={
            'strategy_id': bi('Strategy', '전략'), 'scenario': bi('Scenario', '변화 조건'),
            'net_contribution_krw_m': bi('Net contribution (KRW 100 million)', '기여액 (억원)'),
            'total_risk_adjusted_krw_m': bi('Cumulative risk-adjusted revenue (KRW 100 million)', '누적 위험조정 매출 (억원)'),
        }), hide_index=True, width='stretch')
    st.caption(bi('Sensitivity changes planning assumptions; it is not a confidence interval or a probability distribution.',
                  '민감도는 가정을 바꾸어 보는 비교이며 신뢰구간이나 확률분포가 아닙니다.'))
    col1, col2 = st.columns(2)
    col1.download_button(bi('Annual scenario CSV', '연도별 시나리오 CSV'), annual.to_csv(index=False).encode('utf-8-sig'),
                         file_name='telmisartan-annual-krw-million.csv', mime='text/csv', key='tel_case_annual_csv')
    col2.download_button(bi('Strategy summary CSV', '전략 비교 CSV'), summary.to_csv(index=False).encode('utf-8-sig'),
                         file_name='telmisartan-summary-krw-million.csv', mime='text/csv', key='tel_case_summary_csv')
    st.caption(bi('CSV monetary fields ending in _krw_m are in KRW million.', 'CSV에서 _krw_m으로 끝나는 금액 열은 백만원 단위입니다.'))


def render_handoff(case, comparison):
    st.subheader(bi('Continue the development review in VCC', 'VCC에서 개발 검토 이어가기'))
    strategies = {item['id']: item for item in case['strategies']}
    language = st.session_state.get('rf_lang', 'ko')
    names = {key: item.get('label_' + language, key) for key, item in strategies.items()}
    selected = st.selectbox(bi('Strategy to review', '검토할 전략'), list(strategies),
                            format_func=names.get, key='tel_case_strategy')
    item = strategies[selected]
    for field, en, ko in [('composition', 'Product concept', '제품 구성'),
                           ('development', 'Development approach', '개발 방향'),
                           ('vcc_focus', 'Evidence to review in VCC', 'VCC에서 확인할 근거')]:
        st.markdown('**' + bi(en, ko) + '**')
        st.write(item.get(field + '_' + language, item.get(field + '_en', '')))
    packet = build_handoff(selected, comparison['assumptions'][selected])
    st.download_button(bi('Download current assumptions for VCC (JSON)', '현재 가정 VCC 전달용 다운로드 (JSON)'),
                        json.dumps(packet, ensure_ascii=False, indent=2, allow_nan=False),
                        file_name=f'telmisartan-{selected}-vcc.json', mime='application/json',
                        key='tel_case_handoff', type='primary')
    st.link_button(bi('Open VCC case (default assumptions)', 'VCC 사례 열기 (기본가정)'), vcc_case_url(selected))
    st.info(bi('The link opens this strategy with case defaults. To carry your edited values across, download the JSON above and upload it on the VCC case page. No values are sent automatically.',
               '링크는 선택한 전략을 기본가정으로 엽니다. 수정한 값을 이어서 쓰려면 위 JSON을 내려받아 VCC 사례 화면에서 업로드하세요. 값은 자동 전송되지 않습니다.'))


def render(app):
    st.markdown("<style>.block-container{padding-top:4.5rem}</style>", unsafe_allow_html=True)
    case = load_case()
    initialize(case)
    title = case.get('title_ko' if st.session_state.get('rf_lang') == 'ko' else 'title_en', 'Telmisartan')
    st.markdown(f'<div class="nora-hero"><div class="nora-kicker">NORA × VCC / TELMISARTAN</div>'
                f'<h1>{html.escape(title)}</h1><p>{bi("Compare product strategies, revenue assumptions and the development evidence needed next.", "제품 전략·매출 가정·다음 개발 단계에 필요한 근거를 함께 비교하세요.")}</p></div>', unsafe_allow_html=True)
    st.caption(f"{bi('Evidence date', '근거 확인일')}: {case.get('as_of', '')} · {case.get('market', '')} · "
               + bi('Results: KRW 100 million', '결과 단위: 억원'))
    st.info(bi('CASE STUDY · Commercial figures are editable scenarios. They are not reported sales forecasts or a development recommendation.',
               '사례 연구 · 사업 수치는 수정 가능한 가정으로 계산합니다. 공시 전망이나 개발 권고가 아닙니다.'))
    evidence, assumptions, results, handoff = st.tabs([
        bi('1 · Evidence and pipeline', '1 · 근거·파이프라인'),
        bi('2 · Strategy assumptions', '2 · 전략별 가정'),
        bi('3 · Revenue comparison', '3 · 매출 비교'),
        bi('4 · VCC development review', '4 · VCC 개발 검토'),
    ])
    with evidence:
        render_evidence(case)
    with assumptions:
        render_assumptions(case)
    try:
        comparison = compare_strategies(st.session_state.tel_case_assumptions)
    except (ValueError, TypeError) as exc:
        with assumptions:
            st.error(bi('Please correct the assumptions: ', '가정 입력을 확인하세요: ') + str(exc))
        for tab in (results, handoff):
            with tab:
                st.warning(bi('Correct the assumption table before calculating or exporting.', '가정 표를 수정하면 계산과 내보내기를 이어갈 수 있습니다.'))
        return
    try:
        sensitivity_rows = sensitivity(st.session_state.tel_case_assumptions)
        sensitivity_error = ''
    except (ValueError, TypeError) as exc:
        sensitivity_rows = []
        sensitivity_error = bi('A sensitivity scenario exceeds the input limits. Base results remain available. ',
                               '민감도 조건이 입력 범위를 벗어났습니다. 기본 계산 결과는 계속 사용할 수 있습니다. ') + str(exc)
    with results:
        render_comparison(case, comparison, sensitivity_rows)
        if sensitivity_error:
            st.warning(sensitivity_error)
    with handoff:
        render_handoff(case, comparison)
