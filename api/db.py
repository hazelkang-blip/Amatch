"""
정산 결과 저장 계층.

- Postgres 연결 문자열이 환경변수에 있으면 Postgres(Supabase / Neon / Vercel Postgres) 사용.
- 없으면 메모리 저장(개발용, 서버리스에서는 휘발됨)으로 폴백.

Vercel/Neon/Supabase 마다 주입하는 환경변수 이름이 달라서, 알려진 후보를
폭넓게 탐색하고 필요하면 구성요소(host/user/...)로 URL을 조립한다.
"""
import os
import json
import uuid
from datetime import datetime, timezone

# 다양한 제공자가 쓰는 연결 문자열 환경변수 이름 (우선순위 순)
_URL_ENV_CANDIDATES = [
    "DATABASE_URL",
    "POSTGRES_URL",
    "DATABASE_URL_UNPOOLED",
    "POSTGRES_URL_NON_POOLING",
    "NEON_DATABASE_URL",
    "POSTGRES_PRISMA_URL",  # pgbouncer 파라미터 때문에 가장 마지막
]


def _resolve_db_url():
    for k in _URL_ENV_CANDIDATES:
        v = os.environ.get(k)
        if v:
            return v, k
    # 구성요소로부터 조립
    host = os.environ.get("POSTGRES_HOST") or os.environ.get("PGHOST")
    user = os.environ.get("POSTGRES_USER") or os.environ.get("PGUSER")
    pw = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD")
    dbn = os.environ.get("POSTGRES_DATABASE") or os.environ.get("PGDATABASE")
    if host and user and dbn:
        return f"postgresql://{user}:{pw}@{host}/{dbn}?sslmode=require", "components"
    return None, None


DATABASE_URL, _DB_SOURCE = _resolve_db_url()
_USE_PG = bool(DATABASE_URL)
_MEM = {}  # 폴백용 메모리 저장소
psycopg = None
dict_row = None

if _USE_PG:
    # psycopg import 실패 시 함수 전체가 죽지 않도록 메모리 저장으로 폴백
    try:
        import psycopg
        from psycopg.rows import dict_row
    except Exception as e:
        _USE_PG = False
        _DB_SOURCE = f"{_DB_SOURCE} (psycopg import 실패: {e})"


def _conn():
    # sslmode 요구하는 호스트(Supabase/Neon) 대비
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)


def init_db():
    if not _USE_PG:
        return
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settlement_results (
                id           TEXT PRIMARY KEY,
                label        TEXT,
                target_month TEXT,
                created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
                summary      JSONB,
                payload      JSONB
            )
            """
        )


def save_result(payload, label=None):
    rid = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    target_month = payload.get("target_month")
    summary = payload.get("summary", {})
    label = label or f"{target_month} 정산"

    if not _USE_PG:
        rec = {
            "id": rid, "label": label, "target_month": target_month,
            "created_at": now.isoformat(), "summary": summary, "payload": payload,
        }
        _MEM[rid] = rec
        return {k: rec[k] for k in ("id", "label", "target_month", "created_at", "summary")}

    init_db()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO settlement_results (id, label, target_month, created_at, summary, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (rid, label, target_month, now, json.dumps(summary), json.dumps(payload)),
        )
    return {"id": rid, "label": label, "target_month": target_month,
            "created_at": now.isoformat(), "summary": summary}


def list_results():
    if not _USE_PG:
        rows = sorted(_MEM.values(), key=lambda r: r["created_at"], reverse=True)
        return [{k: r[k] for k in ("id", "label", "target_month", "created_at", "summary")} for r in rows]

    init_db()
    with _conn() as conn:
        cur = conn.execute(
            "SELECT id, label, target_month, created_at, summary FROM settlement_results ORDER BY created_at DESC"
        )
        rows = cur.fetchall()
    for r in rows:
        if isinstance(r.get("created_at"), datetime):
            r["created_at"] = r["created_at"].isoformat()
    return rows


def get_result(rid):
    if not _USE_PG:
        rec = _MEM.get(rid)
        return rec["payload"] if rec else None

    init_db()
    with _conn() as conn:
        cur = conn.execute("SELECT payload FROM settlement_results WHERE id = %s", (rid,))
        row = cur.fetchone()
    return row["payload"] if row else None


def delete_result(rid):
    if not _USE_PG:
        return _MEM.pop(rid, None) is not None

    init_db()
    with _conn() as conn:
        cur = conn.execute("DELETE FROM settlement_results WHERE id = %s", (rid,))
        return cur.rowcount > 0


def storage_mode():
    return "postgres" if _USE_PG else "memory"


def db_env_report():
    """진단용: 어떤 DB 환경변수가 존재하는지(이름만) 보고."""
    url_keys = [k for k in _URL_ENV_CANDIDATES if os.environ.get(k)]
    comp_keys = [k for k in ("POSTGRES_HOST", "POSTGRES_USER", "POSTGRES_DATABASE", "PGHOST")
                 if os.environ.get(k)]
    return {"source": _DB_SOURCE, "url_keys_present": url_keys, "component_keys_present": comp_keys}
