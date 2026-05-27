import json
import logging
import os
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.scoring.scoring_engine import run_full_scoring

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("🚀 데이터 파이프라인 시작")
    logger.info("=" * 60)

    try:
        # ── 스코어링 실행 ──
        result = run_full_scoring()

        # ── data/ 폴더 생성 ──
        data_dir = Path("data")
        data_dir.mkdir(parents=True, exist_ok=True)

        # ── latest_scores.json 저장 ──
        output_path = data_dir / "latest_scores.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 결과 저장 완료: {output_path}")

        comp = result["composite"]
        logger.info(
            f"📊 종합 위험 스코어: "
            f"{comp['final_score']:.1f}/100 [{comp['overall_grade']}]"
        )
        logger.info(f"📌 권장 액션: {comp['action_recommended']}")
        logger.info(
            f"🚦 알고 시그널: {result['algo_signal']['signal']} — "
            f"{result['algo_signal']['signal_desc']}"
        )

        # ── history.jsonl 저장 (최초 실행 시 파일 자동 생성) ──
        history_path = data_dir / "history.jsonl"

        # 파일이 없으면 빈 파일 생성
        if not history_path.exists():
            history_path.touch()
            logger.info(f"📁 히스토리 파일 최초 생성: {history_path}")

        history_entry = {
            "date":   result["meta"]["generated_at"][:10],
            "score":  comp["final_score"],
            "grade":  comp["overall_grade"],
            "w1":     result["warnings"]["w1_liquidity"]["score"],
            "w2":     result["warnings"]["w2_rates"]["score"],
            "w3":     result["warnings"]["w3_credit"]["score"],
            "w4":     result["warnings"]["w4_ipo"]["score"],
            "signal": result["algo_signal"]["signal"],
        }

        with open(history_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")

        logger.info(f"📅 히스토리 저장 완료: {history_path}")
        logger.info("=" * 60)
        logger.info("✅ 파이프라인 완료")
        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"❌ 파이프라인 실패: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
