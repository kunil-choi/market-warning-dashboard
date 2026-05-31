# ============================================================
# scoring_engine.py  –  전체 스코어링 엔진
# 수정: IPO 이중 호출 버그 완전 제거
# ============================================================

import logging
from datetime import datetime, timezone
from backend.data_pipeline.collector_liquidity import collect_liquidity_data
from backend.data_pipeline.collector_rates     import collect_rates_data
from backend.data_pipeline.collector_credit    import collect_credit_data
from backend.data_pipeline.collector_ipo       import collect_ipo_data

logger = logging.getLogger(__name__)


def run_full_scoring() -> dict:
    logger.info("=" * 60)
    logger.info("▶ 펌목적 감세장 경고 대시보드 – 스코어링 시작")
    logger.info("=" * 60)

    # ── 1. 데이터 수집 ────────────────────────────────────
    logger.info("[1/4] W1 주도주 압축 데이터 수집")
    w1_data = collect_liquidity_data()

    logger.info("[2/4] W2 채권 자경단 데이터 수집")
    w2_data = collect_rates_data()

    logger.info("[3/4] W3 사모 크레딧 데이터 수집")
    w3_data = collect_credit_data()

    logger.info("[4/4] W4 대어급 IPO 데이터 수집")
    w4_data = collect_ipo_data()
    # ★ collect_ipo_data()는 내부에서 calculate_ipo_score()를 호출하고
    #    결과 dict를 반환함 → 여기서 calculate_ipo_score()를 다시 호출하면 안 됨

    # ── 2. 원점수 추출 ────────────────────────────────────
    w1_score = w1_data.get("score", 0)
    w2_score = w2_data.get("score", 0)
    w3_score = w3_data.get("score", 0)
    w4_score = w4_data.get("score", 0)   # ★ w4_data["score"] 직접 참조

    # ── 3. 가중 종합점수 ──────────────────────────────────
    composite_score = round(
        w1_score * 0.25 +
        w2_score * 0.30 +
        w3_score * 0.20 +
        w4_score * 0.25,
        1
    )

    # ── 4. 등급 ───────────────────────────────────────────
    if composite_score >= 70:
        grade = "RED"
    elif composite_score >= 40:
        grade = "YELLOW"
    else:
        grade = "GREEN"

    # ── 5. 결과 조립 ──────────────────────────────────────
    result = {
        "composite_score": composite_score,
        "grade":           grade,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "w1_score":        w1_score,
        "w2_score":        w2_score,
        "w3_score":        w3_score,
        "w4_score":        w4_score,
        "w1":              w1_data,
        "w2":              w2_data,
        "w3":              w3_data,
        "w4":              w4_data,
    }

    logger.info("=" * 60)
    logger.info(
        f"스코어링 완료 | 종합={composite_score}점 | 등급={grade} | "
        f"W1={w1_score} W2={w2_score} W3={w3_score} W4={w4_score}"
    )
    logger.info("=" * 60)
    return result
