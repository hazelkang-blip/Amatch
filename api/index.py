"""
AMatch FastAPI 백엔드 (Vercel Python 서버리스 함수).

1회성 정산 대사 분석 전용. (저장/조회 기능 없음, 데이터 미보관)
  GET   /api/health    상태 확인
  POST  /api/analyze   파일 업로드 → 정산 대사 실행 후 결과 반환
"""
import os
import sys

# 서버리스 환경에서 같은 디렉터리의 모듈(reconcile)을 안전하게 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import urllib.parse

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from typing import List

from reconcile import run_reconciliation
from excel_export import build_workbook

app = FastAPI(title="AMatch 정산 대사 API")

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://amatch-psi.vercel.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/analyze")
async def analyze(
    target_month: str,
    bill: UploadFile = File(...),
    sap: UploadFile = File(...),
    rec: UploadFile = File(...),
    axz: UploadFile = File(...),
    pg_files: List[UploadFile] = File(default=[]),
):
    async def pack(f: UploadFile):
        return {"bytes": await f.read(), "name": f.filename}

    try:
        result = run_reconciliation(
            bill=await pack(bill),
            sap=await pack(sap),
            rec=await pack(rec),
            axz=await pack(axz),
            pg_files=[await pack(f) for f in pg_files] if pg_files else [],
            target_month_str=target_month,
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"필수 컬럼 누락 또는 형식 오류: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"분석 오류: {e}")
    return result


@app.post("/api/export")
async def export_excel(
    target_month: str,
    bill: UploadFile = File(...),
    sap: UploadFile = File(...),
    rec: UploadFile = File(...),
    axz: UploadFile = File(...),
    pg_files: List[UploadFile] = File(default=[]),
):
    async def pack(f: UploadFile):
        return {"bytes": await f.read(), "name": f.filename}

    try:
        xlsx = build_workbook(
            bill=await pack(bill),
            sap=await pack(sap),
            rec=await pack(rec),
            axz=await pack(axz),
            pg_files=[await pack(f) for f in pg_files] if pg_files else [],
            target_month_str=target_month,
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=f"필수 컬럼 누락 또는 형식 오류: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"엑셀 생성 오류: {e}")

    fname = urllib.parse.quote(f"AMatch_정산_{target_month}.xlsx")
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )
