# ============================================================
# collector_credit.py  –  W3 사모 크레딧 데이터 수집
# 수정: 함수 내부 임포트 제거 → 상단 임포트로 통일
# ============================================================

import logging
from datetime import datetime, timezone

from backend.data_pipeline.fred_client import get_latest_value, fetch_series

logger = logging.getLogger(__name__)

# ── Fallback 기본값 (FRED 2026-05-28 실측값) ─────────────
FALLBACK = {
    "hy_spread_bps": 272.0,
    "ig_spread_bps":  77.0,
}

HY_DANGER  = 400
HY_WARNING = 300
HY_NORMAL  = 200


def collect_credit_data() -> dict:
    logger.info("[사모크레딧] 데이터 수집 시작")

    # ── FRED 호출 (% → ×100 = bps) ───────────────────────
    hy_spread_bps = get_latest_value(
        "BAMLH0A0HYM2",
        fallback=FALLBACK["hy_spread_bps"] / 100,
        multiplier=100.0,
    )
    ig_spread_bps = get_latest_value(
        "BAMLC0A0CM",
        fallback=FALLBACK["ig_spread_bps"] / 100,
        multiplier=100.0,
    )

    # None 방어
    if hy_spread_bps is None:
        hy_spread_bps = FALLBACK["hy_spread_bps"]
        logger.warning(f"[사모크레딧] HY fallback 사용: {hy_spread_bps}bps")
    if ig_spread_bps is None:
        ig_spread_bps = FALLBACK["ig_spread_bps"]
        logger.warning(f"[사모크레딧] IG fallback 사용: {ig_spread_bps}bps")

    # ── 1개월 변화량 ──────────────────────────────────────
    hy_1m_change = 0.0
    try:
        hy_obs = fetch_series("BAMLH0A0HYM2", limit=30)   # ← 상단 임포트 사용
        if len(hy_obs) >= 20:
            latest    = float(hy_obs[0]["value"])  * 100
            month_ago = float(hy_obs[19]["value"]) * 100
            hy_1m_change = round(latest - month_ago, 1)
    except Exception as e:
        logger.warning(f"[사모크레딧] HY 1개월 변화량 계산 실패: {e}")

    # ── 점수 산출 ─────────────────────────────────────────
    score = 0

    if hy_spread_bps >= HY_DANGER:
        score += 60
    elif hy_spread_bps >= HY_WARNING:
        score += 35
    elif hy_spread_bps >= HY_NORMAL:
        score += 15
    else:
        score += 5

    if hy_1m_change >= 100:
        score += 40
    elif hy_1m_change >= 50:
        score += 25
    elif hy_1m_change >= 20:
        score += 10
    elif hy_1m_change <= -20:
        score = max(0, score - 5)

    score = min(100, score)

    grade = "RED" if score >= 70 else "YELLOW" if score >= 40 else "GREEN"

    logger.info(
        f"[사모크레딧] HY: {hy_spread_bps:.1f}bps | "
        f"IG: {ig_spread_bps:.1f}bps | "
        f"HY 1개월 변화: {hy_1m_change:+.1f}bps | "
        f"점수: {score}"
    )

    return {
        "score":                score,
        "grade":                grade,
        "hy_spread_bps":        round(hy_spread_bps, 1),
        "ig_spread_bps":        round(ig_spread_bps, 1),
        "hy_spread_percentile": None,
        "hy_1m_change_bps":     hy_1m_change,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
    }
