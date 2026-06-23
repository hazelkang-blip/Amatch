"""
AMatch FastAPI 백엔드 (Vercel Python 서버리스 함수).

엔드포인트
  GET    /api/health           상태/저장소 모드 확인
  POST   /api/analyze          파일 업로드 → 정산 대사 실행(저장 안 함)
  POST   /api/results          분석 결과 저장
  GET    /api/results          저장된 결과 목록
  GET    /api/results/{id}     저장된 결과 전체 조회
  DELETE /api/results/{id}     저장된 결과 삭제
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from reconcile import run_reconciliation
import db

app = FastAPI(title="AMatch 정산 대사 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "storage": db.storage_mode()}


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


class SaveBody(BaseModel):
    label: Optional[str] = None
    payload: dict


@app.post("/api/results")
def save(body: SaveBody):
    if not body.payload:
        raise HTTPException(status_code=400, detail="저장할 결과가 없습니다.")
    return db.save_result(body.payload, body.label)


@app.get("/api/results")
def results():
    return db.list_results()


@app.get("/api/results/{rid}")
def result_detail(rid: str):
    payload = db.get_result(rid)
    if payload is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return payload


@app.delete("/api/results/{rid}")
def remove(rid: str):
    if not db.delete_result(rid):
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    return {"ok": True, "deleted": rid}
