# ============================================================
# scoring_engine.py  –  전체 스코어링 엔진 (한국 추가)
# ============================================================

import logging
from datetime import datetime, timezone
from backend.data_pipeline.collector_liquidity import collect_liquidity_data
from backend.data_pipeline.collector_rates     import collect_rates_data
from backend.data_pipeline.collector_credit    import collect_credit_data
from backend.data_pipeline.collector_ipo       import collect_ipo_data
from backend.data_pipeline.collector_korea     import collect_korea_data

logger = logging.getLogger(__name__)


def run_full_scoring() -> dict:
    logger.info("=" * 60)
    logger.info("▶ 글로벌 주식시장 위기경보 대시보드 – 스코어링 시작")
    logger.info("=" * 60)

    # ── 미국 데이터 수집 ──────────────────────────────────
    logger.info("[1/5] W1 선도주 압축 데이터 수집")
    w1_data = collect_liquidity_data()

    logger.info("[2/5] W2 채권 자경단 데이터 수집")
    w2_data = collect_rates_data()

    logger.info("[3/5] W3 사모크레딧 데이터 수집")
    w3_data = collect_credit_data()

    logger.info("[4/5] W4 대형 IPO 데이터 수집")
    w4_data = collect_ipo_data()

    # ── 한국 데이터 수집 ──────────────────────────────────
    logger.info("[5/5] KR 한국 시장 데이터 수집")
    try:
        kr_data = collect_korea_data()
    except Exception as e:
        logger.warning("한국 데이터 수집 실패, 폴백 사용: %s", e)
        kr_data = {
            "kr_composite_score": 0,
            "kr_grade": "GREEN",
            "k1": {"score": 0}, "k2": {"score": 0},
            "k3": {"score": 0}, "k4": {"score": 0},
        }

    # ── 미국 종합점수 ──────────────────────────────────────
    w1_score = w1_data.get("score", 0)
    w2_score = w2_data.get("score", 0)
    w3_score = w3_data.get("score", 0)
    w4_score = w4_data.get("score", 0)

    composite_score = round(
        w1_score * 0.25 +
        w2_score * 0.30 +
        w3_score * 0.20 +
        w4_score * 0.25,
        1
    )

    grade = "RED" if composite_score >= 70 else "YELLOW" if composite_score >= 40 else "GREEN"

    result = {
        "composite_score":    composite_score,
        "grade":              grade,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "w1_score":           w1_score,
        "w2_score":           w2_score,
        "w3_score":           w3_score,
        "w4_score":           w4_score,
        "w1":                 w1_data,
        "w2":                 w2_data,
        "w3":                 w3_data,
        "w4":                 w4_data,
        # 한국 데이터
        "kr_composite_score": kr_data.get("kr_composite_score", 0),
        "kr_grade":           kr_data.get("kr_grade", "GREEN"),
        "k1":                 kr_data.get("k1", {}),
        "k2":                 kr_data.get("k2", {}),
        "k3":                 kr_data.get("k3", {}),
        "k4":                 kr_data.get("k4", {}),
    }

    logger.info("=" * 60)
    logger.info(
        f"스코어링 완료 | US={composite_score}점({grade}) | "
        f"KR={kr_data.get('kr_composite_score',0)}점({kr_data.get('kr_grade','?')}) | "
        f"W1={w1_score} W2={w2_score} W3={w3_score} W4={w4_score}"
    )
    logger.info("=" * 60)
    return result
