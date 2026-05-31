# ============================================================
# scoring_engine.py
# 수정: raw_data["ipo"] → raw_data["ipo"]["ipo_list"] 로 수정
# ============================================================

import logging
from backend.data_pipeline.collector_liquidity import collect_liquidity_data
from backend.data_pipeline.collector_rates     import collect_rates_data
from backend.data_pipeline.collector_credit    import collect_credit_data
from backend.data_pipeline.collector_ipo       import collect_ipo_data, calculate_ipo_score

logger = logging.getLogger(__name__)


def run_full_scoring() -> dict:
    logger.info("▶ 펌목적 감세장 경고 대시보드 – 스코어링 시작")

    # ── 1. 원본 데이터 수집 ───────────────────────────────
    raw_data = {}

    logger.info("[유동성] 데이터 수집 시작")
    raw_data["liquidity"] = collect_liquidity_data()

    logger.info("[금리] 데이터 수집 시작")
    raw_data["rates"] = collect_rates_data()

    logger.info("[크레딧] 데이터 수집 시작")
    raw_data["credit"] = collect_credit_data()

    logger.info("[IPO] 데이터 수집 시작")
    raw_data["ipo"] = collect_ipo_data()   # collect_ipo_data()는 dict 반환

    # ── 2. 점수 산출 ──────────────────────────────────────
    w1_score = raw_data["liquidity"].get("score", 0)
    w2_score = raw_data["rates"].get("score", 0)
    w3_score = raw_data["credit"].get("score", 0)

    # ★ 핵심 수정: collect_ipo_data()가 반환한 dict 안의 score를 직접 사용
    # calculate_ipo_score()는 collect_ipo_data() 내부에서 이미 호출됨
    # 중복 호출 제거 → raw_data["ipo"]["score"] 직접 참조
    w4_score = raw_data["ipo"].get("score", 0)

    # ── 3. 가중 종합점수 ──────────────────────────────────
    composite_score = round(
        w1_score * 0.25 +
        w2_score * 0.30 +
        w3_score * 0.20 +
        w4_score * 0.25,
        1
    )

    # ── 4. 등급 판정 ──────────────────────────────────────
    if composite_score >= 70:
        grade = "RED"
    elif composite_score >= 40:
        grade = "YELLOW"
    else:
        grade = "GREEN"

    # ── 5. 결과 조립 ──────────────────────────────────────
    result = {
        # 종합
        "composite_score": composite_score,
        "grade":           grade,
        "timestamp":       raw_data["ipo"].get("timestamp"),

        # 각 지표 원점수
        "w1_score": w1_score,
        "w2_score": w2_score,
        "w3_score": w3_score,
        "w4_score": w4_score,

        # 각 지표 원본 데이터 (프론트 카드 뒷면용)
        "w1": raw_data["liquidity"],
        "w2": raw_data["rates"],
        "w3": raw_data["credit"],
        "w4": raw_data["ipo"],
    }

    logger.info(
        f"스코어링 완료 | 종합={composite_score}점 | 등급={grade} | "
        f"W1={w1_score} W2={w2_score} W3={w3_score} W4={w4_score}"
    )
    return result
