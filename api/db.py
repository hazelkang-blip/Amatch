"""
정산 결과 저장 계층.

- DATABASE_URL 환경변수가 있으면 Postgres(Supabase / Neon / Vercel Postgres) 사용.
- 없으면 메모리 저장(개발용, 서버리스에서는 휘발됨)으로 폴백.
"""
import os
import json
import uuid
from datetime import datetime, timezone

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")

_USE_PG = bool(DATABASE_URL)
_MEM = {}  # 폴백용 메모리 저장소

if _USE_PG:
    import psycopg
    from psycopg.rows import dict_row


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
