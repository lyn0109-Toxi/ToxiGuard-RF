# NORA 공식 연차보고서 매출 저장본

확인 시각: **2026-09-28 15:56:27 UTC**. 파일: `revenue_snapshot.json`.

이 자료는 웹에서 직접 확인한 공식 보고서 표를 저장한 초기 데이터입니다. 실시간 SEC API 응답, 추정치, 전망치 또는 현재 분기 실적이 아닙니다. 각 회사의 2025년 보고서에 수록된 2023–2025년 연결 연간 매출을 사용합니다. 표의 기간은 매년 12월 31일 종료 연도이며 JSON에는 1월 1일–12월 31일의 연간 보고기간을 기록했습니다.

원표의 USD 백만 단위 값을 **1,000,000배**하여 JSON의 `revenue`에 USD 정수로 저장합니다. 이는 표시 단위 변환이며 원표보다 높은 정밀도를 의미하지 않습니다. 예를 들어 65,179 USD million은 65,179,000,000 USD입니다. 보고서 개정, 표시 단위 변경 또는 이후 비교열 재작성에 따라 다른 출처의 과거 값과 차이가 날 수 있습니다. `filed`는 참조한 보고서의 제출일이며 매출이 발생한 연도의 제출일이 아닙니다.

| 회사 | 2023 (USD million) | 2024 (USD million) | 2025 (USD million) | 원표 항목 |
|---|---:|---:|---:|---|
| Eli Lilly and Company (LLY) | 34,124 | 45,043 | 65,179 | Revenue |
| Pfizer Inc. (PFE) | 59,553 | 63,627 | 62,579 | Revenues |
| Merck & Co., Inc. (MRK) | 60,115 | 64,168 | 65,011 | Sales |

## Eli Lilly and Company

- 원자료: [2025 Form 10-K, Consolidated Statements of Operations, 인쇄 p.57 / PDF 57쪽](https://investor.lilly.com/static-files/0d64699c-0cc7-490e-9152-b2ba1de08634#page=57).
- 표의 연결 Revenue 행, 2025 / 2024 / 2023 비교열을 사용했습니다. 같은 보고서 Note 2의 매출 주석(PDF 63쪽)에서도 값을 교차 확인했습니다.
- [SEC 제출 내역](https://www.sec.gov/Archives/edgar/data/59478/000005947826000013/0000059478-26-000013-index.htm): 2026-02-12, accession `0000059478-26-000013`.
- 연결 매출에는 제품 매출과 협업·기타 수익이 포함됩니다. 2025 보고서의 백만 단위 표를 그대로 따르므로 [LSEG 제공 IR 대화형 재무표](https://investor.lilly.com/financial-information/fundamentals/income-statement)의 과거 소수점 표시값과 일부 차이가 있습니다. 서로 다른 표시 정밀도를 섞지 않았습니다.

## Pfizer Inc.

- 원자료: [2025 Annual Review — Performance, Financial Performance, p.2](https://annualreview.pfizer.com/assets/pdfs/pfizer-performance-2025.pdf#page=2).
- 12월 31일 종료 연도에 대한 3개년 요약표의 Revenues 행, 2025 / 2024 / 2023 비교열을 사용했습니다. [공식 Annual Review 웹페이지의 Financial Performance 표](https://annualreview.pfizer.com/)와 같은 값입니다.
- 원자료 제목을 보고서 식별자로 사용합니다. Annual Review 자체의 정확한 발행일을 확인하지 못하여 `filed`는 빈 문자열입니다. [2025 Form 10-K의 SEC 제출 내역](https://www.sec.gov/Archives/edgar/data/78003/000007800326000026/0000078003-26-000026-index.htm)은 2026-02-26 및 accession `0000078003-26-000026`을 명시하지만, 이를 Annual Review 발행일로 대체하지 않았습니다.

## Merck & Co., Inc.

- 원자료: [2025 Form 10-K, Consolidated Statement of Income, 인쇄 p.77 / PDF 79쪽](https://www.merck.com/wp-content/uploads/sites/124/2026/02/MRK-12.31.2025-10K-FINAL.pdf#page=79).
- 연결 Sales 행, 2025 / 2024 / 2023 비교열을 사용했습니다. 같은 보고서의 Total Sales 표(PDF 3쪽)와 교차 확인했습니다.
- [SEC 제출 내역](https://www.sec.gov/Archives/edgar/data/310158/0000310158-26-000063-index.html) 및 보고서 표지: 2026-02-24, accession `0000310158-26-000063`.
- 회사 전체 연결 매출이므로 동물의약품 부문을 포함합니다. Pharmaceutical 부문만의 매출과 혼동하면 안 됩니다. 미국 Merck & Co., Inc. 데이터이며 독일 Merck KGaA 데이터가 아닙니다.

## 업데이트 원칙

공식 보고서 또는 공식 공시 응답을 다시 확인한 경우에만 갱신합니다. 웹페이지를 확인하지 않고 저장본의 확인 시각만 바꾸지 않습니다. 새 값을 넣을 때는 회사·연도·기간·통화·연결 범위·보고서 위치·보고 정밀도를 함께 검증해야 합니다. 실시간 수집이 실패하면 저장본이라는 표시와 확인 날짜를 유지하고, 지원하지 않는 회사나 연도는 누락으로 처리합니다.
