# ============================================================
# run_pipeline.py  –  파이프라인 메인 진입점
# 단계: 수집·점수산출 → AI검증 → 저장
# ============================================================

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from backend.scoring.scoring_engine import run_full_scoring
from backend.scoring.ai_validator   import validate_with_ai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

DATA_DIR        = Path("data")
LATEST_JSON     = DATA_DIR / "latest_scores.json"
HISTORY_JSONL   = DATA_DIR / "history.jsonl"
VALIDATION_JSON = DATA_DIR / "latest_validation.json"


def run_pipeline():
    DATA_DIR.mkdir(exist_ok=True)

    logger.info("=" * 60)
    logger.info("📊 파이프라인 시작")
    logger.info("=" * 60)

    # ── 1단계: 데이터 수집 및 점수 산출 ─────────────────────
    logger.info("[1/3] 데이터 수집 및 점수 산출")
    try:
        scores = run_full_scoring()
    except Exception as e:
        logger.error(f"[1/3] 스코어링 실패: {e}", exc_info=True)
        sys.exit(1)

    logger.info(
        f"[1/3] 완료 — 종합={scores.get('composite_score')}점 "
        f"등급={scores.get('grade')}"
    )

    # ── 2단계: AI 검증 ───────────────────────────────────────
    logger.info("[2/3] AI 검증 시작")
    try:
        validation = validate_with_ai(scores)
    except Exception as e:
        logger.error(f"[2/3] AI 검증 중 예외 발생: {e}", exc_info=True)
        # AI 검증 실패는 파이프라인을 중단하지 않음
        validation = {
            "validation_passed":  None,
            "overall_assessment": f"검증 예외: {e}",
            "data_checks":        [],
            "score_checks":       [],
            "anomalies":          [],
            "recommendations":    [],
            "validated_at":       datetime.now(timezone.utc).isoformat(),
            "model":              None,
        }

    passed = validation.get("validation_passed")
    if passed is True:
        logger.info("[2/3] ✅ AI 검증 통과")
    elif passed is False:
        logger.warning("[2/3] ⚠️  AI 검증 실패 — 데이터를 확인하세요")
        for a in validation.get("anomalies", []):
            logger.warning(f"         이상: {a}")
        for r in validation.get("recommendations", []):
            logger.warning(f"         권고: {r}")
    else:
        logger.info("[2/3] ℹ️  AI 검증 스킵")

    # 검증 결과를 scores에 포함
    scores["ai_validation"] = validation

    # ── 3단계: 결과 저장 ─────────────────────────────────────
    logger.info("[3/3] 결과 저장")

    # latest_scores.json — 검증 결과 포함 전체
    try:
        with open(LATEST_JSON, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
        logger.info(f"저장 완료: {LATEST_JSON}")
    except Exception as e:
        logger.error(f"latest_scores.json 저장 실패: {e}")
        sys.exit(1)

    # latest_validation.json — 검증 결과 단독
    try:
        with open(VALIDATION_JSON, "w", encoding="utf-8") as f:
            json.dump(validation, f, ensure_ascii=False, indent=2)
        logger.info(f"저장 완료: {VALIDATION_JSON}")
    except Exception as e:
        logger.warning(f"latest_validation.json 저장 실패 (비치명): {e}")

    # history.jsonl — 히스토리 누적
    try:
        history_entry = {
            "date":              datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "composite_score":   scores.get("composite_score"),
            "w1_score":          scores.get("w1_score"),
            "w2_score":          scores.get("w2_score"),
            "w3_score":          scores.get("w3_score"),
            "w4_score":          scores.get("w4_score"),
            "grade":             scores.get("grade"),
            "validation_passed": passed,
        }
        with open(HISTORY_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")
        logger.info(f"히스토리 추가: {HISTORY_JSONL}")
    except Exception as e:
        logger.warning(f"history.jsonl 저장 실패 (비치명): {e}")

    logger.info("=" * 60)
    logger.info(
        f"✅ 파이프라인 완료 | "
        f"종합={scores.get('composite_score')}점 | "
        f"등급={scores.get('grade')} | "
        f"AI검증={'통과' if passed is True else '실패' if passed is False else '스킵'}"
    )
    logger.info("=" * 60)
    return scores


if __name__ == "__main__":
    run_pipeline()
