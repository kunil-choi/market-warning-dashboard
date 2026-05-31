# ============================================================
# collector_credit.py  –  W3 사모 크레딧 데이터 수집
# FRED 호출을 fred_client 공통 클라이언트로 교체
# HY fallback 400bps → 실제값 272bps 수정
# ============================================================

import logging
from datetime import datetime, timezone
from backend.data_pipeline.fred_client import get_latest_value

logger = logging.getLogger(__name__)

# ── Fallback 기본값 ───────────────────────────────────────
# 출처: FRED 2026-05-28 실측값 기준
FALLBACK = {
    "hy_spread_bps": 272.0,   # BAMLH0A0HYM2 × 100
    "ig_spread_bps":  77.0,   # BAMLC0A0CM × 100
}

# ── 점수 임계값 ───────────────────────────────────────────
HY_DANGER   = 400   # bps — 위기 수준
HY_WARNING  = 300   # bps — 경고 수준
HY_NORMAL   = 200   # bps — 정상 하단


def collect_credit_data() -> dict:
    """
    W3 사모 크레딧 데이터 수집 및 점수 산출.

    수집 항목:
      - BAMLH0A0HYM2 : ICE BofA HY 스프레드 (%) → × 100 = bps
      - BAMLC0A0CM   : ICE BofA IG 스프레드 (%) → × 100 = bps
    """
    logger.info("[사모크레딧] 데이터 수집 시작")

    # ── FRED 호출 (% 단위로 수집 → ×100 해서 bps 변환) ────
    hy_spread_bps = get_latest_value(
        "BAMLH0A0HYM2",
        fallback=FALLBACK["hy_spread_bps"] / 100,  # fallback도 % 단위
        multiplier=100.0,                            # bps 변환
    )
    ig_spread_bps = get_latest_value(
        "BAMLC0A0CM",
        fallback=FALLBACK["ig_spread_bps"] / 100,
        multiplier=100.0,
    )

    # fallback이 None이면 기본값 사용
    if hy_spread_bps is None:
        hy_spread_bps = FALLBACK["hy_spread_bps"]
        logger.warning(f"[사모크레딧] HY 스프레드 fallback 사용: {hy_spread_bps}bps")
    if ig_spread_bps is None:
        ig_spread_bps = FALLBACK["ig_spread_bps"]
        logger.warning(f"[사모크레딧] IG 스프레드 fallback 사용: {ig_spread_bps}bps")

    # 1개월 변화량 (추가 수집)
    hy_obs = []
    try:
        from backend.data_pipeline.fred_client import fetch_series
        hy_obs = fetch_series("BAMLH0A0HYM2", limit=30)
    except Exception:
        pass

    hy_1m_change = 0.0
    if len(hy_obs) >= 20:
        try:
            latest   = float(hy_obs[0]["value"])  * 100
            month_ago = float(hy_obs[19]["value"]) * 100
            hy_1m_change = round(latest - month_ago, 1)
        except (ValueError, IndexError):
            pass

    # ── 점수 산출 ─────────────────────────────────────────
    score = 0

    # HY 스프레드 절대 수준 (0~60점)
    if hy_spread_bps >= HY_DANGER:      # 400bps 이상
        score += 60
    elif hy_spread_bps >= HY_WARNING:   # 300~400bps
        score += 35
    elif hy_spread_bps >= HY_NORMAL:    # 200~300bps
        score += 15
    else:                                # 200bps 미만 (역대 저점권)
        score += 5

    # HY 1개월 변화 보너스 (0~40점)
    if hy_1m_change >= 100:
        score += 40
    elif hy_1m_change >= 50:
        score += 25
    elif hy_1m_change >= 20:
        score += 10
    elif hy_1m_change <= -20:           # 스프레드 축소 = 안정화
        score = max(0, score - 5)

    score = min(100, score)

    if score >= 70:
        grade = "RED"
    elif score >= 40:
        grade = "YELLOW"
    else:
        grade = "GREEN"

    logger.info(
        f"[사모크레딧] HY 스프레드: {hy_spread_bps:.1f}bps | "
        f"IG 스프레드: {ig_spread_bps:.1f}bps | "
        f"HY 1개월 변화: {hy_1m_change:+.1f}bps"
    )

    return {
        "score":               score,
        "grade":               grade,
        "hy_spread_bps":       round(hy_spread_bps, 1),
        "ig_spread_bps":       round(ig_spread_bps, 1),
        "hy_spread_percentile": None,   # 향후 히스토리 누적 후 계산
        "hy_1m_change_bps":    hy_1m_change,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }
