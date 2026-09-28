import streamlit as st
PAIRS = '''Scenario template|시나리오 템플릿
Load scenario|시나리오 값 불러오기
Revenue scope / 매출 범위|매출 근거 범위
Company|회사
Product / asset|제품 / 후보물질
Indication market|적응증 시장
Currency label|통화 단위
Revenue input, million|매출 입력 (백만 단위)
Anchor year|기준 연도
Current product share, %|현재 제품 점유율 (%)
Market CAGR, %|시장 연평균 성장률 (%)
Initial share, %|출시 첫해 점유율 (%)
Peak share, %|목표 점유율 (%)
Uptake speed|시장 침투 속도
Payer access, %|보험·시장 접근성 (%)
Competition drag, % per year|연간 경쟁에 따른 감소율 (%)
Prevalent / incident patients|유병 / 발생 환자 수
Patient growth, %|환자 수 증가율 (%)
Diagnosis rate, %|진단율 (%)
Treatment rate, %|치료율 (%)
Eligible rate, %|치료 대상 적합률 (%)
Net annual price per patient|환자당 연간 순가격
Adherence / persistence, %|복약 순응 / 치료 유지율 (%)
Market model weight, %|시장 모델 가중치 (%)
Primary source type|주요 출처 유형
Evidence URL|근거 URL
Filing / report date|공시 / 보고서 날짜
Accession / report ID|공시 / 보고서 식별번호
Reviewer note|검토 메모
Clinical phase|임상 단계
Pipeline asset|개발 후보물질
Pipeline indication|개발 적응증
Expected launch year|예상 출시 연도
Probability of success, %|성공확률 가정 (%)
Expected label scope, %|예상 허가 범위 계수 (%)
Company economics, %|회사 귀속 매출 비율 (%)
NCT / clinical ID|NCT / 임상시험 번호
Clinical source type|임상 근거 유형
Clinical evidence URL|임상 근거 URL
Clinical evidence note|임상 근거 메모
Illustrative assumption|예시 가정
Company total|회사 전체 매출
Product / indication matched|제품 / 적응증 범위 일치
Custom project|사용자 프로젝트
Immunology follow-on entrant|면역질환 후발 진입
Oncology label-expansion asset|항암제 적응증 확대
Rare disease premium therapy|희귀질환 고가 치료제
Metabolic chronic-use asset|대사질환 장기 치료제
Company Annual Report|기업 연차보고서
CMS / HIRA cross-check|CMS / HIRA 교차 확인
Manual review needed|수동 검토 필요
Preclinical|비임상
Phase 1|임상 1상
Phase 2|임상 2상
Phase 3|임상 3상
Filing / Review|허가 신청 / 심사
Approved|허가 완료
Year|연도
Market Model|시장 모델
Patient Model|환자 모델
Triangulated Forecast|가중평균 매출
Market TAM|전체 시장 규모
Base TAM|기준 시장 규모
Adjusted Share|조정 점유율
Patient Pool|환자 모집단
Addressable Patients|치료 대상 환자
Treated Patients|접근성·순응도 반영 환자
Forecast Year|예측 연차
Commercial Year|출시 후 연차
Unadjusted Revenue|위험조정 전 매출
Risk Factor|위험조정 계수
Risk-Adjusted Revenue|위험조정 매출
Overview|요약
Calculation basis|계산 근거
Pipeline risk|개발 위험
Evidence review|근거 검토
Reports|보고서
Pass|계산 확인
Review|검토 필요
Fix|수정 필요
Group|구분
Check|검토 항목
Status|상태
Basis|근거
Next action|다음 업무'''
KO=dict(line.split('|',1) for line in PAIRS.splitlines())
def tr(text):
    return KO.get(text,text) if st.session_state.get('rf_lang','en')=='ko' else text

def bi(en,ko):
    return ko if st.session_state.get('rf_lang','en')=='ko' else en
KO.update({
'Official revenue lookup':'공식 매출 자료 조회','Company name, ticker, or CIK':'회사명 / 티커 / CIK','FY':'회계연도','Product row keyword':'제품 행 검색어','Lookup mode':'조회 방식','Built-in reference anchors (unverified)':'내장 참고 자료 (미검증)','Live SEC lookup':'SEC 실시간 조회','Lookup revenue evidence':'매출 근거 조회','#### Latest anchor':'#### 최근 조회 자료','Revenue':'매출','FY / Source':'회계연도 / 출처',
'Evidence':'근거','Calculation':'계산','Pipeline':'개발','Overall':'종합','Primary revenue source':'주요 매출 출처','Accession / report ID':'공시 / 보고서 ID','Year sequence':'연도 순서','Patient model':'환자 모델','Risk factor':'위험조정 계수','Launch window':'출시 시점','Metadata completeness':'메타데이터 완성도',
'Use SEC 10-K/20-F, annual report, or DART as the final primary source.':'SEC 공시·연차보고서·DART 원문을 확인하세요.',
'Keep the source URL in the final memo.':'최종 메모에 출처 URL을 유지하세요.',
'Add SEC accession, annual report ID, or official report reference.':'공시 번호 또는 보고서 식별번호를 기록하세요.',
'Confirm that company-level sales are appropriate for this product/indication market.':'매출과 점유율의 제품·적응증·지역 범위를 확인하세요.',
'Forecast years should be continuous.':'예측 연도가 연속되는지 확인하세요.',
'Confirm epidemiology, treated population, eligibility, and price.':'역학·치료 환자·적합성·가격 근거를 확인하세요.',
'PoS, label factor, and economics should have traceable assumptions.':'성공확률·허가 범위·귀속 매출 비율의 가정 근거를 기록하세요.',
'If launch is outside the model horizon, extend forecast or revise timing.':'출시가 예측 기간 밖이면 기간을 늘리거나 시점을 검토하세요.',
'Strengthen source ID, URL, memo, and official lookup before external use.':'외부 사용 전 출처 ID·URL·메모·원문을 검토하세요.'})

def formatter():
    lang=st.session_state.get('rf_lang','en')
    return lambda value: KO.get(value,value) if lang=='ko' else value
