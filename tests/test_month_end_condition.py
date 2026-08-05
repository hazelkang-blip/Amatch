"""익월 발행 예정(소거)/전월 말일(합산) '말일' 날짜 조건 검증.

- 소거: 거래일시가 정산월 말일인 34,900 미발행건만 소거
- 합산: 카카오일시가 전월 말일 또는 정산월 1일인 34,900 발행건만 합산
- 말일이 아닌 건은 '기타 확인 필요'로 남아 검토 대상이 됨
실행: python tests/test_month_end_condition.py
"""
import io, os, sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from reconcile import run_reconciliation  # noqa
from excel_export import build_workbook  # noqa

TM = "2025-07"
def xls(df):
    b = io.BytesIO(); df.to_excel(b, index=False); return b.getvalue()

def axz_row(uid, pid, dt):
    return {"거래일시": dt, "결제수단": "카카오페이머니", "결제상태": "결제완료",
            "결제금액": 34900, "환불금액": 0, "User ID": uid, "결제ID": pid,
            "사업자번호": "", "세금유형": "현금영수증", "상품명": "메일", "비고": ""}

# AXZ: 말일 미발행(소거 대상), 비말일 미발행(소거 아님)
axz = pd.DataFrame([
    axz_row("u_end", "P_end", "2025-07-31 23:50"),  # 말일 → 소거
    axz_row("u_mid", "P_mid", "2025-07-03 10:00"),  # 비말일 → 기타
])
bill = pd.DataFrame([{"캐시구분": "머니", "결제금액": 0}])
sap = pd.DataFrame([{"거래처 1": "1112233444", "선수금": 0}])
# 카카오 현금영수증: 정산월초 발행(합산 대상), 월중 발행(합산 아님)
rec = pd.DataFrame([
    {"계정ID": "u_prev", "전송유형": "결제", "요청금액": 34900, "전송상태": "성공",
     "채널": "메일", "승인일시": "2025-06-30 09:00"},   # 승인일시(=결제일) 전월 말일 → 합산
    {"계정ID": "u_spur", "전송유형": "결제", "요청금액": 34900, "전송상태": "성공",
     "채널": "메일", "승인일시": "2025-07-15 09:00"},   # 월중 발행 → 기타
])

kw = dict(
    bill={"bytes": xls(bill), "name": "bill.xlsx"},
    sap={"bytes": xls(sap), "name": "sap.xlsx"},
    rec={"bytes": xls(rec), "name": "rec.xlsx"},
    axz={"bytes": xls(axz), "name": "axz.xlsx"},
    target_month_str=TM,
)
r = run_reconciliation(**kw)
s = r["summary"]
reason = {row["계정 ID"]: row["사유"] for row in r["err_rec"]}
print("사유:", reason)
print("end_of_month_sum:", s["end_of_month_sum"], "| prev_month_end_sum:", s["prev_month_end_sum"])

# 소거: 말일(u_end)만 34,900, 비말일(u_mid)은 소거 아님
assert reason.get("u_end") == "익월 발행 예정건 (소거)", reason
assert reason.get("u_mid") == "기타 확인 필요", reason
assert abs(s["end_of_month_sum"] - 34900) < 1e-6, s["end_of_month_sum"]

# 합산: 정산월초(u_prev)만 34,900, 월중(u_spur)은 합산 아님
assert reason.get("u_prev") == "전월 말일 결제건 (합산)", reason
assert reason.get("u_spur") == "기타 확인 필요", reason
assert abs(s["prev_month_end_sum"] - 34900) < 1e-6, s["prev_month_end_sum"]

# 엑셀(SUMIF 근거식 포함) 생성 정상
assert len(build_workbook(**kw)) > 0

print("\n=== 말일 조건(소거/합산) 검증 통과 ===")
