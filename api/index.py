"""
AMatch FastAPI 백엔드 (Vercel Python 서버리스 함수).

엔드포인트
  GET    /api/health           상태/저장소 모드 확인 (IP 제한 제외 - 모니터링용)
  POST   /api/analyze          파일 업로드 → 정산 대사 실행(저장 안 함)
  POST   /api/results          분석 결과 저장
  GET    /api/results          저장된 결과 목록
  GET    /api/results/{id}     저장된 결과 전체 조회
  DELETE /api/results/{id}     저장된 결과 삭제

보안
  - ALLOWED_IPS 환경변수(쉼표 구분 CIDR)에 사내망 대역을 넣으면,
    /api/* (health 제외)는 해당 대역에서만 접근 가능. 비워두면 제한 없음.
  - CORS 는 ALLOWED_ORIGIN(기본: 배포 도메인)만 허용.
"""
import os
import sys
import ipaddress

# 서버리스 환경에서 같은 디렉터리의 모듈(reconcile, db)을 안전하게 import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from reconcile import run_reconciliation
import db

app = FastAPI(title="AMatch 정산 대사 API")

# --- CORS: 자기 도메인만 허용 ---
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "https://amatch-psi.vercel.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- IP 허용목록 (사내망 제한) ---
ALLOWED_NETWORKS = []
for _cidr in os.environ.get("ALLOWED_IPS", "").split(","):
    _cidr = _cidr.strip()
    if _cidr:
        try:
            ALLOWED_NETWORKS.append(ipaddress.ip_network(_cidr, strict=False))
        except ValueError:
            pass  # 잘못된 CIDR 은 무시


def _client_ip(request: Request) -> str:
    # 사내망 제한: 사내 프록시가 x-forwarded-for 앞쪽에 넣는 내부 클라이언트 IP(172.x)로 판정.
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    ip = request.headers.get("x-real-ip", "").strip()
    if ip:
        return ip
    return request.client.host if request.client else ""


@app.middleware("http")
async def ip_allowlist(request: Request, call_next):
    path = request.url.path
    # 민감 데이터가 오가는 /api/* 만 보호. health 는 모니터링 위해 제외.
    if ALLOWED_NETWORKS and path.startswith("/api/") and path != "/api/health":
        ip = _client_ip(request)
        allowed = False
        try:
            addr = ipaddress.ip_address(ip)
            allowed = any(addr in net for net in ALLOWED_NETWORKS)
        except ValueError:
            allowed = False
        if not allowed:
            return JSONResponse(
                status_code=403,
                content={"detail": f"허용되지 않은 네트워크에서의 접근입니다. (IP: {ip})"},
            )
    return await call_next(request)


@app.get("/api/health")
def health(request: Request):
    return {
        "ok": True,
        "storage": db.storage_mode(),
        "db": db.db_env_report(),
        "ip_guard": bool(ALLOWED_NETWORKS),
        "allowed_networks": [str(n) for n in ALLOWED_NETWORKS],
        # 허용목록에 넣어야 할 "지금 접속한 공인 IP" 진단용
        "your_ip": _client_ip(request),
        "x_real_ip": request.headers.get("x-real-ip", ""),
        "x_forwarded_for": request.headers.get("x-forwarded-for", ""),
    }


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
def save(body: SaveBody, request: Request):
    if not body.payload:
        raise HTTPException(status_code=400, detail="저장할 결과가 없습니다.")
    saved = db.save_result(body.payload, body.label)
    db.log_action("save", saved.get("id"), _client_ip(request), saved.get("label"))
    return saved


@app.get("/api/results")
def results(request: Request):
    db.log_action("list", None, _client_ip(request))
    return db.list_results()


@app.get("/api/results/{rid}")
def result_detail(rid: str, request: Request):
    payload = db.get_result(rid)
    if payload is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    db.log_action("view", rid, _client_ip(request))
    return payload


@app.delete("/api/results/{rid}")
def remove(rid: str, request: Request):
    if not db.delete_result(rid):
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    db.log_action("delete", rid, _client_ip(request))
    return {"ok": True, "deleted": rid}


@app.get("/api/audit")
def audit(request: Request, limit: int = 200):
    return db.list_audit(limit)
