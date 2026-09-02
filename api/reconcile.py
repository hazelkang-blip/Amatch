"""
AMatch 정산 대사 핵심 로직.

기존 Streamlit app.py 의 계산 로직을 그대로 이식하되,
- 입력: 파일 바이트(파일명 포함)
- 출력: JSON 직렬화 가능한 dict
로 변경했습니다. 계산식 자체는 변경하지 않았습니다(프리징 영역 유지).
"""
import io
import math
import re
from datetime import datetime

import numpy as np
import pandas as pd


# ----------------------------------------------------------------------------
# 헬퍼
# ----------------------------------------------------------------------------
def clean_id(val):
    if pd.isna(val) or str(val).lower() in ["nan", "none", ""]:
        return ""
    s = str(val).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


# ----------------------------------------------------------------------------
# 세금계산서 발행 ERP 원본 정규화
#   SAP    : '거래처 1' = 사업자발급번호, '선수금' = 발행금액(공급대가),
#             '전기일' = 세금계산서 신청일자
#   더존    : '품의내역' 괄호 안 숫자 = 사업자발급번호,
#             '장부금액'(= '거래금액') = 발행금액. 별도 판매금액(공급가) 열은 없음.
#             '회계일자' = 세금계산서 신청일자
#   두 양식 모두 취소분은 음수로 노출되므로 부호 그대로 합산한다.
# ----------------------------------------------------------------------------
_BIZ_IN_PAREN = re.compile(r"\(([0-9][0-9\-]*)\)")


def _biz_from_note(text):
    """더존 '품의내역'에서 괄호 안 사업자발급번호 추출 (마지막 괄호 기준)."""
    found = _BIZ_IN_PAREN.findall(str(text))
    return found[-1] if found else ""


def _date_range_str(series):
    """날짜 시리즈 -> 'YYYY-MM-DD' 또는 'YYYY-MM-DD ~ YYYY-MM-DD' (없으면 '-')."""
    d = pd.to_datetime(pd.Series(series), errors="coerce").dropna()
    if d.empty:
        return "-"
    lo, hi = d.min().strftime("%Y-%m-%d"), d.max().strftime("%Y-%m-%d")
    return lo if lo == hi else f"{lo} ~ {hi}"


def find_request_date_col(columns):
    """세금계산서 '신청일자' 성격의 열 이름을 찾는다 (예: '세금계산서 신청일자')."""
    return next((c for c in columns if "신청" in str(c) and "일" in str(c)), None)


def normalize_erp(df):
    """ERP 원본(SAP/더존) -> ['사업자번호', '발행금액', '신청일자'] 열이 추가된 DataFrame, 양식명."""
    df = df.copy()
    df.columns = df.columns.str.strip()

    if "거래처 1" in df.columns and "선수금" in df.columns:
        erp_format = "SAP"
        biz = df["거래처 1"].apply(clean_id)
        amt = df["선수금"]
        date_cands = ("전기일", "증빙일")
    elif "품의내역" in df.columns:
        erp_format = "더존"
        amt_col = next((c for c in ("장부금액", "거래금액") if c in df.columns), None)
        if amt_col is None:
            raise KeyError("장부금액 (또는 거래금액)")
        biz = df["품의내역"].apply(_biz_from_note).apply(clean_id)
        amt = df[amt_col]
        date_cands = ("회계일자",)
    else:
        raise KeyError("거래처 1 / 품의내역 (인식 가능한 ERP 양식이 아닙니다)")

    df["사업자번호"] = biz
    df["발행금액"] = pd.to_numeric(amt.astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    # 세금계산서 신청일자 (더존 '회계일자' = 신청일자). 없으면 NaT.
    date_col = next((c for c in date_cands if c in df.columns), None)
    df["신청일자"] = pd.to_datetime(df[date_col], errors="coerce") if date_col else pd.NaT

    # 합계/총계 행 제거: 사업자번호가 비었거나(더존 총계행·SAP 합계행) 합계 텍스트인 행
    df = df[~df["사업자번호"].str.contains("합계|합산|Total", na=False, case=False)]
    df = df[df["사업자번호"] != ""]
    return df.reset_index(drop=True), erp_format


def _read_bytes(file_bytes, filename):
    """업로드된 파일 바이트를 DataFrame 으로 로드."""
    if file_bytes is None:
        return None
    bio = io.BytesIO(file_bytes)
    name = (filename or "").lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(bio)
        return pd.read_excel(bio)
    except Exception:
        # csv/xlsx 추정 실패 시 양쪽 시도
        try:
            bio.seek(0)
            return pd.read_excel(bio)
        except Exception:
            bio.seek(0)
            return pd.read_csv(bio)


def _sanitize(obj):
    """NaN / inf / numpy 타입을 JSON 안전한 값으로 변환."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    if obj is pd.NaT:
        return None
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _records(df):
    """DataFrame -> list[dict] (JSON 안전)."""
    if df is None or df.empty:
        return []
    return _sanitize(df.replace({np.nan: None}).to_dict("records"))


def _pivot_payload(df):
    """피벗 테이블 -> {columns, rows}. 인덱스를 첫 컬럼으로 펼친다."""
    if df is None or df.empty:
        return {"columns": [], "rows": []}
    flat = df.reset_index()
    columns = [str(c) for c in flat.columns]
    rows = _sanitize(flat.replace({np.nan: None}).to_dict("records"))
    return {"columns": columns, "rows": rows}


# ----------------------------------------------------------------------------
# 메인 로직
# ----------------------------------------------------------------------------
def run_reconciliation(*, bill, sap, rec, axz, pg_files=None, target_month_str):
    """
    bill / sap / rec / axz : {"bytes": b"...", "name": "file.xlsx"} (필수 4종)
    pg_files               : list of 같은 형태 dict (선택)
    target_month_str       : "YYYY-MM"
    반환                    : JSON 직렬화 가능한 결과 dict
    """
    pg_files = pg_files or []

    df_axz = _read_bytes(axz["bytes"], axz["name"]); df_axz.columns = df_axz.columns.str.strip()
    df_sap = _read_bytes(sap["bytes"], sap["name"]); df_sap.columns = df_sap.columns.str.strip()
    df_k_rec = _read_bytes(rec["bytes"], rec["name"]); df_k_rec.columns = df_k_rec.columns.str.strip()
    df_k_bill = _read_bytes(bill["bytes"], bill["name"]); df_k_bill.columns = df_k_bill.columns.str.strip()
    df_pg_all = (
        pd.concat([_read_bytes(pf["bytes"], pf["name"]) for pf in pg_files], ignore_index=True)
        if pg_files else pd.DataFrame()
    )

    # --- 계산 로직 프리징 영역 (app.py 와 동일) ---
    df_axz["거래일시"] = pd.to_datetime(df_axz["거래일시"], errors="coerce")
    df_axz["결제금액"] = pd.to_numeric(df_axz["결제금액"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    df_axz["환불금액"] = pd.to_numeric(df_axz["환불금액"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    df_axz["결제상태"] = df_axz["결제상태"].fillna("")

    def calc_final_amt(row, target_m):
        row_month = row["거래일시"].strftime("%Y-%m") if pd.notnull(row["거래일시"]) else ""
        if row_month == target_m:
            return row["결제금액"] - row["환불금액"]
        else:
            return -row["환불금액"]
    df_axz["최종매출인식금액"] = df_axz.apply(lambda r: calc_final_amt(r, target_month_str), axis=1)

    for c in ["결제ID", "User ID", "사업자번호"]:
        if c in df_axz.columns:
            df_axz[c] = df_axz[c].apply(clean_id)

    is_old_daum_text = df_axz["상품명"].fillna("").str.contains("구다음메일") | df_axz["비고"].fillna("").str.contains("구다음결제")
    old_daum_ids = set(df_axz.loc[is_old_daum_text, "결제ID"].dropna().unique()) - {"", "nan"}
    is_old_daum_final = is_old_daum_text | df_axz["결제ID"].isin(old_daum_ids)

    df_old_daum = df_axz[is_old_daum_final].copy()
    df_axz_target = df_axz[~is_old_daum_final].copy()

    # 1. PG 요약
    if not df_pg_all.empty:
        df_pg_all.columns = df_pg_all.columns.str.strip()
        df_pg_all["정제_ID"] = df_pg_all["결제번호"].astype(str).str.replace("DKPG", "", regex=False).apply(clean_id)
        df_pg_all["금액"] = pd.to_numeric(df_pg_all["결제금액"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        pg_sum = df_pg_all.groupby("정제_ID")["금액"].sum().reset_index()
    else:
        pg_sum = pd.DataFrame(columns=["정제_ID", "금액"])

    df_k_bill["결제금액"] = pd.to_numeric(df_k_bill["결제금액"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    bill_summary = df_k_bill.groupby("캐시구분")["결제금액"].sum().reset_index()
    axz_by_method = df_axz_target.groupby("결제수단")["최종매출인식금액"].sum().reset_index()
    mapping = {"휴대폰": "모바일", "카카오페이머니": "머니", "신용카드": "신용카드", "카카오페이 카드": "카카오페이(카드)", "카카오페이카드": "카카오페이(카드)"}
    axz_by_method["mapping_key"] = axz_by_method["결제수단"].map(mapping)
    pg_summary_table = pd.merge(axz_by_method, bill_summary, left_on="mapping_key", right_on="캐시구분", how="outer").fillna(0)
    pg_summary_table["차액"] = pg_summary_table["최종매출인식금액"] - pg_summary_table["결제금액"]
    pg_summary_table["결제유형"] = pg_summary_table["결제수단"].replace(0, np.nan).combine_first(pg_summary_table["캐시구분"])
    pg_summary_table = pg_summary_table[["결제유형", "최종매출인식금액", "결제금액", "차액"]]
    pg_summary_table = pd.concat([pg_summary_table, pd.DataFrame([{"결제유형": "총 합계", "최종매출인식금액": pg_summary_table["최종매출인식금액"].sum(), "결제금액": pg_summary_table["결제금액"].sum(), "차액": pg_summary_table["차액"].sum()}])], ignore_index=True)

    pg_merge = pd.merge(df_axz_target, pg_sum, left_on="결제ID", right_on="정제_ID", how="outer").fillna(0)
    pg_merge["ID_Final"] = pg_merge["결제ID"].replace(0, np.nan).combine_first(pg_merge["정제_ID"].replace(0, np.nan))
    pg_merge["상세차액_원본"] = pg_merge["최종매출인식금액"] - pg_merge["금액"]
    mismatch_pg = pg_merge[pg_merge["상세차액_원본"] != 0].copy()

    # 2. 현금영수증 대사
    raw_axz_rec_df = df_axz[df_axz["세금유형"].isin(["현금영수증", "자진발급"])]
    raw_total_axz_rec = raw_axz_rec_df["최종매출인식금액"].sum()

    df_k_rec["요청액"] = pd.to_numeric(df_k_rec["요청금액"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
    if "전송상태" in df_k_rec.columns:
        df_k_rec = df_k_rec[df_k_rec["전송상태"].fillna("").str.upper().str.contains("PG실패") == False]
    df_k_rec["계정ID_clean"] = df_k_rec["계정ID"].apply(clean_id)

    # 구다음메일(현금영수증 채널='다음메일') 건 분리 → 정산 제외 대상
    # 중복결제 시스템 취소분 중 현금영수증만 남은 건으로, 이후 대사/합계 계산에서 제외한다.
    if "채널" in df_k_rec.columns:
        is_daum_rec = df_k_rec["채널"].fillna("").astype(str).str.strip() == "다음메일"
        df_daum_rec = df_k_rec[is_daum_rec].copy()
        df_k_rec = df_k_rec[~is_daum_rec].copy()
    else:
        df_daum_rec = pd.DataFrame()

    # 중복 제거 키: 계정·전송유형·요청액에 '승인일시'(없으면 거래일시)까지 포함해
    # 같은 시각 다채널 중복만 제거하고, 서로 다른 시각의 실제 별건 결제/취소는 보존한다.
    # (중복결제 등으로 동일 금액 결제가 2건이면 예전엔 1건으로 합쳐져 대사가 틀어졌음)
    _dedup_keys = ["계정ID_clean", "전송유형", "요청액"]
    for _dc in ("승인일시", "거래일시"):
        if _dc in df_k_rec.columns:
            _dedup_keys.append(_dc)
            break
    if "채널" in df_k_rec.columns:
        df_k_rec = df_k_rec.sort_values("채널").drop_duplicates(subset=_dedup_keys, keep="first")
    else:
        df_k_rec = df_k_rec.drop_duplicates(subset=_dedup_keys, keep="first")

    total_k_rec = df_k_rec[df_k_rec["전송유형"] == "결제"]["요청액"].sum() - df_k_rec[df_k_rec["전송유형"] == "취소"]["요청액"].abs().sum()

    df_k_rec["보정액"] = df_k_rec.apply(lambda r: -abs(r["요청액"]) if r["전송유형"] == "취소" else r["요청액"], axis=1)
    df_k_rec["_취소건수"] = (df_k_rec["전송유형"] == "취소").astype(int)
    agg_dict = {"보정액": "sum", "_취소건수": "sum"}
    if "채널" in df_k_rec.columns:
        agg_dict["채널"] = "first"
    # 카카오 일자는 '승인일시'(결제 승인일)를 우선 사용 — 합산(전월 말일) 판별·표시 기준
    if "승인일시" in df_k_rec.columns:
        agg_dict["승인일시"] = "max"
    elif "거래일시" in df_k_rec.columns:
        agg_dict["거래일시"] = "max"

    k_rec_sum = df_k_rec.groupby("계정ID_clean").agg(agg_dict).reset_index()
    k_rec_sum = k_rec_sum.rename(columns={"승인일시": "카카오일시", "거래일시": "카카오일시"}, errors="ignore")

    a_rec = raw_axz_rec_df.groupby("User ID").agg({"최종매출인식금액": "sum", "거래일시": "max"}).reset_index()
    m_rec = pd.merge(a_rec, k_rec_sum, left_on="User ID", right_on="계정ID_clean", how="outer")
    # 금액·ID 컬럼만 0으로 채우고, 날짜(거래일시/카카오일시)는 NaT 유지 →
    # combine_first 가 DAUM 없는 건에서 카카오 승인일시로 정상 폴백하도록 함
    _fill0 = [c for c in ["최종매출인식금액", "보정액", "_취소건수", "User ID", "계정ID_clean", "채널"] if c in m_rec.columns]
    m_rec[_fill0] = m_rec[_fill0].fillna(0)
    m_rec["ID_Display"] = m_rec["User ID"].replace(0, np.nan).combine_first(m_rec["계정ID_clean"].replace(0, np.nan))

    for col in ["거래일시", "카카오일시"]:
        if col in m_rec.columns:
            m_rec[col] = pd.to_datetime(m_rec[col], errors="coerce")
    # 거래일시(DAUM 결제일)와 발행일시(카카오 승인일시)를 각각 표시 — 소거/합산 판별을 눈으로 구분
    m_rec["거래일시_str"] = m_rec["거래일시"].dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    if "카카오일시" in m_rec.columns:
        m_rec["발행일시_str"] = m_rec["카카오일시"].dt.strftime("%Y-%m-%d %H:%M").fillna("-")
    else:
        m_rec["발행일시_str"] = "-"

    m_rec["차액"] = m_rec["최종매출인식금액"] - m_rec["보정액"]
    err_rec = m_rec[m_rec["차액"] != 0].copy()

    # 시차보정 판별용 날짜 기준
    # 카카오 현금영수증의 승인일시 = '발행일시'. 전월 말일 결제분은 정산월 1일에 발행되고,
    # 정산월 말일 결제분은 익월 1일에 발행되어 정산월 rec 에서 빠진다.
    _tp = pd.Period(target_month_str, freq="M")
    _last_day = _tp.end_time.normalize()       # 정산월 말일 (예: 2025-07-31)
    _first_day = _tp.start_time.normalize()    # 정산월 1일  (예: 2025-07-01)

    def _is_day(ts, ref):
        if ts is None or pd.isna(ts):
            return False
        try:
            return pd.Timestamp(ts).normalize() == ref
        except Exception:
            return False

    def get_reason(row):
        axz, kakao = row["최종매출인식금액"], row["보정액"]
        # 결제내역 상태 확인필요: 카카오는 결제취소를 반영(순액 차감)했으나 DAUM 결제내역엔 취소 미반영
        # → DAUM 인식액이 카카오 실제 순액보다 큼. 결제내역 추출 후 취소된 건으로 DAUM 상태 갱신 필요.
        if row.get("_취소건수", 0) > 0 and axz > kakao:
            return "결제내역 상태 확인필요"
        # 익월 발행 예정건(소거): DAUM 거래일시(결제일)가 정산월 '말일' & 카카오 발행 없음
        # → 발행이 익월 1일로 넘어가 정산월 rec 에 없음
        if axz == 34900 and kakao == 0 and _is_day(row.get("거래일시"), _last_day):
            return "익월 발행 예정건 (소거)"
        # 전월 말일 결제건(합산): 카카오 발행일시(승인일시)가 정산월 '1일' & DAUM 결제내역 없음
        # → 전월 말일 결제분이 정산월 1일에 발행되어 정산월 rec 에만 존재
        if axz == 0 and kakao == 34900 and _is_day(row.get("카카오일시"), _first_day):
            return "전월 말일 결제건 (합산)"
        if axz == 0 and kakao < 0 and str(row.get("채널", "")).strip() == "다음메일":
            return "구다음결제건"
        return "기타 확인 필요"

    if not err_rec.empty:
        err_rec["사유"] = err_rec.apply(get_reason, axis=1)
        end_of_month_sum = err_rec[err_rec["사유"] == "익월 발행 예정건 (소거)"]["최종매출인식금액"].sum()
        prev_month_end_sum = err_rec[err_rec["사유"] == "전월 말일 결제건 (합산)"]["보정액"].sum()
    else:
        err_rec["사유"] = []
        end_of_month_sum = prev_month_end_sum = 0

    adjusted_axz_rec = raw_total_axz_rec - end_of_month_sum + prev_month_end_sum

    # 3. 세금계산서(ERP) 대사 — SAP / 더존 양식 자동 인식
    # 신청일자는 대사 계산에 쓰지 않고 참고용으로만 나란히 표시한다
    # (더존 '회계일자' = 신청일자, DAUM 결제내역에 신청일자 열이 생기면 자동 인식).
    df_erp, erp_format = normalize_erp(df_sap)
    df_a_tax = df_axz_target[df_axz_target["세금유형"] == "세금계산서"]
    daum_req_col = find_request_date_col(df_a_tax.columns)

    a_agg = {"최종매출인식금액": ("최종매출인식금액", "sum")}
    if daum_req_col:
        a_agg["신청일자_DAUM"] = (daum_req_col, _date_range_str)
    a_tax = df_a_tax.groupby("사업자번호").agg(**a_agg).reset_index()

    s_tax = df_erp.groupby("사업자번호").agg(
        발행금액=("발행금액", "sum"), 신청일자_ERP=("신청일자", _date_range_str),
    ).reset_index().rename(columns={"사업자번호": "사업자번호_ERP"})

    m_tax = pd.merge(a_tax, s_tax, left_on="사업자번호", right_on="사업자번호_ERP", how="outer")
    _num_cols = ["최종매출인식금액", "발행금액"]
    m_tax[_num_cols] = m_tax[_num_cols].fillna(0)
    for _dc in ["신청일자_DAUM", "신청일자_ERP"]:
        if _dc in m_tax.columns:
            m_tax[_dc] = m_tax[_dc].fillna("-")
    # 한쪽에만 있는 사업자번호는 결측이므로 반대쪽 값으로 폴백
    _blank = ["", "nan", 0]
    m_tax["사업자_통합"] = m_tax["사업자번호"].replace(_blank, np.nan).combine_first(m_tax["사업자번호_ERP"].replace(_blank, np.nan))
    m_tax["차액"] = m_tax["최종매출인식금액"] - m_tax["발행금액"]
    err_tax = m_tax[m_tax["차액"] != 0]

    # 4. 피벗
    def get_status_pivot(df, status_name):
        f = df[df["결제상태"] == status_name]
        if f.empty:
            return pd.DataFrame()
        return pd.pivot_table(f, values="최종매출인식금액", index="결제수단", columns="세금유형", aggfunc="sum", fill_value=0, margins=True, margins_name="합계")

    pivot_all = pd.pivot_table(df_axz_target, values="최종매출인식금액", index="결제수단", columns="세금유형", aggfunc="sum", fill_value=0, margins=True, margins_name="합계")

    total_axz = float(df_axz_target["최종매출인식금액"].sum())
    total_k_bill = float(bill_summary["결제금액"].sum())

    # 표시용 가공
    if not mismatch_pg.empty:
        mismatch_pg_disp = mismatch_pg[["ID_Final", "결제수단", "최종매출인식금액", "금액", "상세차액_원본"]].rename(
            columns={"ID_Final": "결제번호", "최종매출인식금액": "DAUM", "금액": "카카오원본", "상세차액_원본": "차액"})
    else:
        mismatch_pg_disp = pd.DataFrame(columns=["결제번호", "결제수단", "DAUM", "카카오원본", "차액"])

    if not err_rec.empty:
        err_rec_disp = err_rec[["거래일시_str", "발행일시_str", "ID_Display", "최종매출인식금액", "보정액", "차액", "사유"]].rename(
            columns={"거래일시_str": "거래일시", "발행일시_str": "발행일시", "ID_Display": "계정 ID", "최종매출인식금액": "DAUM", "보정액": "카카오원본"})
        reasons = list(pd.unique(err_rec["사유"]))
    else:
        err_rec_disp = pd.DataFrame(columns=["거래일시", "발행일시", "계정 ID", "DAUM", "카카오원본", "차액", "사유"])
        reasons = []

    # 표시 컬럼: 사업자번호 · (신청일자 참고열) · DAUM 인식액 · ERP 발행액 · 차액
    erp_amt_label = f"{erp_format} 원본"
    tax_cols, tax_ren = ["사업자_통합"], {"사업자_통합": "사업자번호", "발행금액": erp_amt_label}
    if daum_req_col:
        tax_cols.append("신청일자_DAUM"); tax_ren["신청일자_DAUM"] = "신청일자(DAUM)"
    tax_cols.append("신청일자_ERP"); tax_ren["신청일자_ERP"] = f"신청일자({erp_format})"
    tax_cols += ["최종매출인식금액", "발행금액", "차액"]
    err_tax_columns = [tax_ren.get(c, c) for c in tax_cols]

    if not err_tax.empty:
        err_tax_disp = err_tax[tax_cols].rename(columns=tax_ren)
    else:
        err_tax_disp = pd.DataFrame(columns=err_tax_columns)

    if not df_old_daum.empty:
        old_daum_disp = df_old_daum[["거래일시", "결제수단", "결제상태", "User ID", "결제ID", "상품명", "세금유형", "최종매출인식금액"]].copy()
    else:
        old_daum_disp = pd.DataFrame(columns=["거래일시", "결제수단", "결제상태", "User ID", "결제ID", "상품명", "세금유형", "최종매출인식금액"])

    # 현금영수증 채널='다음메일' 정산제외 건 (구다음결제건)
    old_daum_rec_cols = ["일시", "계정 ID", "채널", "전송유형", "요청금액"]
    if not df_daum_rec.empty:
        daum_date_col = next((c for c in ["승인일시", "거래일시"] if c in df_daum_rec.columns), None)
        pick = ([daum_date_col] if daum_date_col else []) + ["계정ID_clean", "채널", "전송유형", "요청액"]
        old_daum_rec_disp = df_daum_rec[pick].copy()
        ren = {"계정ID_clean": "계정 ID", "요청액": "요청금액"}
        if daum_date_col:
            ren[daum_date_col] = "일시"
        old_daum_rec_disp = old_daum_rec_disp.rename(columns=ren)
        if "일시" not in old_daum_rec_disp.columns:
            old_daum_rec_disp["일시"] = "-"
        old_daum_rec_disp = old_daum_rec_disp[old_daum_rec_cols]
    else:
        old_daum_rec_disp = pd.DataFrame(columns=old_daum_rec_cols)

    result = {
        "target_month": target_month_str,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "erp_format": erp_format,
        "summary": {
            "total_axz": total_axz,
            "total_k_bill": total_k_bill,
            "main_diff": total_axz - total_k_bill,
            "raw_total_axz_rec": float(raw_total_axz_rec),
            "end_of_month_sum": float(end_of_month_sum),
            "prev_month_end_sum": float(prev_month_end_sum),
            "adjusted_axz_rec": float(adjusted_axz_rec),
            "total_k_rec": float(total_k_rec),
            "diff_rec": float(adjusted_axz_rec - total_k_rec),
        },
        "pg_summary": _records(pg_summary_table),
        "mismatch_pg": _records(mismatch_pg_disp),
        "err_rec": _records(err_rec_disp),
        "err_rec_reasons": reasons,
        "err_tax": _records(err_tax_disp),
        "err_tax_columns": err_tax_columns,
        "err_tax_money_columns": ["최종매출인식금액", erp_amt_label, "차액"],
        "old_daum": _records(old_daum_disp),
        "old_daum_rec": _records(old_daum_rec_disp),
        "pivot_all": _pivot_payload(pivot_all),
        "pivot_success": _pivot_payload(get_status_pivot(df_axz_target, "결제완료")),
        "pivot_cancel": _pivot_payload(get_status_pivot(df_axz_target, "취소완료")),
        "pivot_partial": _pivot_payload(get_status_pivot(df_axz_target, "부분취소")),
    }
    return _sanitize(result)
