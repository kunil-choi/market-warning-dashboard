# ============================================================
# collector_rates.py  –  W2 채권 자경단
# 수정: Bug6 – us10y/us2y None일 때 term_spread 계산 TypeError
# ============================================================

import logging
from datetime import datetime, timezone

from backend.data_pipeline.fred_client import get_latest_value

logger = logging.getLogger(__name__)

FALLBACK = {
    "us10y_yield":         4.45,
    "us2y_yield":          3.99,
    "term_spread":         0.46,
    "tips_10y_real_yield": 2.09,
}

THRESHOLD_10Y    = 4.5
THRESHOLD_INVERT = 0.0


def collect_rates_data() -> dict:
    logger.info("[채권자경단] 데이터 수집 시작")

    us10y = get_latest_value("DGS10",  fallback=FALLBACK["us10y_yield"])
    us2y  = get_latest_value("DGS2",   fallback=FALLBACK["us2y_yield"])
    tips  = get_latest_value("DFII10", fallback=FALLBACK["tips_10y_real_yield"])

    # ── Bug6 수정: None 방어 후 계산 ──────────────────────
    us10y = us10y if us10y is not None else FALLBACK["us10y_yield"]
    us2y  = us2y  if us2y  is not None else FALLBACK["us2y_yield"]
    tips  = tips  if tips  is not None else FALLBACK["tips_10y_real_yield"]

    term_spread = round(us10y - us2y, 2)
    is_inverted = term_spread < THRESHOLD_INVERT

    # 점수 산출
    score = 0

    if us10y >= 5.0:   score += 50
    elif us10y >= 4.5: score += 35
    elif us10y >= 4.0: score += 20
    else:              score += 5

    if is_inverted:        score += 30
    elif term_spread < 0.3: score += 10

    if tips >= 2.5:   score += 20
    elif tips >= 2.0: score += 10
    elif tips >= 1.5: score += 5

    score = min(100, score)
    grade = "RED" if score >= 70 else "YELLOW" if score >= 40 else "GREEN"

    logger.info(
        f"[채권자경단] 10Y:{us10y}% 2Y:{us2y}% "
        f"스프레드:{term_spread}%p 역전:{is_inverted} "
        f"TIPS:{tips}% 점수:{score}"
    )

    return {
        "score":               score,
        "grade":               grade,
        "us10y_yield":         us10y,
        "us2y_yield":          us2y,
        "term_spread":         term_spread,
        "tips_10y_real_yield": tips,
        "is_inverted":         is_inverted,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }
