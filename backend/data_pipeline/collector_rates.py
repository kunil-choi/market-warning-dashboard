# ============================================================
# collector_rates.py  –  W2 채권 자경단 데이터 수집
# FRED 호출을 fred_client 공통 클라이언트로 교체
# ============================================================

import logging
from datetime import datetime, timezone
from backend.data_pipeline.fred_client import get_latest_value

logger = logging.getLogger(__name__)

# ── Fallback 기본값 (FRED 완전 실패 시) ──────────────────
FALLBACK = {
    "us10y_yield":        4.45,
    "us2y_yield":         3.99,
    "term_spread":        0.46,
    "tips_10y_real_yield": 2.09,
}

# ── 점수 임계값 ───────────────────────────────────────────
THRESHOLD_10Y     = 4.5    # 10년물 임계선 (%)
THRESHOLD_INVERT  = 0.0    # 장단기 역전 기준


def collect_rates_data() -> dict:
    """
    W2 채권 자경단 데이터 수집 및 점수 산출.

    수집 항목:
      - DGS10  : 미국 10년물 국채금리
      - DGS2   : 미국 2년물 국채금리
      - DFII10 : 10년 실질금리 (TIPS)
    """
    logger.info("[채권자경단] 데이터 수집 시작")

    # ── FRED 호출 (공통 클라이언트 사용 → 자동 딜레이·재시도) ──
    us10y = get_latest_value("DGS10",  fallback=FALLBACK["us10y_yield"])
    us2y  = get_latest_value("DGS2",   fallback=FALLBACK["us2y_yield"])
    tips  = get_latest_value("DFII10", fallback=FALLBACK["tips_10y_real_yield"])

    # ── 파생 지표 계산 ────────────────────────────────────
    term_spread = round((us10y or 0) - (us2y or 0), 2)
    is_inverted = term_spread < THRESHOLD_INVERT

    # ── 점수 산출 ─────────────────────────────────────────
    score = 0

    # 10년물 금리 점수 (0~50점)
    if us10y is not None:
        if us10y >= 5.0:
            score += 50
        elif us10y >= 4.5:
            score += 35
        elif us10y >= 4.0:
            score += 20
        else:
            score += 5

    # 장단기 역전 보너스 (0~30점)
    if is_inverted:
        score += 30
    elif term_spread < 0.3:
        score += 10

    # 실질금리 보너스 (0~20점)
    if tips is not None:
        if tips >= 2.5:
            score += 20
        elif tips >= 2.0:
            score += 10
        elif tips >= 1.5:
            score += 5

    score = min(100, score)

    # ── 등급 ─────────────────────────────────────────────
    if score >= 70:
        grade = "RED"
    elif score >= 40:
        grade = "YELLOW"
    else:
        grade = "GREEN"

    logger.info(
        f"[채권자경단] 연준인하:{not is_inverted} | "
        f"10Y:{us10y}% | 2Y:{us2y}% | "
        f"스프레드:{term_spread}%p(임계:{THRESHOLD_INVERT}) | "
        f"트리거:{is_inverted}"
    )

    return {
        "score":              score,
        "grade":              grade,
        "us10y_yield":        us10y,
        "us2y_yield":         us2y,
        "term_spread":        term_spread,
        "tips_10y_real_yield": tips,
        "is_inverted":        is_inverted,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }
