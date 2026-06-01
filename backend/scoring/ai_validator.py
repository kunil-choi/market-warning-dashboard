# ============================================================
# ai_validator.py  –  Claude AI 기반 원천 데이터 신뢰성 검증
# 수정:
#   Fix-V4 – 응답 형식 최소화 (data_checks 제거, 핵심만 유지)
#             → 응답 300자 이내로 제한
# ============================================================

import os
import json
import logging
import time
from datetime import datetime, timezone

import anthropic

logger = logging.getLogger(__name__)

VALIDATION_PROMPT = """
당신은 금융 데이터 검증 전문가입니다.
아래 수집된 시장 데이터가 현재 실제 시장 상황과 일치하는지 검증하세요.

## 수집 데이터
{raw_data}

## 응답 규칙
- 반드시 아래 JSON 형식만 출력 (다른 텍스트 절대 금지)
- 짧고 간결하게 (전체 200자 이내)

{{"validation_passed": true, "overall_assessment": "한 문장 평가", "anomalies": [], "recommendations": []}}
"""

def _build_raw_summary(scores_data: dict) -> str:
    w1 = scores_data.get("w1", {})
    w2 = scores_data.get("w2", {})
    w3 = scores_data.get("w3", {})
    w4 = scores_data.get("w4", {})

    summary = {
        "SPY_YTD":       w1.get("spy_ytd"),
        "RSP_YTD":       w1.get("rsp_ytd"),
        "괴리율":         w1.get("current_spread"),
        "10년물":         w2.get("us10y_yield"),
        "2년물":          w2.get("us2y_yield"),
        "장단기스프레드": w2.get("term_spread"),
        "TIPS":          w2.get("tips_10y_real_yield"),
        "역전여부":       w2.get("is_inverted"),
        "HY_bps":        w3.get("hy_bps"),
        "IG_bps":        w3.get("ig_bps"),
        "HY변화_bps":    w3.get("hy_change_bps"),
        "IPO파이프라인_B": w4.get("total_valuation_bn"),
        "시총대비_%":     w4.get("pipeline_ratio_pct"),
        "가격확정건수":   w4.get("priced_count"),
        "신청완료건수":   w4.get("filed_count"),
    }
    return json.dumps(summary, ensure_ascii=False)


def validate_with_ai(scores_data: dict) -> dict:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("[AI검증] ANTHROPIC_API_KEY 없음 → 스킵")
        return _skip_result("ANTHROPIC_API_KEY 미설정")

    prompt = VALIDATION_PROMPT.format(
        raw_data=_build_raw_summary(scores_data),
    )

    logger.info("[AI검증] Claude API 호출 시작")
    time.sleep(3)

    wait_times = [15, 30, 60]

    for attempt in range(1, 4):
        try:
            client = anthropic.Anthropic(
                api_key=api_key,
                max_retries=0,
                timeout=60.0,
            )
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = message.content[0].text.strip()

            # 마크다운 코드블록 제거
            if "```" in raw_text:
                parts    = raw_text.split("```")
                raw_text = parts[1] if len(parts) > 1 else parts[0]
                if raw_text.lstrip().startswith("json"):
                    raw_text = raw_text.lstrip()[4:].strip()

            result = json.loads(raw_text)
            result["validated_at"] = datetime.now(timezone.utc).isoformat()
            result["model"]        = "claude-sonnet-4-6"

            passed = result.get("validation_passed")
            if passed is True:
                logger.info(f"[AI검증] ✅ 통과: {result.get('overall_assessment', '')}")
            else:
                logger.warning(f"[AI검증] ⚠️  실패: {result.get('overall_assessment', '')}")
                for a in result.get("anomalies", []):
                    logger.warning(f"[AI검증]   이상: {a}")
                for r in result.get("recommendations", []):
                    logger.warning(f"[AI검증]   권고: {r}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"[AI검증] JSON 파싱 실패 ({attempt}/3): {e}")
            if attempt == 3:
                return _skip_result(f"JSON 파싱 오류: {e}")
            time.sleep(wait_times[attempt - 1])

        except anthropic.RateLimitError:
            wait = wait_times[attempt - 1]
            logger.warning(f"[AI검증] Rate Limit → {wait}초 대기 ({attempt}/3)")
            time.sleep(wait)

        except anthropic.APIStatusError as e:
            err_msg = str(e)
            logger.error(f"[AI검증] API 상태 오류 {e.status_code} ({attempt}/3): {err_msg}")
            if e.status_code in (500, 529):
                time.sleep(wait_times[attempt - 1])
            else:
                return _skip_result(f"API 오류 {e.status_code}: {err_msg}")

        except anthropic.APIConnectionError as e:
            wait = wait_times[attempt - 1]
            logger.warning(f"[AI검증] 연결 오류 ({attempt}/3): {e} → {wait}초 대기")
            time.sleep(wait)

        except anthropic.APIError as e:
            logger.error(f"[AI검증] 기타 API 오류 ({attempt}/3): {e}")
            if attempt == 3:
                return _skip_result(f"API 오류: {e}")
            time.sleep(wait_times[attempt - 1])

        except Exception as e:
            logger.error(f"[AI검증] 예상치 못한 오류 ({attempt}/3): {e}")
            if attempt == 3:
                return _skip_result(f"알 수 없는 오류: {e}")
            time.sleep(wait_times[attempt - 1])

    return _skip_result("3회 재시도 모두 실패")


def _skip_result(reason: str) -> dict:
    return {
        "validation_passed":  None,
        "overall_assessment": f"검증 스킵: {reason}",
        "data_checks":        [],
        "anomalies":          [],
        "recommendations":    [],
        "validated_at":       datetime.now(timezone.utc).isoformat(),
        "model":              None,
    }
