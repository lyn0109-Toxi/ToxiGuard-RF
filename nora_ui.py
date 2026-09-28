"""Bilingual company revenue workspace; source records remain unmodified."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from nora_data import build_comparison, fetch_company_revenue, search_companies
from rf_i18n import bi

COLORS = ['#127F82', '#4863A0', '#D78636', '#9A64A0', '#647F43', '#AD5E62']
DATA_PATH = Path(__file__).parent / 'data' / 'revenue_snapshot.json'


def load_snapshot():
    if not DATA_PATH.exists():
        return {'records': [], 'retrieved_at': ''}
    return json.loads(DATA_PATH.read_text(encoding='utf-8'))


def initialize():
    if 'nora_records' not in st.session_state:
        snapshot = load_snapshot()
        st.session_state.nora_records = {
            ticker: [r for r in snapshot['records'] if r['ticker'] == ticker]
            for ticker in dict.fromkeys(r['ticker'] for r in snapshot['records'])
        }
        st.session_state.nora_retrieved = {
            ticker: snapshot['retrieved_at'] for ticker in st.session_state.nora_records
        }
    st.session_state.setdefault('nora_selected', ['LLY', 'PFE', 'MRK'])
    st.session_state.setdefault('nora_errors', {})


def style():
    st.markdown('''<style>
    .stApp {background:#F5F7F9;color:#183044}
    .block-container {max-width:1440px;padding-top:2.1rem;padding-bottom:3rem}
    [data-testid="stSidebar"] {background:#fff;border-right:1px solid #E0E7EB}
    [data-testid="stMetric"] {background:#fff;border:1px solid #E0E7EB;border-radius:14px;padding:17px}
    [data-testid="stMetricValue"] {font-size:1.8rem;color:#127F82}
    .nora-hero {background:#153549;border-radius:18px;padding:28px 32px;margin-bottom:22px}
    .nora-hero h1 {font-size:2.25rem;line-height:1.25;color:white;margin:8px 0 10px;word-break:keep-all;overflow-wrap:break-word}
    .nora-hero p {color:#D2E1E8;margin:0;max-width:780px;font-size:1.04rem}
    .nora-kicker {font-size:12px;letter-spacing:2px;color:#8FDBD3;font-weight:700}
    .nora-brand {font-size:2rem;font-weight:800;letter-spacing:3px;color:#153549}
    button[data-baseweb="tab"] {font-size:1rem;padding:12px 18px}
    @media(max-width:700px) {.block-container{padding-top:4.5rem}.nora-hero{padding:20px}.nora-hero h1{font-size:1.65rem}}
    </style>''', unsafe_allow_html=True)


def company_label(ticker, language=None):
    matches = search_companies(ticker)
    item = next((c for c in matches if c['ticker'] == ticker), None)
    if not item:
        return ticker
    language = language or st.session_state.get('rf_lang','en')
    name = (item.get('name_ko') or item['name']) if language=='ko' else item['name']
    return f"{name} · {ticker}"


def company_formatter():
    language=st.session_state.get('rf_lang','en')
    return lambda ticker:company_label(ticker,language)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fetch(ticker, user_agent):
    records=fetch_company_revenue(ticker, user_agent=user_agent or None)
    return {'records':records,'retrieved_at':datetime.now(timezone.utc).isoformat()}


def readable_error(exc):
    if exc.__cause__ is not None:
        return readable_error(exc.__cause__)
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        if status == 403:
            return bi('SEC blocked this connection (403). Try later or check the operator’s SEC contact setting.',
                      'SEC가 현재 연결을 차단했습니다(403). 나중에 재시도하거나 운영자의 SEC 연락처 설정을 확인하세요.')
        if status == 429:
            return bi('SEC request limit reached. Please try again later.', 'SEC 요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.')
    if isinstance(exc, (requests.Timeout, requests.ConnectionError)):
        return bi('Unable to connect to SEC. Please try again later.', 'SEC에 연결할 수 없습니다. 잠시 후 다시 시도하세요.')
    return bi('Annual revenue could not be retrieved. Check the company’s original report.',
              '연간 매출을 가져오지 못했습니다. 회사의 원문 보고서를 확인하세요.')


def refresh_selected():
    user_agent = os.getenv('SEC_USER_AGENT', '')
    try:
        user_agent = st.secrets.get('SEC_USER_AGENT', user_agent)
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    with st.status(bi('Retrieving annual company reports…', '회사별 연간 공시 자료를 조회하고 있습니다…')) as status:
        for ticker in st.session_state.nora_selected:
            try:
                fetched = cached_fetch(ticker, user_agent)
                rows = fetched['records']
                if not rows:
                    raise ValueError('No annual revenue')
                st.session_state.nora_records[ticker] = rows
                st.session_state.nora_retrieved[ticker] = fetched['retrieved_at']
                st.session_state.nora_errors.pop(ticker, None)
            except Exception as exc:
                st.session_state.nora_errors[ticker] = readable_error(exc)
        failed = any(t in st.session_state.nora_errors for t in st.session_state.nora_selected)
        status.update(label=bi('Some companies could not be refreshed' if failed else 'Reports retrieved',
                               '일부 회사의 자료를 갱신하지 못했습니다' if failed else '공시 자료를 가져왔습니다'),
                      state='error' if failed else 'complete', expanded=False)


def chart(fig, y_label):
    fig.update_layout(template='plotly_white', height=390, paper_bgcolor='rgba(0,0,0,0)',
                      margin=dict(l=10,r=15,t=35,b=35),
                      font=dict(family='Arial, Noto Sans KR, sans-serif',size=13,color='#183044'),
                      legend=dict(orientation='h',y=1.15), yaxis_title=y_label,
                      hovermode='closest')
    st.plotly_chart(fig, width='stretch')


def export_table(df):
    result = df.copy()
    fields = {
        'company': bi('Company','회사'), 'ticker':bi('Ticker','티커'),
        'fiscal_year':bi('Fiscal year','회계연도'), 'period_start':bi('Period start','회계기간 시작'),
        'period_end':bi('Period end','회계기간 종료'), 'revenue':bi('Revenue (original unit)','매출 (원 통화 단위)'),
        'currency':bi('Currency','통화'), 'yoy_pct':bi('YoY (%)','전년 대비 (%)'),
        'source_url':bi('Original report','원문 보고서'), 'filed':bi('Published / filed','발표 / 공시일'),
        'accession':bi('Report ID','보고서 식별번호'), 'concept':bi('Reported item','공시 항목'),
        'taxonomy':bi('Taxonomy','항목 체계'), 'year_basis':bi('Fiscal-year basis','회계연도 기준'),
        'source_kind':bi('Source type','자료 유형'),
        'source_note':bi('Source note','출처 메모'),
        'retrieved_at':bi('Retrieved at (UTC)','자료 확인 시각 (UTC)'),
        'comparability_note':bi('Growth comparison basis','성장률 비교 기준'),
        'yoy_prior_revenue':bi('Prior revenue used for growth','성장률 계산에 사용한 전년 매출'),
        'yoy_prior_source_url':bi('Prior-period source','전년 매출 출처'),
    }
    value_labels = {
        'official_report_snapshot':bi('Official report snapshot','공식 보고서 저장 자료'),
        'sec_companyfacts':bi('SEC Company Facts','SEC 공시 데이터'),
        'SEC Company Facts':bi('SEC Company Facts','SEC 공시 데이터'),
        'issuer_report':bi('Issuer annual report','발행회사 연차보고서'),
        'issuer_start_year':bi('Issuer fiscal-year starting year','발행회사 회계연도 시작 연도'),
        'issuer_fiscal_year':bi('Issuer fiscal year','발행회사 회계연도'),
        'issuer_calendar_year':bi('Issuer calendar year','발행회사 역년 기준'),
        'derived_period_end_year':bi('Derived from period end','회계기간 종료일에서 산출'),
        'same_filing_comparative':bi('Same-report prior period','같은 보고서의 전년 비교 수치'),
        'consecutive_same_basis':bi('Consecutive periods, same basis','동일 기준의 연속 회계기간'),
        'first_available_period':bi('No earlier annual period','직전 연간 자료 없음'),
        'nonconsecutive_periods':bi('Gap between annual periods','연속 회계기간 아님'),
        'currency_or_concept_changed':bi('Currency or reported item changed','통화 또는 공시 항목 변경'),
        'incompatible_restatement_basis':bi('Restatement basis differs','정정 기준 차이'),
        'nonpositive_prior_revenue':bi('Prior revenue is not positive','전년 매출이 0 이하'),
        'conflicting_comparative_values':bi('Conflicting comparative amounts','전년 비교 수치 불일치'),
    }
    for column in ('source_kind','year_basis','comparability_note'):
        if column in result:
            result[column]=result[column].map(lambda value:value_labels.get(value,value))
    return result[[key for key in fields if key in result]].rename(columns=fields)


def show_results(records):
    df = build_comparison(records)
    if df.empty:
        st.info(bi('Choose a company and retrieve its annual revenue.', '회사를 선택한 뒤 연간 매출을 조회하세요.'))
        return
    years = sorted(df.fiscal_year.astype(int).unique(), reverse=True)
    counts = df.groupby('fiscal_year').ticker.nunique()
    complete = counts[counts == df.ticker.nunique()].index.tolist()
    default_year = max(complete) if complete else years[0]
    c1,c2 = st.columns([1,3])
    with c1:
        if st.session_state.get('nora_year') not in years:
            st.session_state.nora_year = default_year
        year = st.selectbox(bi('Comparison fiscal year','비교 회계연도'),years,key='nora_year')
    with c2:
        st.caption(bi('Company-wide reported revenue. May include animal health, medical devices and collaboration revenue. Growth is nominal, not adjusted for currency or acquisitions.',
                      '회사 전체 공시 매출입니다. 동물의약품·의료기기·협업 매출 등이 포함될 수 있습니다. 성장률은 환율·인수 효과를 조정하지 않은 명목 수치입니다.'))
    annual = df[df.fiscal_year == year].copy()
    missing = set(st.session_state.nora_selected)-set(annual.ticker)
    if missing:
        st.warning(bi(f'No data for FY{year}: '+', '.join(sorted(missing)),f'{year} 회계연도 자료 없음: '+', '.join(sorted(missing))))
    if annual[['period_start','period_end']].drop_duplicates().shape[0] > 1:
        st.warning(bi('These fiscal years cover different dates. Review each period before interpreting the ranking.',
                      '회사별 회계기간이 다릅니다. 순위를 해석하기 전에 각 회사의 시작일·종료일을 확인하세요.'))
    cols=st.columns(3)
    cols[0].metric(bi('Companies with data','자료가 있는 회사'),f'{annual.ticker.nunique()} / {len(st.session_state.nora_selected)}')
    cols[1].metric(bi('Comparison year','비교 연도'),str(year))
    cols[2].metric(bi('Reporting currencies','공시 통화'),' · '.join(sorted(annual.currency.unique())))
    tabs = st.tabs([bi('Revenue comparison','매출 비교'),bi('Annual trends','연간 추이'),bi('Sources & download','출처·다운로드')])
    with tabs[0]:
        st.subheader(bi('Compare revenue in the same currency','같은 통화로 매출 비교'))
        if annual.currency.nunique()>1:
            st.info(bi('Currencies are shown separately. No exchange-rate conversion or cross-currency ranking is applied.',
                       '통화별로 나누어 표시합니다. 환율 환산이나 서로 다른 통화 간 순위는 적용하지 않습니다.'))
        for currency, group in annual.groupby('currency',sort=True):
            group=group.sort_values('revenue')
            custom=[[int(r.fiscal_year),r.period_start,r.period_end] for r in group.itertuples()]
            fig=go.Figure(go.Bar(x=group.revenue/1e9,y=[company_label(t) for t in group.ticker],orientation='h',
                                marker_color=COLORS[0],text=[f'{v/1e9:,.2f}' for v in group.revenue],textposition='auto',
                                customdata=custom,hovertemplate='%{y}<br>%{x:,.3f} '+currency+bi(' billion',' 십억')+'<br>%{customdata[1]} → %{customdata[2]}<extra></extra>'))
            fig.update_layout(title=currency, xaxis_title=bi('Revenue (billion)','매출 (십억 단위)'))
            chart(fig,'')
        view=annual[['ticker','fiscal_year','period_end','currency','revenue','yoy_pct']].copy()
        view['revenue']=view.revenue/1e9
        view=export_table(view).rename(columns={bi('Revenue (original unit)','매출 (원 통화 단위)'):bi('Revenue (billion)','매출 (십억 단위)')})
        st.dataframe(view, hide_index=True, width='stretch',column_config={bi('YoY (%)','전년 대비 (%)'):st.column_config.NumberColumn(format='%.2f%%'),bi('Revenue (billion)','매출 (십억 단위)'):st.column_config.NumberColumn(format='%.3f')})
        st.caption(bi('A blank growth rate means a comparable prior annual period is unavailable. Revenue ranking uses reported values; it does not measure profitability.',
                      '성장률이 비어 있으면 비교 가능한 직전 연간 자료가 없는 것입니다. 매출 순위는 공시 금액 기준이며 수익성을 나타내지 않습니다.'))
    with tabs[1]:
        st.subheader(bi('Revenue over time','연도별 매출 변화'))
        history=df[df.fiscal_year.between(year-4,year)]
        for currency,group in history.groupby('currency',sort=True):
            fig=go.Figure()
            for i,(ticker,rows) in enumerate(group.groupby('ticker',sort=False)):
                rows=rows.sort_values('period_end')
                fig.add_trace(go.Scatter(x=rows.period_end,y=rows.revenue/1e9,mode='lines+markers',name=company_label(ticker),
                                         line=dict(color=COLORS[i%len(COLORS)],width=3),marker_size=8,
                                         hovertemplate='%{x}<br>%{y:,.3f} '+currency+bi(' billion',' 십억')+'<extra>%{fullData.name}</extra>'))
            chart(fig,bi(f'{currency} billion',f'{currency} 십억'))
        st.caption(bi('The horizontal axis is the actual annual period end date. Up to five fiscal years are shown where available.',
                      '가로축은 실제 회계기간 종료일입니다. 자료가 있는 경우 최대 5개 회계연도를 표시합니다.'))
    with tabs[2]:
        st.subheader(bi('Trace every number to its source','숫자마다 원문 확인'))
        st.caption(bi('Downloaded revenue is in original currency units. Source dates, periods and links travel with the data.',
                      '다운로드 파일의 매출은 원 통화 단위입니다. 회계기간·출처 날짜·원문 링크를 함께 저장합니다.'))
        exported=export_table(df.sort_values(['ticker','fiscal_year'],ascending=[True,False]))
        st.dataframe(exported,hide_index=True,width='stretch',column_config={bi('Original report','원문 보고서'):st.column_config.LinkColumn(display_text=bi('Open source','원문 열기'))})
        st.download_button(bi('Download selected companies (CSV)','선택한 회사 자료 다운로드 (CSV)'),
                           exported.to_csv(index=False).encode('utf-8-sig'),file_name='nora-company-revenue.csv',mime='text/csv')
        for ticker,group in annual.groupby('ticker',sort=False):
            row=group.iloc[0]
            st.markdown(f"**{company_label(ticker)}** · {row.period_start} → {row.period_end}")
            st.link_button(bi('Open original report','원문 보고서 열기'),str(row.source_url))
            st.caption(bi('Retrieved: ','자료 확인: ')+st.session_state.nora_retrieved.get(ticker,'—'))


def render(app):
    # Keep inputs when a workspace's widgets are temporarily absent. Streamlit
    # otherwise removes their keys at the end of the other workspace's run.
    persistent_keys=set(app.scenario_session_defaults(app.SCENARIOS['Custom project'])) | {
        'nora_selected','nora_query','nora_candidate','nora_year',
        'rf_scenario_template','lookup_query','lookup_year','lookup_product','rf_lookup_mode',
    }
    for key in persistent_keys:
        if key in st.session_state:
            st.session_state[key]=st.session_state[key]
    initialize()
    st.session_state.setdefault('rf_lang','ko')
    st.sidebar.markdown('<div class="nora-brand">NORA</div>',unsafe_allow_html=True)
    st.sidebar.caption('PHARMA REVENUE INTELLIGENCE · 1.3.0')
    st.sidebar.radio('Language / 언어',['ko','en'],format_func=lambda v:'한국어' if v=='ko' else 'English',key='rf_lang',horizontal=True)
    mode_labels={'companies':bi('Company revenue comparison','회사 매출 비교'),
                 'forecast':bi('Product revenue scenarios','제품 매출 시나리오')}
    mode=st.sidebar.radio(bi('Workspace','작업 화면'),['companies','forecast'],
                          format_func=lambda v:mode_labels[v],key='nora_mode')
    if mode=='forecast':
        from rf_ui import render as render_forecast
        render_forecast(app,show_language=False)
        return
    style()
    st.markdown(f'<div class="nora-hero"><div class="nora-kicker">NORA / COMPANY REVENUE</div><h1>{bi("Pharma revenue, in perspective.","제약회사 매출을 한눈에 비교하세요.")}</h1><p>{bi("Find a company. Compare annual revenue and growth. Follow every figure back to its original report.","회사를 검색하고 연간 매출과 성장률을 비교하세요. 모든 수치는 원문 보고서로 연결됩니다.")}</p></div>',unsafe_allow_html=True)
    st.subheader(bi('Choose companies to compare','비교할 회사 선택'))
    query=st.text_input(bi('Company name or ticker','회사명 또는 티커'),placeholder=bi('Try Pfizer, Eli Lilly, MRK…','예: 화이자, 일라이 릴리, 머크, PFE'),key='nora_query')
    candidates=search_companies(query)
    if query.strip():
        if candidates:
            choice=st.selectbox(bi('Search results','검색 결과'),[c['ticker'] for c in candidates],format_func=company_formatter(),key='nora_candidate')
            if st.button(bi('Add to comparison','비교 대상에 추가'),key='nora_add',disabled=choice in st.session_state.nora_selected):
                if len(st.session_state.nora_selected)<6:
                    st.session_state.nora_selected=st.session_state.nora_selected+[choice]
                    st.rerun()
                else:
                    st.warning(bi('Compare up to six companies at a time.', '한 번에 최대 6개 회사를 비교할 수 있습니다.'))
        else:
            st.info(bi('No supported company found. Search a listed name or ticker; Korean domestic issuers are not connected yet.',
                       '지원 목록에서 회사를 찾지 못했습니다. 회사명·티커를 확인하세요. 국내 상장 제약사의 DART 자료는 아직 연결되지 않았습니다.'))
    options=list(dict.fromkeys([c['ticker'] for c in search_companies('')]+st.session_state.nora_selected))
    st.multiselect(bi('Comparison companies (up to 6)','비교 대상 (최대 6개)'),options,format_func=company_formatter(),max_selections=6,key='nora_selected')
    st.caption(bi('Search covers the supported SEC-filing pharma registry. Merck means US Merck & Co. (MSD).',
                  '검색은 지원 목록의 SEC 공시 제약회사를 대상으로 합니다. ‘머크’는 미국 Merck & Co.(MSD)를 뜻합니다.'))
    st.button(bi('Retrieve latest SEC data','SEC 최신 자료 조회'),key='nora_refresh',type='primary',on_click=refresh_selected,disabled=not st.session_state.nora_selected)
    records=[]
    snapshot_tickers=[]
    for ticker in st.session_state.nora_selected:
        rows=st.session_state.nora_records.get(ticker,[])
        records.extend(dict(row,retrieved_at=st.session_state.nora_retrieved.get(ticker,'')) for row in rows)
        if any(row.get('metadata_warning') for row in rows):
            st.warning(bi(f'{ticker}: Filing metadata could not be loaded. Period-derived years and filing-index links may be used.',
                          f'{ticker}: 공시 메타데이터를 가져오지 못했습니다. 회계기간에서 산출한 연도와 공시 목록 링크가 사용될 수 있습니다.'))
        if any(r.get('source_kind')=='official_report_snapshot' for r in rows):
            snapshot_tickers.append(ticker)
        if ticker in st.session_state.nora_errors:
            st.warning(f'{ticker}: '+st.session_state.nora_errors[ticker]+bi(' Previously loaded data remains visible.' if rows else ' No data displayed.', ' 기존에 불러온 자료를 표시합니다.' if rows else ' 표시할 자료가 없습니다.'))
    if snapshot_tickers:
        date=load_snapshot().get('retrieved_at','')[:10]
        st.info(bi(f'Official report snapshot · checked {date} · '+', '.join(snapshot_tickers)+'. These saved annual figures are not a live feed.',
                   f'공식 보고서 저장 자료 · 확인일 {date} · '+', '.join(snapshot_tickers)+'. 저장된 연간 실적이며 실시간 조회 결과가 아닙니다.'))
    show_results(records)
    with st.expander(bi('How this comparison works','비교 기준과 지원 범위')):
        st.markdown(bi('Annual consolidated revenue only. Quarterly figures and forecasts are excluded. Currencies are kept as reported. SEC refresh uses standard revenue tags; companies without usable annual tags show an explicit gap. Historical comparisons may reflect later restatements. Check the source and fiscal dates for changes in business scope.',
                       '연간 연결 매출을 비교하며 분기 실적과 전망치는 제외합니다. 공시 통화를 유지합니다. SEC 갱신은 표준 매출 항목을 사용하며 연간 항목이 없으면 자료 없음으로 표시합니다. 과거 수치는 이후 정정 공시가 반영될 수 있으므로 사업 범위 변경과 회계기간은 원문에서 확인하세요.'))
        st.link_button(bi('SEC data documentation','SEC 데이터 설명'),'https://www.sec.gov/search-filings/edgar-application-programming-interfaces')
