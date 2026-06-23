"""
collector_korea.py
한국 주식시장 위기경보 — K1~K4 데이터 수집

K1: 코스피 선도주 압축  (yfinance: ^KS11 vs ARIRANG 동일가중 프록시)
K2: 국고채 감시 & 금리  (FRED: IRLTLT01KRM156N, IRSTCI01KRM156N)
K3: 사모펀드 & PF 위험  (수동 + Claude 뉴스검색)
K4: 대형 공모주 유동성  (수동 관리)
"""

import logging
import re
import json
from datetime import datetime, timezone, date

import yfinance as yf
import anthropic

from backend.data_pipeline.fred_client import get_latest_value

logger = logging.getLogger(__name__)

# ── FRED 시리즈 (한국) ────────────────────────────────────
KR_10Y_SERIES = "IRLTLT01KRM156N"   # 한국 10년물 국채금리
KR_3Y_SERIES  = "IRSTCI01KRM156N"   # 한국 3년물 (단기 정책금리 근사)

# ── 폴백 값 ──────────────────────────────────────────────
KR_10Y_FALLBACK = 2.85
KR_3Y_FALLBACK  = 2.65
CD91_FALLBACK   = 3.42

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
        "valuation_bn": 2.5,   # 조원
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
    """코스피 시가총액 가중 vs 동일가중 스프레드 측정"""
    logger.info("K1 코스피 선도주 압축 수집 시작")

    # yfinance로 코스피 + 삼성전자(대형주 대표) + KODEX200(동일가중 프록시)
    try:
        ks11  = yf.Ticker("^KS11")
        hist_ks = ks11.history(period="1y")

        # 연초 대비 수익률
        this_year = str(datetime.now().year)
        year_start = hist_ks[hist_ks.index >= f"{this_year}-01-01"]
        if len(year_start) >= 2:
            kospi_ytd = round((year_start["Close"].iloc[-1] / year_start["Close"].iloc[0] - 1) * 100, 2)
        else:
            kospi_ytd = 0.0

        # 상위 5 종목 비중: 삼성전자(005930.KS), SK하이닉스, LG에너지솔루션, 삼성바이오, 현대차
        top5_tickers = ["005930.KS", "000660.KS", "373220.KS", "207940.KS", "005380.KS"]
        top5_caps = []
        total_kospi_cap = 0
        for t in top5_tickers:
            try:
                info = yf.Ticker(t).fast_info
                mc = getattr(info, "market_cap", 0) or 0
                top5_caps.append(mc)
                total_kospi_cap += mc
            except Exception:
                top5_caps.append(0)

        # 코스피 전체 시총으로 나누기 (근사: KR_MARKET_CAP_TR × 1e12 KRW, 환율 1350 적용)
        kospi_cap_usd = KR_MARKET_CAP_TR * 1e12 / 1350
        top5_weight = round(sum(top5_caps) / kospi_cap_usd * 100, 1) if kospi_cap_usd > 0 else 38.5

        # 동일가중 프록시: KODEX 200 ETF (069500.KS)
        kodex = yf.Ticker("069500.KS")
        hist_kodex = kodex.history(period="1y")
        year_kodex = hist_kodex[hist_kodex.index >= f"{this_year}-01-01"]
        if len(year_kodex) >= 2:
            keqw_ytd = round((year_kodex["Close"].iloc[-1] / year_kodex["Close"].iloc[0] - 1) * 100, 2)
        else:
            keqw_ytd = kospi_ytd * 0.85  # 근사

        spread = round(kospi_ytd - keqw_ytd, 2)

    except Exception as e:
        logger.warning("K1 yfinance 수집 실패, 폴백: %s", e)
        kospi_ytd   = 8.5
        keqw_ytd    = 5.2
        spread      = 3.3
        top5_weight = 38.5

    # 백분위 (간이 계산: 역사적 평균 대비)
    spread_percentile = min(int(abs(spread) / 10 * 100), 95) if spread > 0 else 20

    # 점수 산출
    if spread >= 8:
        s_spread = 80
    elif spread >= 5:
        s_spread = 60
    elif spread >= 3:
        s_spread = 35
    elif spread >= 1:
        s_spread = 15
    else:
        s_spread = 5

    s_pct    = min(int(spread_percentile * 0.8), 80)
    s_top5   = 80 if top5_weight >= 45 else 50 if top5_weight >= 40 else 25 if top5_weight >= 30 else 10

    score = round(s_spread * 0.50 + s_pct * 0.30 + s_top5 * 0.20)
    score = min(score, 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":              score,
        "grade":              grade,
        "kospi_ytd":          kospi_ytd,
        "keqw_ytd":           keqw_ytd,
        "current_spread":     spread,
        "spread_percentile":  spread_percentile,
        "top5_weight_pct":    top5_weight,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }


# ── K2: 국고채 감시 & 금리 ───────────────────────────────

def collect_k2_data() -> dict:
    logger.info("K2 국고채 & 금리 수집 시작")

    kr10y = get_latest_value(KR_10Y_SERIES, fallback=KR_10Y_FALLBACK)
    kr3y  = get_latest_value(KR_3Y_SERIES,  fallback=KR_3Y_FALLBACK)
    cd91  = CD91_FALLBACK  # FRED에 CD91일물 없음 → 수동

    term_spread = round(kr10y - kr3y, 2)
    is_inverted = term_spread < 0

    # 점수
    if kr10y >= 4.0:
        s_rate = 80
    elif kr10y >= 3.5:
        s_rate = 55
    elif kr10y >= 3.0:
        s_rate = 30
    else:
        s_rate = 10

    if is_inverted:
        s_inv = 80
    elif term_spread < 0.2:
        s_inv = 40
    else:
        s_inv = 5

    s_cd = 50 if cd91 >= 4.0 else 25 if cd91 >= 3.5 else 5

    score = round(s_rate * 0.40 + s_inv * 0.40 + s_cd * 0.20)
    score = min(score, 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":        score,
        "grade":        grade,
        "kr10y_yield":  round(kr10y, 2),
        "kr3y_yield":   round(kr3y,  2),
        "term_spread":  term_spread,
        "is_inverted":  is_inverted,
        "cd91_rate":    cd91,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }


# ── K3: 한국 PF & 사모펀드 위험 + 뉴스검색 ──────────────

def search_kr_pf_news() -> dict:
    """Claude AI 웹검색으로 한국 부동산 PF·사모펀드 환매 제한 뉴스 탐지"""
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    "Search for recent news (within 3 months) about: "
                    "1) Korean real estate PF (부동산 PF) delinquency or default crisis 2025 2026 "
                    "2) Korean private fund (사모펀드) redemption suspension or gating 2025 2026 "
                    "3) Korean construction company default or workout 2025 2026. "
                    "Return ONLY JSON: "
                    "{\"has_event\": bool, "
                    "\"risk_level\": \"none\"|\"low\"|\"medium\"|\"high\", "
                    "\"events\": [max 3 brief descriptions in Korean], "
                    "\"summary\": \"one sentence in Korean\"}"
                )
            }],
        )
        full_text = " ".join(b.text for b in response.content if hasattr(b, "text"))
        match = re.search(r"\{.*\}", full_text, re.S)
        if match:
            result = json.loads(match.group(0))
            bump = {"none": 0, "low": 5, "medium": 15, "high": 25}.get(result.get("risk_level","none"), 0)
            return {**result, "risk_bump": bump}
    except Exception as e:
        logger.warning("K3 뉴스 검색 실패: %s", e)
    return {"has_event": False, "risk_level": "none", "events": [], "summary": "검색 불가", "risk_bump": 0}


def collect_k3_data() -> dict:
    logger.info("K3 사모펀드 & PF 위험 수집 시작")

    pf_news = search_kr_pf_news()
    pf_delq = PF_DELINQUENCY_PCT
    kbdc    = KBDC_DISCOUNT_PCT
    dsr     = DSR_AVG_PCT

    # 점수
    s_pf   = 100 if pf_delq >= 5 else 70 if pf_delq >= 3 else 40 if pf_delq >= 1.5 else 10
    s_kbdc = 80 if kbdc >= 20 else 50 if kbdc >= 10 else 25 if kbdc >= 5 else 5
    s_dsr  = 70 if dsr >= 50 else 40 if dsr >= 45 else 20 if dsr >= 40 else 5

    score = round(s_pf * 0.35 + s_kbdc * 0.25 + s_dsr * 0.20)
    score = min(score + pf_news.get("risk_bump", 0), 100)
    grade = "위험" if score >= 70 else "경고" if score >= 55 else "주의" if score >= 40 else "정상"

    return {
        "score":               score,
        "grade":               grade,
        "pf_delinquency_pct":  pf_delq,
        "pf_update_date":      PF_UPDATE_DATE,
        "kbdc_discount_pct":   kbdc,
        "dsr_avg_pct":         dsr,
        "pf_gate_news":        pf_news,
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
