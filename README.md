# AMatch 정산 대사 시스템 (Vercel 배포판)

기존 Streamlit 데스크톱 앱을 **Vercel 서버리스 배포용**으로 재구성했습니다.
정산 대사 계산 로직(Python/pandas)은 그대로 유지하고, UI는 정적 웹으로,
결과는 DB에 저장·삭제할 수 있도록 기능을 추가했습니다.

## 구조

```
vercel-app/
├── api/
│   ├── index.py      # FastAPI 엔드포인트 (Vercel Python 서버리스 함수)
│   ├── reconcile.py  # 정산 대사 핵심 로직 (기존 app.py 이식)
│   └── db.py         # Postgres 결과 저장 계층
├── public/
│   └── index.html    # 프론트엔드 (데이터 세팅 / 대시보드 / 저장된 결과)
├── requirements.txt  # 배포용 의존성
├── vercel.json       # 라우팅·함수 설정
└── .env.example      # 환경변수 예시
```

## 주요 기능

- **데이터 세팅**: 정산월 선택 + 필수 4개 파일(빌링/SAP/현금영수증/AXZ) + PG 상세(선택) 업로드 후 분석
- **정산 대시보드**: 총괄 요약, AXZ 정산 피벗, PG/현금영수증/세금계산서 대사, 정산 제외 내역
- **결과 저장/삭제 (신규)**: 분석 결과를 이름과 함께 저장하고, '저장된 정산결과' 메뉴에서 목록·불러오기·삭제

## API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/health` | 상태 및 저장소 모드 확인 |
| POST | `/api/analyze?target_month=YYYY-MM` | 파일 업로드 → 대사 실행(저장 안 함) |
| POST | `/api/results` | 결과 저장 `{label, payload}` |
| GET | `/api/results` | 저장 목록 |
| GET | `/api/results/{id}` | 결과 전체 조회 |
| DELETE | `/api/results/{id}` | 결과 삭제 |

## 배포 (Vercel)

1. 이 `vercel-app` 폴더를 Git 저장소로 푸시(또는 Vercel CLI로 해당 폴더에서 `vercel`).
2. Vercel 프로젝트 **Root Directory** 를 `vercel-app` 으로 지정.
3. 결과 저장을 쓰려면 Postgres를 준비하고 환경변수 `DATABASE_URL` 등록
   (Supabase / Neon / Vercel Postgres 중 택1, 연결 문자열에 `?sslmode=require` 권장).
   - 테이블은 첫 호출 시 자동 생성됩니다.
   - `DATABASE_URL` 미설정 시 메모리 저장으로 동작하며 배포·재시작 시 사라집니다.
4. 배포. 프론트는 루트(`/`), API는 `/api/*` 로 서비스됩니다.

## 로컬 실행

```bash
cd vercel-app
pip install -r requirements-dev.txt
export DATABASE_URL=...        # 선택
uvicorn api.index:app --reload --port 8000
# 프론트는 public/index.html 을 정적 서버로 띄우거나,
# 같은 도메인 가정이므로 8000 포트에 /api 가 뜬 상태에서 index.html 을 열어 테스트
```

> 로컬에서 프론트와 API 도메인이 다르면 CORS 는 이미 전체 허용(`*`)으로 설정되어 있습니다.
> 다만 `index.html` 의 `API` 상수를 `http://localhost:8000` 으로 바꿔야 호출됩니다.

## ⚠️ 서버리스 제약 (중요)

- **요청 본문 크기 한도**: Vercel 서버리스 함수는 요청 본문이 **4.5MB** 로 제한됩니다.
  업로드 파일 합계가 이를 넘으면 분석이 실패합니다. 큰 파일이 필요하면
  (a) CSV로 변환해 용량을 줄이거나, (b) Vercel Blob/직접 업로드 방식으로 전환하거나,
  (c) Streamlit 그대로 Render/Railway 에 배포하는 방안을 고려하세요.
- **실행 시간**: `maxDuration` 을 60초로 설정했으나 요금제(Hobby=최대 10초)에 따라 제한됩니다.
- **Python 런타임**: Vercel 기본 Python 런타임(3.12 권장)을 사용합니다.

## 계산 로직 안전성

`api/reconcile.py` 의 계산식은 기존 `app.py` 의 "프리징 영역" 을 그대로 옮긴 것으로,
시차 결제 보정(익월 발행/전월 말일), 구다음메일 제외, PG/현금영수증/세금계산서 대사,
피벗 집계 결과가 동일하게 산출됩니다.
