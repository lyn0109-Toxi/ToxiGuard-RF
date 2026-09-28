import html
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dataclasses import asdict
from rf_i18n import tr, bi

COLORS=['#137C83','#E99A4A','#263B60']
def table(df):
    return df.map(lambda v: tr(v) if isinstance(v,str) else v).rename(columns=tr)
def chart(fig, currency):
    fig.update_layout(template='plotly_white',height=390,margin=dict(l=16,r=16,t=30,b=30),font=dict(family='Arial, Noto Sans KR, sans-serif',size=14),legend=dict(orientation='h',y=1.14),yaxis_title=bi(f'{currency} million',f'{currency} 백만'),xaxis_title=None,hovermode='x unified')
    st.plotly_chart(fig,width='stretch')

def render(app, show_language=True):
    if show_language:
        st.sidebar.radio('Language / 언어',['en','ko'],format_func=lambda x:'English' if x=='en' else '한국어',key='rf_lang',horizontal=True)
    st.markdown('''<style>
    .stApp{background:#F4F6F8;color:#183044} .block-container{max-width:1400px;padding-top:2rem}
    [data-testid="stSidebar"]{background:#fff;border-right:1px solid #e0e6eb}
    [data-testid="stMetric"]{background:white;border:1px solid #e0e6eb;border-radius:14px;padding:18px}
    [data-testid="stMetricValue"]{font-size:1.65rem;color:#137C83}
    button[data-baseweb="tab"]{font-size:1rem;padding:12px 18px}
    .rf-hero{padding:24px 28px;background:#183044;color:white;border-radius:18px;margin-bottom:20px}
    .rf-hero h1{font-size:2rem;margin:5px 0;color:white}.rf-hero p{color:#cddce4;margin:0}
    .rf-tag{font-size:12px;letter-spacing:2px;color:#87d1ce}
    @media(max-width:700px){.rf-hero{padding:18px}.rf-hero h1{font-size:1.5rem}}
    </style>''',unsafe_allow_html=True)
    st.markdown(f'<div class="rf-hero"><div class="rf-tag">TOXIGUARD · RF 1.2.0</div><h1>{bi("Revenue scenarios. Visible assumptions.","매출 시나리오, 가정을 투명하게.")}</h1><p>{bi("Compare commercial pathways and identify the evidence needed for your next decision.","사업 시나리오를 비교하고 다음 의사결정에 필요한 근거를 확인합니다.")}</p></div>',unsafe_allow_html=True)
    x,p,matched=app.sidebar_inputs()
    if x.revenue_scope=='Company total':
        st.error(bi('Company revenue cannot define a product market. Provide a matching product or indication revenue anchor.','회사 전체 매출로 제품 시장을 계산할 수 없습니다. 제품·적응증 범위에 맞는 매출 근거를 입력하세요.'))
        app.render_lookup_panel(x)
        return
    try:f=app.calculate_forecast(x,p.launch_year)
    except ValueError as exc:
        st.error(bi(str(exc),'입력 범위를 확인하세요. 점유율은 양수, 성장률은 -100% 이상이어야 합니다.'));return
    pf=app.calculate_pipeline(x,p,f)
    score,_=app.calculate_confidence(x,matched)
    checks=app.validation_checks(x,p,f,pf,score)
    st.caption(f'{x.company} / {x.product} · {x.indication} · {x.currency_label} · {int(f.Year.min())}–{int(f.Year.max())}')
    st.info(bi('UNVERIFIED SCENARIO · Source values and assumptions require review. Metadata completeness is not accuracy.','미검증 시나리오 · 원문 수치와 가정은 검토가 필요합니다. 입력 완성도는 정확도가 아닙니다.'))
    cols=st.columns(4)
    labels=[bi('Peak within horizon','기간 내 최대 매출'),bi('Risk-adjusted peak','위험조정 최대 매출'),bi('Launch year','출시 연도'),bi('Items to review','검토 필요 항목')]
    vals=[app.fmt_money(f['Triangulated Forecast'].max(),x.currency_label),app.fmt_money(pf['Risk-Adjusted Revenue'].max(),x.currency_label),str(p.launch_year),str((checks.Status!='Pass').sum())]
    for c,l,v in zip(cols,labels,vals):c.metric(l,v)
    tabs=st.tabs([tr(v) for v in ['Overview','Calculation basis','Pipeline risk','Evidence review','Reports']])
    with tabs[0]:
        st.subheader(bi('Two models. One comparison.','두 모델의 차이를 먼저 확인하세요.'))
        fig=go.Figure()
        for name,col in zip(['Market Model','Patient Model','Triangulated Forecast'],COLORS):
            fig.add_trace(go.Scatter(x=f.Year,y=f[name],name=tr(name),mode='lines+markers',line=dict(color=col,width=3)))
        fig.add_vline(x=p.launch_year,line_dash='dot',line_color='#82939c')
        chart(fig,x.currency_label)
        st.caption(bi('Dotted line: launch year. The weighted average is a user-defined scenario, not a validated forecast.','점선: 출시 연도. 가중평균은 사용자가 정의한 시나리오이며 검증된 전망이 아닙니다.'))
        y=f.iloc[4];c1,c2=st.columns(2)
        with c1:
            st.subheader(bi('Year 5 model comparison','예측 5년차 모델 비교'))
            chart(go.Figure(go.Bar(x=[tr('Market Model'),tr('Patient Model')],y=[y['Market Model'],y['Patient Model']],marker_color=COLORS[:2])),x.currency_label)
        with c2:
            st.subheader(bi('Meeting questions','회의에서 확인할 질문'))
            for en,ko in [('Do sales and market share cover the same indication, region and year?','매출과 점유율의 적응증·지역·연도가 일치하는가?'),('What explains the difference between market and patient estimates?','시장 모델과 환자 모델의 차이는 무엇 때문인가?'),('Which launch, price or access assumption changes the decision?','출시·가격·접근성 중 어떤 가정이 결정을 바꾸는가?')]:st.markdown('• '+bi(en,ko))
            st.caption(bi('Year 5 is counted from the anchor year, not launch.','5년차는 출시일이 아닌 기준 연도부터 계산합니다.'))
    with tabs[1]:
        st.subheader(bi('Trace the calculation','계산 경로 확인'))
        st.markdown(bi('**Market** = TAM × share × access\n\n**Patient** = eligible patients × share × adherence × access × annual net price ÷ 1,000,000\n\n**Weighted scenario** = market × weight + patient × (1 − weight)','**시장 모델** = 전체 시장 × 점유율 × 접근성\n\n**환자 모델** = 적합 환자 × 점유율 × 순응도 × 접근성 × 연간 순가격 ÷ 1,000,000\n\n**가중 시나리오** = 시장 모델 × 가중치 + 환자 모델 × (1 − 가중치)'))
        st.dataframe(table(f),hide_index=True,width='stretch')
    with tabs[2]:
        st.subheader(bi('Commercial revenue → risk-adjusted revenue','사업 매출 → 위험조정 매출'))
        risk=pf['Risk Factor'].iloc[0]
        st.caption(bi(f'Probability {p.probability:g}% × label {p.label_factor:g}% × economics {p.economics:g}% = {risk:.2%}. User assumptions; not empirical validation.',f'성공확률 {p.probability:g}% × 허가 범위 {p.label_factor:g}% × 회사 귀속 {p.economics:g}% = {risk:.2%}. 사용자 가정이며 실증 검증값이 아닙니다.'))
        fig=go.Figure()
        for name,col in zip(['Unadjusted Revenue','Risk-Adjusted Revenue'],COLORS):fig.add_trace(go.Bar(x=pf.Year,y=pf[name],name=tr(name),marker_color=col))
        fig.update_layout(barmode='group');chart(fig,x.currency_label)
        st.dataframe(table(pf),hide_index=True,width='stretch')
    with tabs[3]:
        st.subheader(bi('Source record & open review','출처 기록과 미해결 검토'))
        st.progress(score/100,text=bi(f'Metadata completeness {score}% — unverified',f'메타데이터 완성도 {score}% — 미검증'))
        st.write(bi('Source type','출처 유형')+': '+tr(x.source_type))
        st.write(bi('Revenue scope','매출 범위')+': '+tr(x.revenue_scope))
        st.write(bi('Report ID','보고서 식별번호')+': '+x.accession)
        st.write(bi('Source URL','출처 URL')+': '+x.evidence_url)
        st.caption(bi('The detailed audit table retains source English terminology.','상세 검토표의 원문 용어는 영어로 유지합니다.'))
        st.dataframe(table(checks.assign(Status=checks.Status.map(tr))),hide_index=True,width='stretch')
        app.render_lookup_panel(x)
    with tabs[4]:
        st.subheader(bi('Export the decision record','검토 기록 내보내기'))
        memo=bi('# Revenue scenario review','# 매출 시나리오 검토')+'\n\n'+bi('UNVERIFIED — review source and assumptions.','미검증 — 원문과 가정을 확인해야 합니다.')+'\n\n'+f'{x.company} / {x.product}\n\n'+bi('Source','출처')+f': {x.evidence_url}\n\n'+bi('Report ID','보고서 ID')+f': {x.accession}\n\n'+bi('Launch year','출시 연도')+f': {p.launch_year}\n\n'+bi('Forecast values (million)','예측값 (백만 단위)')+f' {x.currency_label}\n\n'+table(f).to_csv(index=False)
        report='<html lang="'+st.session_state.rf_lang+'"><meta charset="utf-8"><style>body{font-family:Arial,sans-serif;max-width:1200px;margin:40px auto;color:#183044}table{border-collapse:collapse;width:100%;font-size:12px}td,th{padding:8px;border:1px solid #ddd}pre{white-space:pre-wrap}</style><body><h1>ToxiGuard RF 1.2.0</h1><pre>'+html.escape(memo)+'</pre>'+table(pf).to_html(index=False)+table(checks).to_html(index=False)+'</body></html>'
        c1,c2,c3=st.columns(3)
        c1.download_button(bi('Download memo','메모 다운로드'),memo,file_name='rf-memo.md')
        c2.download_button(bi('Download HTML','HTML 다운로드'),report,file_name='rf-report.html',mime='text/html')
        c3.download_button(bi('Download CSV','CSV 다운로드'),app.build_csv_bytes(f,pf),file_name='rf-forecast.csv',mime='text/csv')
        packet={'schema':'rf-evidence-1','verification':'unverified','inputs':asdict(x),'pipeline':asdict(p),'forecast':f.to_dict('records'),'risk_adjusted':pf.to_dict('records')}
        st.download_button(bi('NORA evidence packet (JSON)','NORA 근거 패킷 (JSON)'),json.dumps(packet,ensure_ascii=False,indent=2),file_name='rf-nora-evidence.json',mime='application/json')
        st.caption(bi('JSON export only; this does not automatically execute or connect NORA.','JSON 내보내기 기능입니다. NORA를 자동 실행하거나 연결하지 않습니다.'))
