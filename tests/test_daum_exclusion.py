"""현금영수증 채널='다음메일' 정산제외 처리 검증.

PR 변경분(reconcile.run_reconciliation / excel_export.build_workbook)이
다음메일 건을 정산에서 제외하고 정산제외 대상(old_daum_rec)에 노출하는지 확인.
서버 없이 실행: python tests/test_daum_exclusion.py
"""
import io, os, sys
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from reconcile import run_reconciliation  # noqa
from excel_export import build_workbook  # noqa

TM = "2025-05"
def xls(df):
    b = io.BytesIO(); df.to_excel(b, index=False); return b.getvalue()

axz = pd.DataFrame([
    {"거래일시": "2025-05-04 11:00", "결제수단": "카카오페이머니", "결제상태": "결제완료",
     "결제금액": 34900, "환불금액": 0, "User ID": "u2", "결제ID": "P2",
     "사업자번호": "", "세금유형": "현금영수증", "상품명": "메일", "비고": ""},
    {"거래일시": "2025-04-20 09:00", "결제수단": "신용카드", "결제상태": "취소완료",
     "결제금액": 20000, "환불금액": 20000, "User ID": "u5", "결제ID": "P5",
     "사업자번호": "", "세금유형": "현금영수증", "상품명": "메일", "비고": ""},
])
bill = pd.DataFrame([{"캐시구분": "머니", "결제금액": 34900}])
# u9: 중복결제 시스템취소분 중 현금영수증만 남은 구다음메일 건 (채널='다음메일')
rec = pd.DataFrame([
    {"계정ID": "u2", "전송유형": "결제", "요청금액": 34900, "전송상태": "성공",
     "채널": "메일", "승인일시": "2025-05-04 11:05"},
    {"계정ID": "u5", "전송유형": "취소", "요청금액": 20000, "전송상태": "성공",
     "채널": "메일", "승인일시": "2025-05-20 09:10"},
    {"계정ID": "u9", "전송유형": "취소", "요청금액": 34900, "전송상태": "성공",
     "채널": "다음메일", "승인일시": "2025-05-15 09:10"},
])
sap = pd.DataFrame([{"거래처 1": "1112233444", "선수금": 0}])

kw = dict(
    bill={"bytes": xls(bill), "name": "bill.xlsx"},
    sap={"bytes": xls(sap), "name": "sap.xlsx"},
    rec={"bytes": xls(rec), "name": "rec.xlsx"},
    axz={"bytes": xls(axz), "name": "axz.xlsx"},
    target_month_str=TM,
)
r = run_reconciliation(**kw)

# 1) 다음메일 건이 정산제외(old_daum_rec)에 노출
assert len(r["old_daum_rec"]) == 1, r["old_daum_rec"]
assert r["old_daum_rec"][0]["계정 ID"] == "u9"
assert r["old_daum_rec"][0]["채널"] == "다음메일"

# 2) 카카오 실제 발행액에서 제외: 34900(결제) - 20000(취소) = 14900 (u9 -34900 제외)
assert abs(r["summary"]["total_k_rec"] - 14900) < 1e-6, r["summary"]["total_k_rec"]

# 3) 상세 불일치 사유에 '구다음결제건'이 더는 없음(정산제외로 이동)
assert "구다음결제건" not in (r["err_rec_reasons"] or []), r["err_rec_reasons"]

# 4) 채널 컬럼이 없는 rec 파일도 정상(하위호환)
kw2 = dict(kw); kw2["rec"] = {"bytes": xls(rec.drop(columns=["채널"])), "name": "rec.xlsx"}
assert run_reconciliation(**kw2)["old_daum_rec"] == []

# 5) 엑셀 내보내기 정상 생성
assert len(build_workbook(**kw)) > 0

print("old_daum_rec:", r["old_daum_rec"])
print("total_k_rec :", r["summary"]["total_k_rec"], "(다음메일 34,900 제외됨)")
print("\n=== 다음메일 정산제외 검증 통과 ===")
