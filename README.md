# AMatch 정산 대사 시스템 (Vercel 배포판)

기존 Streamlit 데스크톱 앱을 **Vercel 서버리스 배포용**으로 재구성했습니다.
정산 대사 계산 로직(Python/pandas)은 그대로 유지하고, UI는 정적 웹으로 제공합니다.
**데이터는 저장하지 않는 1회성 분석 도구**이며, 결과를 수식이 적용된 엑셀로 내려받을 수 있습니다.

## 구조

```
.
├── api/
│   ├── index.py         # FastAPI 엔드포인트 (Vercel Python 서버리스 함수)
│   ├── reconcile.py     # 정산 대사 핵심 로직 (기존 app.py 이식)
│   └── excel_export.py  # 수식 적용 엑셀(.xlsx) 생성기 (openpyxl)
├── public/
│   └── index.html       # 프론트엔드 (데이터 세팅 / 정산 대시보드)
├── requirements.txt     # 배포용 의존성
└── vercel.json          # 라우팅 설정
```

> `api/db.py` 는 과거 저장 기능용이었으며 현재 코드에서 사용하지 않습니다(삭제해도 무방).

## 주요 기능

- **데이터 세팅**: 정산월 선택 + 필수 4개 파일(카카오 빌링 / 더존 세금계산서 발행 / 카카오 현금영수증 / DAUM 내부결제) + PG 상세(선택) 업로드 후 분석
- **정산 대시보드**: 총괄 요약, DAUM 정산 피벗(결제완료·취소완료·부분취소), PG / 현금영수증 / 세금계산서 대사, 정산 제외(구다음) 내역
- **엑셀 다운로드**: 결과를 수식이 적용된 .xlsx 로 내려받기
  - 원본 시트: `원본_DAUM` / `원본_더존` / `원본_카카오빌링` / `원본_현금영수증` / `원본_PG`
  - `원본_DAUM` 에 보조 수식열(정산월여부 / 최종매출인식금액 / 구다음 판별 / 대상매출) 추가
  - 요약 시트: `요약_DAUM정산` / `요약_PG` / `요약_현금영수증` / `요약_세금계산서` / `정산제외`
  - DAUM정산·세금계산서·PG·현금영수증 원본합계는 `SUMIFS/SUMIF` 수식이라 **원본을 고치면 요약이 자동 재계산**됩니다.
  - 단, 현금영수증 시차보정(익월/전월)·카카오 실제발행(중복제거·PG실패 제외)은 순수 수식화가 어려워 계산값으로 기입됩니다.

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/health` | 상태 확인 |
| POST | `/api/analyze?target_month=YYYY-MM` | 파일 업로드 → 대사 실행 후 결과(JSON) 반환 |
| POST | `/api/export?target_month=YYYY-MM` | 파일 업로드 → 수식 적용 엑셀(.xlsx) 다운로드 |

두 POST 모두 `multipart/form-data` 로 `bill / sap / rec / axz` (필수) 와 `pg_files`(선택, 다중)를 전송합니다.

## 배포 (Vercel)

1. 이 저장소를 GitHub 에 올리고 Vercel 프로젝트에 연결합니다(Root Directory = 저장소 루트, 즉 `api/`·`public/`·`vercel.json`·`requirements.txt` 가 있는 위치).
2. 별도 환경변수·DB 설정이 필요 없습니다. (데이터를 저장하지 않음)
3. 배포하면 프론트는 루트(`/`), API 는 `/api/*` 로 서비스됩니다.

`vercel.json` 은 루트(`/`)를 `/index.html` 로 보내고, `/api/*` 를 Python 함수(`api/index.py`)로 라우팅합니다.

## 로컬 실행

```bash
pip install -r requirements-dev.txt
uvicorn api.index:app --reload --port 8000
# 프론트(public/index.html)를 정적 서버로 띄우거나, 브라우저로 직접 열어 테스트
```

> 로컬에서 프론트와 API 도메인이 다르면 `index.html` 상단의 `API` 상수를 `http://localhost:8000` 으로 바꾸세요.

## ⚠️ 서버리스 제약 (중요)

- **요청 본문 크기 한도**: Vercel 서버리스 함수는 요청 본문이 **4.5MB** 로 제한됩니다.
  분석·엑셀 다운로드 모두 원본 파일을 업로드하므로, 파일 합계가 이를 넘으면 실패합니다.
  큰 파일은 (a) CSV 로 변환해 용량 축소, (b) Streamlit 그대로 Render/Railway 배포 등을 고려하세요.
- **실행 시간**: 함수 최대 실행시간은 요금제(Hobby=최대 10초, Pro=최대 60초)를 따릅니다.
  필요 시 Vercel → Settings → Functions 에서 `maxDuration` 을 조정하세요.
- **Python 런타임**: Vercel 기본 Python 런타임(3.12 권장)을 사용합니다.

## 계산 로직 안전성

`api/reconcile.py` 의 계산식은 기존 `app.py` 의 "프리징 영역" 을 그대로 옮긴 것으로,
시차 결제 보정(익월 발행/전월 말일), 구다음메일 제외, PG/현금영수증/세금계산서 대사,
피벗 집계 결과가 동일하게 산출됩니다. 엑셀 요약의 수식 결과도 LibreOffice 재계산으로
Python 계산값과 일치함을 확인했습니다.
