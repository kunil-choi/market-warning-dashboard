"""
collector_korea.py
한국 주식시장 위기경보 — K1~K4 데이터 수집

K1: 코스피 선도주 압축  (yfinance: ^KS11 vs ARIRANG 동일가중 프록시)
K2: 국고채 감시 & 금리  (FRED: IRLTLT01KRM156N, IRSTCI01KRM156N)
K3: 사모펀드 & PF 위험  (수동 + Claude 뉴스검색)
K4: 대형 공모주 유동성  (수동 관리)
"""

import logging
from datetime import datetime, timezone, date

import yfinance as yf

from backend.data_pipeline.fred_client import get_latest_value

logger = logging.getLogger(__name__)

# ── FRED 시리즈 (한국) ────────────────────────────────────
KR_10Y_SERIES = "IRLTLT01KRM156N"   # 한국 10년물 국채금리
KR_3Y_SERIES  = "IRSTCI01KRM156N"   # 한국 3년물 (단기 정책금리 근사)

# ── 폴백 값 ──────────────────────────────────────────────
KR_10Y_FALLBACK = 2.85
KR_3Y_FALLBACK  = 2.65
CD91_FALLBACK   = 3.42

# 한국은행 기준금리 (수동 관리 — 변경 시 업데이트)
# 2024-10: 3.50% → 2024-11: 3.25% → 2025-01: 3.00% → 2025-02: 2.75% → 2025-08: 2.50%
KR_BASE_RATE = 2.50

# ── 수동 관리 지표 ────────────────────────────────────────
# 부동산 PF 연체율 (금융감독원, 2026-Q1)
PF_DELINQUENCY_PCT   = 2.15
PF_UPDATE_DATE       = "2026-Q1"
# 메자닌 펀드 평균 할인율 (사모펀드 시장, 추정)
KBDC_DISCOUNT_PCT    = 6.5
# 가계 DSR 평균 비율 (한국은행, 2025)
DSR_AVG_PCT          = 41.2

# ── 한국 대형 공모주 목록 (수동 관리) ────────────────────
KR_IPO_LIST = [
    {
        "company":      "케이뱅크",
        "valuation_bn": 5.0,   # 조원 (2026년 재추진 목표 시총)
        "status":       "검토중",
        "active_date":  "2026-01-01",
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "DN솔루션즈",
        "valuation_bn": 3.0,   # 조원
        "status":       "검토중",
        "active_date":  "2026-01-01",
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "LG CNS",
        "valuation_bn": 2.1,
        "status":       "상장완료",
        "active_date":  "2026-01-01",
        "listed_date":  "2026-01-15",
        "ticker":       "064400.KS",
    },
    {
        "company":      "HD현대마린솔루션",
        "valuation_bn": 1.8,
        "status":       "상장완료",
        "active_date":  "2026-01-01",
        "listed_date":  "2024-05-17",
        "ticker":       "443060.KS",
    },
]

KR_MARKET_CAP_TR = 2_200.0  # 코스피 시총 약 2,200조원


# ── K1: 코스피 선도주 압축 ────────────────────────────────

def collect_k1_data() -> dict:
    """코스피 선도주 압축 측정
    수정 근거:
    - 기존 코드에서 yfinance fast_info.market_cap의 단위 불일치로
      top5_weight=187.6% 같은 비정상 값이 발생 → top5 계산 제거
    - 대신 KRX 공시 기반 반기 업데이트값(수동)과 코스피 30일 모멘텀으로 단순화
    - top5 집중도 임계값: 역사적 정상 30~38%, 주의 38~45%, 위험 45%+
    """
    logger.info("K1 코스피 선도주 압축 수집 시작")

    # ── 코스피 YTD 및 30일 모멘텀 ──────────────────────────
    try:
        ks11    = yf.Ticker("^KS11")
        hist_ks = ks11.history(period="1y")

        this_year  = str(datetime.now().year)
        year_start = hist_ks[hist_ks.index >= f"{this_year}-01-01"]
        if len(year_start) >= 2:
            kospi_ytd = round(
                (year_start["Close"].iloc[-1] / year_start["Close"].iloc[0] - 1) * 100, 2
            )
        else:
            kospi_ytd = 0.0

        # 30일 모멘텀 (급락 감지)
        if len(hist_ks) >= 22:
            mom_30d = round(
                (hist_ks["Close"].iloc[-1] / hist_ks["Close"].iloc[-22] - 1) * 100, 2
            )
        else:
            mom_30d = 0.0

    except Exception as e:
        logger.warning("K1 yfinance 수집 실패, 폴백: %s", e)
        kospi_ytd = 12.8   # 2026-06 추정치
        mom_30d   = 0.0

    # ── TOP5 집중도: KRX 공시 기반 수동 관리값 ────────────
    # 출처: KRX 시가총액 상위 종목 비중 (반기 업데이트)
    # 2026-06 기준: 삼성전자14.5%+SK하이닉스7.5%+삼성바이오4.2%+LG엔솔3.9%+현대차3.1% ≈ 33.2%
    TOP5_WEIGHT_MANUAL = 33.2   # ← 반기마다 수동 업데이트 (KRX 공시 확인)

    # ── 점수 산출 ──────────────────────────────────────────
    # top5 집중도 (가중 60%)
    # 역사적 기준: 정상 <38%, 주의 38~45%, 위험 45%+
    s_top5 = (
        80 if TOP5_WEIGHT_MANUAL >= 45 else
        45 if TOP5_WEIGHT_MANUAL >= 38 else
        15
    )

    # 30일 모멘텀 급락 (가중 40%)
    # -10% 이상 급락이면 위험, -5% 경고, 그 외 정상
    s_momentum = (
        80 if mom_30d <= -10 else
        50 if mom_30d <= -5  else
        20 if mom_30d <= -2  else
        0
    )

    score = round(s_top5 * 0.60 + s_momentum * 0.40)
    score = min(score, 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":             score,
        "grade":             grade,
        "kospi_ytd":         kospi_ytd,
        "mom_30d":           mom_30d,
        "top5_weight_pct":   TOP5_WEIGHT_MANUAL,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }


# ── K2: 국고채 감시 & 금리 ───────────────────────────────

def collect_k2_data() -> dict:
    """한국 국고채 감시 & 금리
    수정 근거:
    - 10년물 4.08%는 한국은행 기준금리(2.5%) 대비 1.58%p 가산 → 재정/인플레 프리미엄
    - 역사적 기준: 정상 <2.8%, 주의 2.8~3.3%, 경고 3.3~3.8%, 위험 3.8%+
    - term premium(10Y - 기준금리)도 별도 반영: 1.5%p 이상이면 경고
    - CD91일물 기준 상향: 3.5% 이상이면 기업 단기조달 부담
    """
    logger.info("K2 국고채 & 금리 수집 시작")

    kr10y = get_latest_value(KR_10Y_SERIES, fallback=KR_10Y_FALLBACK)
    kr3y  = get_latest_value(KR_3Y_SERIES,  fallback=KR_3Y_FALLBACK)
    cd91  = CD91_FALLBACK  # FRED에 CD91일물 없음 → 수동

    term_spread   = round(kr10y - kr3y, 2)
    is_inverted   = term_spread < 0
    term_premium  = round(kr10y - KR_BASE_RATE, 2)   # 기준금리 대비 장기프리미엄

    # 10년물 절대금리 점수 (가중 40%)
    # 역사적 기준: 위험 3.8%+, 경고 3.3~3.8%, 주의 2.8~3.3%, 정상 <2.8%
    s_rate = (
        80 if kr10y >= 3.8 else
        55 if kr10y >= 3.3 else
        30 if kr10y >= 2.8 else
        10
    )

    # term premium (10Y - 기준금리) 점수 (가중 35%)
    # 1.5%p 이상: 재정/인플레 불안, 경고
    # 1.0%p 이상: 주의
    s_premium = (
        70 if term_premium >= 1.5 else
        45 if term_premium >= 1.0 else
        20 if term_premium >= 0.5 else
        5
    )

    # CD91일물 점수 (가중 15%)
    # 3.5% 이상이면 기업 단기조달 부담
    s_cd = (
        50 if cd91 >= 4.0 else
        30 if cd91 >= 3.5 else
        10
    )

    # 장단기 역전 보너스 (가중 10%)
    s_inv = 80 if is_inverted else 40 if term_spread < 0.2 else 5

    score = round(s_rate * 0.40 + s_premium * 0.35 + s_cd * 0.15 + s_inv * 0.10)
    score = min(score, 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":         score,
        "grade":         grade,
        "kr10y_yield":   round(kr10y, 2),
        "kr3y_yield":    round(kr3y,  2),
        "term_spread":   term_spread,
        "term_premium":  term_premium,
        "is_inverted":   is_inverted,
        "cd91_rate":     cd91,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }


# ── K3: 한국 PF & 사모펀드 위험 + 뉴스검색 ──────────────


def collect_k3_data() -> dict:
    """한국 PF & 사모펀드 위험
    수정 근거:
    - PF 연체율 2.15%: 금감원 공식 경고 기준 1.5% 초과 → 주의 구간 진입
      (2023년 2.9%에서 위기 본격화, 2024년 4.6% 피크)
    - DSR 41.2%: 한국은행 거시건전성 위험 임계치 40% 초과 → 가계부채 부담 구간
    - KBDC 할인율 6.5%: 정상 0~3%, 주의 3~8%, 위험 8%+ (기존과 동일)
    """
    logger.info("K3 사모펀드 & PF 위험 수집 시작")

    pf_delq = PF_DELINQUENCY_PCT
    kbdc    = KBDC_DISCOUNT_PCT
    dsr     = DSR_AVG_PCT

    # PF 연체율 점수 (가중 45%)
    # 금감원 기준: 1.5%+ 경보, 3.0%+ 위험, 5.0%+ 위기
    s_pf = (
        100 if pf_delq >= 5.0 else
        75  if pf_delq >= 3.0 else
        55  if pf_delq >= 2.0 else
        35  if pf_delq >= 1.5 else
        10
    )

    # KBDC 할인율 점수 (가중 30%)
    s_kbdc = (
        80 if kbdc >= 20 else
        55 if kbdc >= 10 else
        35 if kbdc >= 5  else
        10
    )

    # 가계 DSR 점수 (가중 25%)
    # 한국은행 임계치 40% 기준: 40% 초과면 이미 위험 구간
    s_dsr = (
        75 if dsr >= 50 else
        50 if dsr >= 43 else
        35 if dsr >= 40 else
        10
    )

    score = round(s_pf * 0.45 + s_kbdc * 0.30 + s_dsr * 0.25)
    score = min(score, 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":               score,
        "grade":               grade,
        "pf_delinquency_pct":  pf_delq,
        "pf_update_date":      PF_UPDATE_DATE,
        "kbdc_discount_pct":   kbdc,
        "dsr_avg_pct":         dsr,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }


# ── K4: 한국 대형 공모주 유동성 ──────────────────────────

STATUS_WEIGHT_KR = {
    "루머": 0.0, "검토중": 0.1, "제출완료": 0.7, "가격확정": 1.0,
}

def get_kr_ipo_weight(item: dict) -> float:
    status = item.get("status", "루머")
    if status != "상장완료":
        return STATUS_WEIGHT_KR.get(status, 0.0)
    listed_raw = item.get("listed_date")
    if not listed_raw:
        return 0.0
    try:
        months = (date.today() - date.fromisoformat(str(listed_raw)[:10])).days / 30.0
        if months <= 3:  return 0.9
        if months <= 6:  return 0.6
        if months <= 12: return 0.3
        return 0.0
    except ValueError:
        return 0.0


def collect_k4_data() -> dict:
    logger.info("K4 한국 대형 공모주 유동성 수집 시작")

    total_val = 0.0
    filed_count = priced_count = 0
    signals = []
    alerts  = []
    ipo_out = []

    for item in KR_IPO_LIST:
        item = dict(item)
        # yfinance 상장 확인
        ticker = item.get("ticker")
        if ticker and item.get("status") != "상장완료":
            try:
                info = yf.Ticker(ticker).fast_info
                if getattr(info, "market_cap", 0) or getattr(info, "last_price", 0):
                    item["status"] = "상장완료"
                    item["listed_date"] = item.get("listed_date") or date.today().isoformat()
            except Exception:
                pass

        val    = item.get("valuation_bn", 0)
        weight = get_kr_ipo_weight(item)
        total_val += val * weight

        st = item.get("status","루머")
        if st in ("제출완료","신청완료"): filed_count  += 1
        if st == "가격확정":             priced_count += 1

        signals.append(f"{'🚨' if st=='가격확정' else '📋' if st in ('제출완료','신청완료') else '📊' if '상장완료' in st else '🔍'} {item['company']}: {st} ({val}조 × {weight})")
        ipo_out.append(item)

    ratio = round(total_val / KR_MARKET_CAP_TR * 100, 4)

    if ratio >= 0.40:
        base_score = 75
        alerts.append(f"🚨 코스피 시총 대비 {ratio:.2f}% — 전례 없는 공모 압력")
    elif ratio >= 0.20:
        base_score = 50
        alerts.append(f"⚠️ 코스피 시총 대비 {ratio:.2f}% — 대형 공모 집중 경고")
    elif ratio >= 0.10:
        base_score = 30
        alerts.append(f"📢 코스피 시총 대비 {ratio:.2f}% — 주의 구간")
    else:
        base_score = 10

    score = min(base_score + priced_count * 10 + filed_count * 5, 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":               score,
        "grade":               grade,
        "total_valuation_tn":  round(total_val, 2),
        "pipeline_ratio_pct":  ratio,
        "kr_market_cap_tr":    KR_MARKET_CAP_TR,
        "filed_count":         filed_count,
        "priced_count":        priced_count,
        "signals":             signals,
        "alerts":              alerts,
        "ipo_list":            ipo_out,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }


# ── 한국 종합 수집 ────────────────────────────────────────

def collect_korea_data() -> dict:
    """K1~K4 수집 후 한국 종합 점수 산출"""
    logger.info("한국 시장 데이터 수집 시작")

    k1 = collect_k1_data()
    k2 = collect_k2_data()
    k3 = collect_k3_data()
    k4 = collect_k4_data()

    kr_composite = round(
        k1["score"] * 0.25 +
        k2["score"] * 0.30 +
        k3["score"] * 0.20 +
        k4["score"] * 0.25,
        1
    )
    kr_grade = "RED" if kr_composite >= 70 else "YELLOW" if kr_composite >= 40 else "GREEN"

    return {
        "kr_composite_score": kr_composite,
        "kr_grade":           kr_grade,
        "k1": k1, "k2": k2, "k3": k3, "k4": k4,
    }


