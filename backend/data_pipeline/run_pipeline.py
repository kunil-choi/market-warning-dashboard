# ============================================================
# run_pipeline.py  –  파이프라인 메인 진입점
# 수정:
#   Fix1 – DATA_DIR 절대경로 강제 지정 (frontend/data/)
#   Fix2 – sys.path에 레포 루트 추가
#   Bug7 – history.jsonl 같은 날 중복 기록 방지
# ============================================================

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Fix2: 레포 루트를 sys.path에 추가 ──────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scoring.scoring_engine import run_full_scoring
from backend.scoring.ai_validator   import validate_with_ai

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Fix1: 절대경로로 강제 지정 ─────────────────────────────
DATA_DIR        = REPO_ROOT / "frontend" / "data"
LATEST_JSON     = DATA_DIR / "latest_scores.json"
HISTORY_JSONL   = DATA_DIR / "history.jsonl"
VALIDATION_JSON = DATA_DIR / "latest_validation.json"


def _update_history(entry: dict) -> None:
    today = entry["date"]
    lines = []
    if HISTORY_JSONL.exists():
        with open(HISTORY_JSONL, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("date") != today:
                        lines.append(line)
                except json.JSONDecodeError:
                    lines.append(line)
    lines.append(json.dumps(entry, ensure_ascii=False))
    with open(HISTORY_JSONL, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_pipeline():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("📊 파이프라인 시작")
    logger.info(f"📁 저장 경로: {DATA_DIR.resolve()}")
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
        f"등급={scores.get('grade')} "
        f"W4={scores.get('w4_score')}"
    )

    # ── 2단계: AI 검증 ───────────────────────────────────────
    logger.info("[2/3] AI 검증 시작")
    try:
        validation = validate_with_ai(scores)
    except Exception as e:
        logger.error(f"[2/3] AI 검증 예외: {e}", exc_info=True)
        validation = {
            "validation_passed":  None,
            "overall_assessment": f"검증 예외: {e}",
            "data_checks": [], "anomalies": [], "recommendations": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "model": None,
        }

    passed = validation.get("validation_passed")
    if passed is True:
        logger.info("[2/3] ✅ AI 검증 통과")
    elif passed is False:
        logger.warning("[2/3] ⚠️  AI 검증 실패")
        for a in validation.get("anomalies", []):
            logger.warning(f"         이상: {a}")
        for r in validation.get("recommendations", []):
            logger.warning(f"         권고: {r}")
    else:
        logger.info("[2/3] ℹ️  AI 검증 스킵")

    scores["ai_validation"] = validation

    # ── 3단계: 결과 저장 ─────────────────────────────────────
    logger.info("[3/3] 결과 저장")

    try:
        with open(LATEST_JSON, "w", encoding="utf-8") as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
        logger.info(f"저장 완료: {LATEST_JSON.resolve()}")
    except Exception as e:
        logger.error(f"latest_scores.json 저장 실패: {e}")
        sys.exit(1)

    try:
        with open(VALIDATION_JSON, "w", encoding="utf-8") as f:
            json.dump(validation, f, ensure_ascii=False, indent=2)
        logger.info(f"저장 완료: {VALIDATION_JSON.resolve()}")
    except Exception as e:
        logger.warning(f"latest_validation.json 저장 실패: {e}")

    try:
        history_entry = {
            "date":              datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "score":             scores.get("composite_score"),   # dashboard.js / charts.js 호환
            "composite_score":   scores.get("composite_score"),   # 하위 호환 유지
            "w1_score":          scores.get("w1_score"),
            "w2_score":          scores.get("w2_score"),
            "w3_score":          scores.get("w3_score"),
            "w4_score":          scores.get("w4_score"),
            "grade":             scores.get("grade"),
            "validation_passed": passed,
        }
        _update_history(history_entry)
        logger.info(f"히스토리 업데이트: {HISTORY_JSONL.resolve()}")
    except Exception as e:
        logger.warning(f"history.jsonl 저장 실패: {e}")

    logger.info("=" * 60)
    logger.info(
        f"✅ 파이프라인 완료 | "
        f"종합={scores.get('composite_score')}점 | "
        f"등급={scores.get('grade')} | "
        f"W4={scores.get('w4_score')}점 | "
        f"AI검증={'통과' if passed is True else '실패' if passed is False else '스킵'}"
    )
    logger.info("=" * 60)
    return scores


if __name__ == "__main__":
    run_pipeline()
