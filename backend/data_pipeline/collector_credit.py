"""
collector_credit.py
신용 스프레드(HY / IG OAS) 데이터 수집 및 위험 점수 계산 모듈
"""

import logging
from datetime import datetime, timezone

from backend.data_pipeline.fred_client import get_latest_value, get_series

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수 정의
# ──────────────────────────────────────────────

HY_SERIES_ID = "BAMLH0A0HYM2"  # ICE BofA US High Yield OAS (단위: %)
IG_SERIES_ID = "BAMLC0A0CM"    # ICE BofA US Corporate OAS  (단위: %)

# API 장애 시 fallback 값 (bps)
# HY: FRED BAMLH0A0HYM2 2026-05-28
# IG: FRED BAMLC0A0CM   2026-05-25
HY_FALLBACK: float = 272.0
IG_FALLBACK: float = 74.0   # ✅ 수정: 77 → 74

# 1개월 변화량 계산을 위한 관측 수
LOOKBACK_DAYS: int = 22


# ──────────────────────────────────────────────
# 점수 계산 헬퍼
# ──────────────────────────────────────────────

def _score_hy(hy_bps: float, hy_change_bps: float) -> int:
    """HY 스프레드 수준 + 1개월 변화량으로 점수를 산출한다."""
    if hy_bps >= 400:
        level_score = 60
    elif hy_bps >= 300:
        level_score = 35
    elif hy_bps >= 200:
        level_score = 15
    else:
        level_score = 5

    if hy_change_bps >= 100:
        change_bonus = 25
    elif hy_change_bps >= 50:
        change_bonus = 15
    elif hy_change_bps >= 20:
        change_bonus = 8
    else:
        change_bonus = 0

    return min(level_score + change_bonus, 100)


def _grade(score: int) -> tuple[str, str]:
    if score >= 80:
        return "위험", "red"
    if score >= 60:
        return "경고", "orange"
    if score >= 40:
        return "주의", "yellow"
    return "정상", "green"


# ──────────────────────────────────────────────
# 메인 수집 함수
# ──────────────────────────────────────────────

def collect_credit_data() -> dict:
    """
    HY / IG OAS 스프레드를 수집하고 위험 점수를 계산해 반환한다.

    Returns:
        score, grade, color, hy_bps, ig_bps, hy_change_bps,
        signals, timestamp 포함 딕셔너리
    """
    logger.info("신용 스프레드 수집 시작")

    # ── HY 스프레드 수집 (% → bps 변환)
    hy_pct = get_latest_value(HY_SERIES_ID)
    if hy_pct is None:
        logger.warning("HY FRED 수집 실패 → fallback %.1f bps", HY_FALLBACK)
        hy_bps = HY_FALLBACK
    else:
        hy_bps = hy_pct * 100

    # ── IG 스프레드 수집 (% → bps 변환)
    ig_pct = get_latest_value(IG_SERIES_ID)
    if ig_pct is None:
        logger.warning("IG FRED 수집 실패 → fallback %.1f bps", IG_FALLBACK)
        ig_bps = IG_FALLBACK
    else:
        ig_bps = ig_pct * 100

    # ── HY 1개월 변화량 계산
    hy_change_bps: float = 0.0
    try:
        series = get_series(HY_SERIES_ID, limit=LOOKBACK_DAYS + 5)
        if series and len(series) >= 2:
            latest_val = series[-1].get("value")
            oldest_val = series[0].get("value")
            if latest_val is not None and oldest_val is not None:
                hy_change_bps = (float(latest_val) - float(oldest_val)) * 100
    except Exception as exc:
        logger.warning("HY 변화량 계산 실패: %s", exc)

    # ── 점수 및 등급
    raw_score      = _score_hy(hy_bps, hy_change_bps)
    grade, color   = _grade(raw_score)

    # ── 시그널 메시지
    signals: list[str] = []
    if hy_bps >= 400:
        signals.append(f"🚨 HY 스프레드 {hy_bps:.0f} bps — 위험 구간 (≥400 bps)")
    elif hy_bps >= 300:
        signals.append(f"⚠️ HY 스프레드 {hy_bps:.0f} bps — 경고 구간")
    elif hy_bps >= 200:
        signals.append(f"📢 HY 스프레드 {hy_bps:.0f} bps — 주의 구간")
    else:
        signals.append(f"✅ HY 스프레드 {hy_bps:.0f} bps — 역사적 저점 (정상)")

    if ig_bps <= 80:
        signals.append(f"✅ IG 스프레드 {ig_bps:.0f} bps — 타이트 (하위 10%)")
    else:
        signals.append(f"📊 IG 스프레드 {ig_bps:.0f} bps")

    if hy_change_bps >= 20:
        signals.append(f"📈 HY 1개월 변화: +{hy_change_bps:.0f} bps (급등)")

    result = {
        "score":         raw_score,
        "grade":         grade,
        "color":         color,
        "hy_bps":        round(hy_bps, 1),
        "ig_bps":        round(ig_bps, 1),
        "hy_change_bps": round(hy_change_bps, 1),
        "signals":       signals,
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "신용 스프레드: HY %.0f bps | IG %.0f bps | 점수 %d점 (%s)",
        hy_bps, ig_bps, raw_score, grade,
    )
    return result
