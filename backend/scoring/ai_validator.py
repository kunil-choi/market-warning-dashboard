# ============================================================
# ai_validator.py  –  Claude AI 기반 검증
# 수정:
#   Bug4 – _build_raw_summary W3 키명 수정
#          hy_spread_bps  → hy_bps
#          ig_spread_bps  → ig_bps
#          hy_1m_change_bps → hy_change_bps
#          (collector_credit.py 실제 반환 키와 일치)
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
아래의 시장 경고 대시보드 데이터와 산출 점수를 검토하고,
데이터 이상 여부와 계산 정확성을 확인해주세요.

## 점수 계산 규칙
- W1 주도주 압축 (가중치 25%): SPY-RSP 괴리율 기반, 괴리 클수록 고점수
- W2 채권 자경단 (가중치 30%): 10년물 금리 4.5% 임계선, 장단기 역전 여부
- W3 사모 크레딧 (가중치 20%): HY 스프레드 기준, 400bps 이상 위험
- W4 대어급 IPO  (가중치 25%): 가중 파이프라인 $1,500B 임계선
- 종합점수 = W1×0.25 + W2×0.30 + W3×0.20 + W4×0.25
- 등급: 0~39점 GREEN / 40~69점 YELLOW / 70~100점 RED

## 현실적 데이터 범위 기준
- 10년물 금리: 2.0% ~ 6.0%
- 2년물 금리: 1.0% ~ 6.0%
- HY 스프레드: 150bps ~ 2000bps
- IG 스프레드: 40bps ~ 500bps
- SPY YTD: -50% ~ +60%
- RSP YTD: -50% ~ +60%
- IPO 기업가치: 1B ~ 5,000B

## 수집된 원본 데이터
{raw_data}

## 산출된 점수
{scores}

## 검토 요청 사항
1. 각 원본 데이터 수치가 현실적인 범위인지 (이상값 탐지)
2. 각 W1~W4 원점수가 원본 데이터와 계산 규칙에 부합하는지
3. 종합점수 계산이 가중치 기준과 정확히 일치하는지
4. 등급 판정이 올바른지
5. fallback 값 사용 여부 및 신뢰도 평가

## 응답 형식 (반드시 순수 JSON만 출력, 마크다운 코드블록 없이)
{{
  "validation_passed": true,
  "overall_assessment": "전체 평가 한 문장",
  "data_checks": [
    {{"field": "필드명", "value": "수치", "status": "OK", "comment": "설명"}}
  ],
  "score_checks": [
    {{"indicator": "W1", "reported_score": 40, "expected_range": "30~55",
      "status": "OK", "comment": "설명"}}
  ],
  "anomalies": [],
  "recommendations": []
}}
"""


def _build_raw_summary(scores_data: dict) -> str:
    w1 = scores_data.get("w1", {})
    w2 = scores_data.get("w2", {})
    w3 = scores_data.get("w3", {})
    w4 = scores_data.get("w4", {})
    summary = {
        "W1_주도주압축": {
            "SPY_YTD_%":      w1.get("spy_ytd"),
            "RSP_YTD_%":      w1.get("rsp_ytd"),
            "괴리율_%p":       w1.get("current_spread"),
            "괴리_퍼센타일":   w1.get("spread_percentile"),
            "RSP_1주수익률_%": w1.get("rsp_1w_return"),
        },
        "W2_채권자경단": {
            "10년물금리_%":    w2.get("us10y_yield"),
            "2년물금리_%":     w2.get("us2y_yield"),
            "장단기금리차_%p": w2.get("term_spread"),
            "TIPS실질금리_%":  w2.get("tips_10y_real_yield"),
            "장단기역전여부":  w2.get("is_inverted"),
        },
        # Bug4 수정: collector_credit.py 실제 반환 키와 일치
        "W3_사모크레딧": {
            "HY스프레드_bps":    w3.get("hy_bps"),
            "IG스프레드_bps":    w3.get("ig_bps"),
            "HY_1개월변화_bps":  w3.get("hy_change_bps"),
        },
        "W4_대어급IPO": {
            "가중파이프라인_B": w4.get("total_valuation_bn"),
            "신청완료건수":     w4.get("filed_count"),
            "공모가확정건수":   w4.get("priced_count"),
            "IPO목록": [
                {"기업": i.get("company"),
                 "기업가치_B": i.get("valuation_bn"),
                 "상태": i.get("status")}
                for i in (w4.get("ipo_list") or [])
            ],
        },
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def _build_scores_summary(scores_data: dict) -> str:
    w1 = scores_data.get("w1_score") or 0
    w2 = scores_data.get("w2_score") or 0
    w3 = scores_data.get("w3_score") or 0
    w4 = scores_data.get("w4_score") or 0
    summary = {
        "W1_원점수": w1,
        "W2_원점수": w2,
        "W3_원점수": w3,
        "W4_원점수": w4,
        "종합점수":  scores_data.get("composite_score"),
        "등급":      scores_data.get("grade"),
        "가중계산_검증": {
            "W1×0.25": round(w1 * 0.25, 2),
            "W2×0.30": round(w2 * 0.30, 2),
            "W3×0.20": round(w3 * 0.20, 2),
            "W4×0.25": round(w4 * 0.25, 2),
            "합산":    round(w1*0.25 + w2*0.30 + w3*0.20 + w4*0.25, 2),
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
        scores=_build_scores_summary(scores_data),
    )

    logger.info("[AI검증] Claude API 호출 시작")

    for attempt in range(1, 4):
        try:
            client  = anthropic.Anthropic(api_key=api_key)
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
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
            result["model"]        = "claude-3-5-sonnet-20241022"

            passed = result.get("validation_passed")
            if passed is True:
                logger.info(f"[AI검증] ✅ 통과: {result.get('overall_assessment','')}")
            else:
                logger.warning(f"[AI검증] ⚠️  실패: {result.get('overall_assessment','')}")
                for a in result.get("anomalies", []):
                    logger.warning(f"[AI검증]   이상: {a}")
                for r in result.get("recommendations", []):
                    logger.warning(f"[AI검증]   권고: {r}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"[AI검증] JSON 파싱 실패 ({attempt}/3): {e}")
            if attempt == 3:
                return _skip_result(f"JSON 파싱 오류: {e}")

        except anthropic.RateLimitError:
            logger.warning(f"[AI검증] Rate Limit → 5초 대기 ({attempt}/3)")
            time.sleep(5)

        except anthropic.APIStatusError as e:
            err_msg = str(e)
            logger.error(f"[AI검증] API 상태 오류 {e.status_code} ({attempt}/3): {err_msg}")
            if e.status_code in (500, 529):
                time.sleep(5)
            else:
                return _skip_result(f"API 오류 {e.status_code}: {err_msg}")

        except anthropic.APIConnectionError as e:
            logger.warning(f"[AI검증] 연결 오류 ({attempt}/3): {e}")
            time.sleep(5)

        except anthropic.APIError as e:
            logger.error(f"[AI검증] 기타 API 오류 ({attempt}/3): {e}")
            if attempt == 3:
                return _skip_result(f"API 오류: {e}")
            time.sleep(5)

        except Exception as e:
            logger.error(f"[AI검증] 예상치 못한 오류 ({attempt}/3): {e}")
            if attempt == 3:
                return _skip_result(f"알 수 없는 오류: {e}")
            time.sleep(5)

    return _skip_result("3회 재시도 모두 실패")


def _skip_result(reason: str) -> dict:
    return {
        "validation_passed":  None,
        "overall_assessment": f"검증 스킵: {reason}",
        "data_checks":        [],
        "score_checks":       [],
        "anomalies":          [],
        "recommendations":    [],
        "validated_at":       datetime.now(timezone.utc).isoformat(),
        "model":              None,
    }
