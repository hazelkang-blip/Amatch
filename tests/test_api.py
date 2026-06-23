"""FastAPI 엔드포인트 통합 테스트 (메모리 저장 모드)."""
import io, sys, os
import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "api"))
os.environ.pop("DATABASE_URL", None)
os.environ.pop("POSTGRES_URL", None)
import index  # noqa

client = TestClient(index.app)

def xls(df):
    b = io.BytesIO(); df.to_excel(b, index=False); return b.getvalue()

axz = pd.DataFrame([{"거래일시":"2025-05-03 10:00","결제수단":"신용카드","결제상태":"결제완료","결제금액":100000,
    "환불금액":0,"User ID":"u1","결제ID":"P1","사업자번호":"1112233444","세금유형":"세금계산서","상품명":"메일","비고":""}])
bill = pd.DataFrame([{"캐시구분":"신용카드","결제금액":100000}])
rec = pd.DataFrame([{"계정ID":"u2","전송유형":"결제","요청금액":34900,"전송상태":"성공","채널":"메일","승인일시":"2025-05-04 11:05"}])
sap = pd.DataFrame([{"거래처 1":"1112233444","선수금":100000}])

# 1) health
r = client.get("/api/health"); assert r.status_code == 200, r.text
print("health:", r.json())

# 2) analyze
files = {
    "bill": ("bill.xlsx", xls(bill)), "sap": ("sap.xlsx", xls(sap)),
    "rec": ("rec.xlsx", xls(rec)), "axz": ("axz.xlsx", xls(axz)),
}
r = client.post("/api/analyze?target_month=2025-05", files=files)
assert r.status_code == 200, r.text
result = r.json()
print("analyze total_axz:", result["summary"]["total_axz"])

# 3) save
r = client.post("/api/results", json={"label": "5월 테스트", "payload": result})
assert r.status_code == 200, r.text
saved = r.json(); rid = saved["id"]
print("saved id:", rid, "label:", saved["label"])

# 4) list
r = client.get("/api/results"); assert r.status_code == 200
lst = r.json(); assert len(lst) == 1, lst
print("list count:", len(lst))

# 5) get detail
r = client.get(f"/api/results/{rid}"); assert r.status_code == 200
assert r.json()["summary"]["total_axz"] == result["summary"]["total_axz"]
print("detail ok")

# 6) delete
r = client.delete(f"/api/results/{rid}"); assert r.status_code == 200, r.text
r = client.get("/api/results"); assert len(r.json()) == 0
print("delete ok")

# 7) 404
r = client.get("/api/results/nope"); assert r.status_code == 404
print("404 ok")

print("\n=== API 테스트 전부 통과 ===")
