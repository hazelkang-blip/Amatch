"""현금영수증 대사 케이스 검증.

케이스1: 중복결제 수동삭제 — 동일 금액 결제 2건이 dedup 으로 합쳐지지 않고
         결제2 - 취소1 = 34,900 이 AXZ 34,900 과 일치해야 함 (err 없음).
케이스2: 정산월 결제취소가 카카오엔 반영, AXZ 결제내역엔 미반영 →
         '결제내역 상태 확인필요' 로 분류.
실행: python tests/test_recon_cases.py
"""
import io, os, sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from reconcile import run_reconciliation  # noqa
from excel_export import build_workbook  # noqa

def xls(df):
    b = io.BytesIO(); df.to_excel(b, index=False); return b.getvalue()

def axz_row(uid, pid, status, pay, refund, dt):
    return {"거래일시": dt, "결제수단": "카카오페이머니", "결제상태": status, "결제금액": pay,
            "환불금액": refund, "User ID": uid, "결제ID": pid, "사업자번호": "",
            "세금유형": "현금영수증", "상품명": "메일", "비고": ""}

bill = pd.DataFrame([{"캐시구분": "머니", "결제금액": 0}])
sap = pd.DataFrame([{"거래처 1": "1", "선수금": 0}])
def run(axz, rec):
    return run_reconciliation(
        bill={"bytes": xls(bill), "name": "b"}, sap={"bytes": xls(sap), "name": "s"},
        rec={"bytes": xls(rec), "name": "r"}, axz={"bytes": xls(axz), "name": "a"},
        target_month_str="2025-07")

# ---- 케이스1: 중복결제 수동삭제 → 일치 ----
axz1 = pd.DataFrame([
    axz_row("u1", "P1a", "취소완료", 34900, 34900, "2025-07-10 10:00"),
    axz_row("u1", "P1b", "결제완료", 34900, 0, "2025-07-10 10:00"),
])
rec1 = pd.DataFrame([
    {"계정ID": "u1", "전송유형": "결제", "요청금액": 34900, "전송상태": "성공", "채널": "메일", "승인일시": "2025-07-10 10:01"},
    {"계정ID": "u1", "전송유형": "결제", "요청금액": 34900, "전송상태": "성공", "채널": "메일", "승인일시": "2025-07-10 10:02"},
    {"계정ID": "u1", "전송유형": "취소", "요청금액": 34900, "전송상태": "성공", "채널": "메일", "승인일시": "2025-07-10 10:05"},
])
r1 = run(axz1, rec1)
reasons1 = [x["사유"] for x in r1["err_rec"]]
assert not r1["err_rec"], f"케이스1은 일치여야 함: {r1['err_rec']}"
assert abs(r1["summary"]["total_k_rec"] - 34900) < 1e-6, r1["summary"]["total_k_rec"]

# ---- 케이스2: 결제취소 AXZ 미반영 → 결제내역 상태 확인필요 ----
axz2 = pd.DataFrame([axz_row("u2", "P2", "결제완료", 34900, 0, "2025-07-12 10:00")])
rec2 = pd.DataFrame([
    {"계정ID": "u2", "전송유형": "결제", "요청금액": 34900, "전송상태": "성공", "채널": "메일", "승인일시": "2025-07-12 10:01"},
    {"계정ID": "u2", "전송유형": "취소", "요청금액": 34900, "전송상태": "성공", "채널": "메일", "승인일시": "2025-07-13 09:00"},
])
r2 = run(axz2, rec2)
by_id2 = {x["계정 ID"]: x for x in r2["err_rec"]}
assert by_id2.get("u2", {}).get("사유") == "결제내역 상태 확인필요", r2["err_rec"]

# 엑셀 생성도 정상
assert len(build_workbook(bill={"bytes": xls(bill), "name": "b"}, sap={"bytes": xls(sap), "name": "s"},
                          rec={"bytes": xls(rec2), "name": "r"}, axz={"bytes": xls(axz2), "name": "a"},
                          target_month_str="2025-07")) > 0

print("케이스1 err건수:", len(r1["err_rec"]), "(0=일치)")
print("케이스2 사유:", by_id2["u2"]["사유"])
print("\n=== 현금영수증 케이스1·2 검증 통과 ===")
