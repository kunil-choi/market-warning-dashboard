import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.scoring.scoring_engine import run_full_scoring

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def main():
    logger.info("🚀 데이터 파이프라인 시작")

    try:
        result = run_full_scoring()

        os.makedirs("data", exist_ok=True)

        output_path = "data/latest_scores.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"✅ 결과 저장 완료: {output_path}")
        logger.info(f"📊 종합 위험 스코어: {result['composite']['final_score']:.1f}/100 [{result['composite']['overall_grade']}]")

        history_path = "data/history.jsonl"
        history_entry = {
            "date": result["meta"]["generated_at"][:10],
            "score": result["composite"]["final_score"],
            "grade": result["composite"]["overall_grade"],
            "w1": result["warnings"]["w1_liquidity"]["score"],
            "w2": result["warnings"]["w2_rates"]["score"],
            "w3": result["warnings"]["w3_credit"]["score"],
            "w4": result["warnings"]["w4_ipo"]["score"],
            "signal": result["algo_signal"]["signal"],
        }
        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")

        logger.info(f"📅 히스토리 저장: {history_path}")
        return 0

    except Exception as e:
        logger.error(f"❌ 파이프라인 실패: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
