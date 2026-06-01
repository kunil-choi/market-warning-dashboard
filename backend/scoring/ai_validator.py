# ============================================================
# ai_validator.py  –  Claude AI 기반 원천 데이터 신뢰성 검증
# 수정:
#   Fix-V1 – 검증 목적 변경: 점수 계산 검증 → 원천 데이터 신뢰성 검증
#   Fix-V2 – IPO 목록 프롬프트 완전 제거 → 토큰 절감
#   Fix-V3 – max_tokens 512로 축소 (응답 잘림 방지)
# ============================================================

import os
import json
import logging
import time
from datetime import datetime, timezone

import anthropic

logger = logging.getLogger(__name__)

VALIDATION_PROMPT = """
당신은 금융 데이터 신뢰성 검증 전문가입니다.
아래는 시장 경고 대시보드가 각 기관 API에서 수집한 원천 데이터입니다.
각 수치가 실제 시장 현황과 일치하는 신뢰할 수 있는 데이터인지 검증해주세요.

## 데이터 출처
- W1 SPY/RSP 수익률: yfinance (Yahoo Finance API)
- W2 금리 데이터: FRED API (미국 연방준비제도)
- W3 HY/IG 스프레드: FRED API (ICE BofA 채권 인덱스)
- W4 IPO 파이프라인: Reuters, Bloomberg, CNBC 보도 기반 fallback

## 수집된 원천 데이터
{raw_data}

## 검증 요청 사항
1. 각 수치가 현재 시장 상황에서 현실적으로 가능한 범위인지
2. 데이터 간 일관성 (10년물↔2년물 관계, HY↔IG 스프레드 관계)
3. fallback 값 사용 의심 여부 (FRED fallback: 10년물 4.45%, HY 272bps)
4. IPO 기업 상태·기업가치가 최근 보도와 일치하는지

## 응답 형식 (반드시 순수 JSON만 출력, 마크다운 코드블록 없이)
{{"validation_passed": true, "overall_assessment": "전체 신뢰성 평가 한 문장", "data_checks": [{{"source": "FRED", "field": "us10y_yield", "value": "4.45", "status": "FALLBACK", "comment": "fallback 값 사용 의심"}}, {{"source": "yfinance", "field": "spy_ytd", "value": "11.24", "status": "OK", "comment": "현재 시장 범위 내"}}], "anomalies": ["이상 항목"], "recommendations": ["권고 사항"]}}
"""

def _build_raw_summary(scores_data: dict) -> str:
    w1 = scores_data.get("w1", {})
    w2 = scores_data.get("w2", {})
    w3 = scores_data.get("w3", {})
    w4 = scores_data.get("w4", {})

    summary = {
        "W1_주도주압축_yfinance": {
            "SPY_YTD_%":        w1.get("spy_ytd"),
            "RSP_YTD_%":        w1.get("rsp_ytd"),
            "SPY_RSP_괴리율_%p": w1.get("current_spread"),
            "괴리_퍼센타일":     w1.get("spread_percentile"),
            "RSP_1주수익률_%":   w1.get("rsp_1w_return"),
            "RSP_역행신호":      w1.get("rsp_is_negative_while_spy_positive"),
        },
        "W2_금리_FRED": {
            "미국10년물_%":      w2.get("us10y_yield"),
            "미국2년물_%":       w2.get("us2y_yield"),
            "장단기스프레드_%p": w2.get("term_spread"),
            "TIPS실질금리_%":    w2.get("tips_10y_real_yield"),
            "장단기역전":        w2.get("is_inverted"),
        },
        "W3_크레딧스프레드_FRED": {
            "HY스프레드_bps":   w3.get("hy_bps"),
            "IG스프레드_bps":   w3.get("ig_bps"),
            "HY_1개월변화_bps": w3.get("hy_change_bps"),
        },
        "W4_IPO파이프라인": {
            "가중파이프라인_B":  w4.get("total_valuation_bn"),
            "시총대비비율_%":    w4.get("pipeline_ratio_pct"),
            "가격확정건수":      w4.get("priced_count"),
            "신청완료건수":      w4.get("filed_count"),
        },
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


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
                max_tokens=512,
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
