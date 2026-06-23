"""합성 데이터로 reconcile 로직 검증."""
import io, sys, os
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
from reconcile import run_reconciliation  # noqa

TM = "2025-05"

def xls(df):
    b = io.BytesIO(); df.to_excel(b, index=False); return b.getvalue()

# AXZ 내부결제: 다양한 케이스
axz = pd.DataFrame([
    # 정산월 정상 결제 (신용카드/세금계산서)
    {"거래일시":"2025-05-03 10:00","결제수단":"신용카드","결제상태":"결제완료","결제금액":100000,"환불금액":0,
     "User ID":"u1","결제ID":"P1","사업자번호":"1112233444","세금유형":"세금계산서","상품명":"메일","비고":""},
    # 현금영수증 정상 (양쪽 일치)
    {"거래일시":"2025-05-04 11:00","결제수단":"카카오페이머니","결제상태":"결제완료","결제금액":34900,"환불금액":0,
     "User ID":"u2","결제ID":"P2","사업자번호":"","세금유형":"현금영수증","상품명":"메일","비고":""},
    # 익월 발행 예정건(소거): AXZ 34900, 카카오 0
    {"거래일시":"2025-05-31 23:50","결제수단":"카카오페이머니","결제상태":"결제완료","결제금액":34900,"환불금액":0,
     "User ID":"u3","결제ID":"P3","사업자번호":"","세금유형":"현금영수증","상품명":"메일","비고":""},
    # 구다음메일 제외건
    {"거래일시":"2025-05-10 09:00","결제수단":"신용카드","결제상태":"결제완료","결제금액":5000,"환불금액":0,
     "User ID":"u4","결제ID":"P4","사업자번호":"","세금유형":"현금영수증","상품명":"구다음메일 서비스","비고":""},
    # 전월 결제분 이번달 환불(취소완료)
    {"거래일시":"2025-04-20 09:00","결제수단":"신용카드","결제상태":"취소완료","결제금액":20000,"환불금액":20000,
     "User ID":"u5","결제ID":"P5","사업자번호":"","세금유형":"현금영수증","상품명":"메일","비고":""},
])

# 카카오 빌링 요약 (캐시구분별)
bill = pd.DataFrame([
    {"캐시구분":"신용카드","결제금액":100000},
    {"캐시구분":"머니","결제금액":34900+34900},  # u2 + u3 가 빌링엔 둘다 잡힘
])

# 카카오 현금영수증 발행 데이터
rec = pd.DataFrame([
    {"계정ID":"u2","전송유형":"결제","요청금액":34900,"전송상태":"성공","채널":"메일","승인일시":"2025-05-04 11:05"},
    # u3 는 카카오 발행 없음 → 익월 발행 예정건(소거)
    {"계정ID":"u5","전송유형":"취소","요청금액":20000,"전송상태":"성공","채널":"메일","승인일시":"2025-05-20 09:10"},
])

# SAP (선수금)
sap = pd.DataFrame([
    {"거래처 1":"1112233444","선수금":100000},
    {"거래처 1":"합계","선수금":100000},  # 합계행 제거되어야 함
])

# PG 상세
pg = pd.DataFrame([
    {"결제번호":"DKPGP1","결제금액":100000},
    {"결제번호":"P2","결제금액":34900},
])

result = run_reconciliation(
    bill={"bytes": xls(bill), "name": "bill.xlsx"},
    sap={"bytes": xls(sap), "name": "sap.xlsx"},
    rec={"bytes": xls(rec), "name": "rec.xlsx"},
    axz={"bytes": xls(axz), "name": "axz.xlsx"},
    pg_files=[{"bytes": xls(pg), "name": "pg.xlsx"}],
    target_month_str=TM,
)

import json
s = result["summary"]
print("=== SUMMARY ===")
print(json.dumps(s, ensure_ascii=False, indent=2))

# --- 기대값 검증 ---
# df_axz_target = 구다음(P4) 제외한 나머지
# 최종매출인식금액: P1=100000, P2=34900, P3=34900, P5(전월결제 취소)= -환불 = -20000
expected_total_axz = 100000 + 34900 + 34900 - 20000
assert abs(s["total_axz"] - expected_total_axz) < 1e-6, (s["total_axz"], expected_total_axz)

# 빌링 합계
assert abs(s["total_k_bill"] - (100000+34900+34900)) < 1e-6, s["total_k_bill"]

# 현금영수증 원본: 세금유형 현금/자진발급 → P2(34900)+P3(34900)+P4(5000, 구다음이지만 df_axz 전체 기준 포함)+P5(-20000)
# raw_axz_rec_df 는 df_axz(전체) 기준이므로 P4 포함됨 (원본 로직과 동일)
expected_raw_rec = 34900 + 34900 + 5000 - 20000
assert abs(s["raw_total_axz_rec"] - expected_raw_rec) < 1e-6, (s["raw_total_axz_rec"], expected_raw_rec)

# 익월 발행 예정건(소거): u3 (AXZ 34900, 카카오 0) → 34900
assert abs(s["end_of_month_sum"] - 34900) < 1e-6, s["end_of_month_sum"]

# JSON 직렬화 가능 확인
json.dumps(result, ensure_ascii=False)

print("\n=== 검증 통과 ===")
print("pg_summary rows:", len(result["pg_summary"]))
print("err_rec rows:", len(result["err_rec"]), "reasons:", result["err_rec_reasons"])
print("err_tax rows:", len(result["err_tax"]))
print("old_daum rows:", len(result["old_daum"]))
print("pivot_all cols:", result["pivot_all"]["columns"])
