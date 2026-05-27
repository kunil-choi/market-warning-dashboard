import json
import logging
from datetime import datetime
from typing import Dict, Any

from backend.data_pipeline.collector_liquidity import (
    collect_liquidity_funnel_data, calculate_liquidity_score
)
from backend.data_pipeline.collector_rates import (
    collect_rates_data, calculate_rates_score
)
from backend.data_pipeline.collector_credit import (
    collect_credit_data, calculate_credit_score
)
from backend.data_pipeline.collector_ipo import (
    collect_ipo_data, calculate_ipo_score
)

logger = logging.getLogger(__name__)


def run_full_scoring() -> Dict[str, Any]:
    logger.info("=" * 60)
    logger.info("🚨 맹목적 강세장 경고 대시보드 — 스코어링 시작")
    logger.info("=" * 60)

    raw_data = {}
    raw_data["liquidity"] = collect_liquidity_funnel_data()
    raw_data["rates"]     = collect_rates_data()
    raw_data["credit"]    = collect_credit_data()
    raw_data["ipo"]       = collect_ipo_data()

    scores = {}
    scores["liquidity"] = calculate_liquidity_score(raw_data["liquidity"])
    scores["rates"]     = calculate_rates_score(raw_data["rates"])
    scores["credit"]    = calculate_credit_score(raw_data["credit"])
    scores["ipo"]       = calculate_ipo_score(raw_data["ipo"])

    w = {"liquidity": 0.30, "rates": 0.25, "credit": 0.25, "ipo": 0.20}

    composite_score = (
        scores["liquidity"]["raw_score"] * w["liquidity"] +
        scores["rates"]["raw_score"]     * w["rates"]     +
        scores["credit"]["raw_score"]    * w["credit"]    +
        scores["ipo"]["raw_score"]       * w["ipo"]
    )

    high_warnings = sum(1 for s in scores.values() if s["raw_score"] >= 50)
    critical_warnings = sum(1 for s in scores.values() if s["raw_score"] >= 70)

    perfect_storm_bonus = 0
    if critical_warnings >= 3:
        perfect_storm_bonus = 15
    elif critical_warnings >= 2:
        perfect_storm_bonus = 10
    elif high_warnings >= 3:
        perfect_storm_bonus = 5

    final_score = min(100.0, composite_score + perfect_storm_bonus)

    if final_score >= 80:
        overall_grade = "PERFECT_STORM"
        overall_color = "#CC0000"
        overall_label = "🚨 퍼펙트 스톰 임박"
        action = "즉각 위험 관리 — 포지션 축소 및 헤지 실행"
    elif final_score >= 65:
        overall_grade = "CRITICAL"
        overall_color = "#FF0000"
        overall_label = "⛔ 위험 최고조"
        action = "공격적 리스크 감축 — 브레이크 준비 완료"
    elif final_score >= 50:
        overall_grade = "HIGH"
        overall_color = "#FF4400"
        overall_label = "⚠️ 위험 높음"
        action = "방어적 운용 — 신규 진입 자제, 손절 라인 점검"
    elif final_score >= 35:
        overall_grade = "ELEVATED"
        overall_color = "#FF8800"
        overall_label = "🟡 경계 구간"
        action = "백미러 모니터링 강화 — 주간 단위 점검"
    elif final_score >= 20:
        overall_grade = "MODERATE"
        overall_color = "#FFCC00"
        overall_label = "🟢 보통 수준"
        action = "정상 운용 — 정기 모니터링 유지"
    else:
        overall_grade = "LOW"
        overall_color = "#00CC44"
        overall_label = "✅ 위험 낮음"
        action = "공격적 운용 가능 — 기회 탐색 모드"

    algo_signal = generate_algo_signal(scores, final_score, raw_data)

    output = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "version": "2.0",
            "source": "김효진 박사 강연 기반 매크로 대시보드",
        },
        "composite": {
            "final_score":            round(final_score, 1),
            "weighted_score":         round(composite_score, 1),
            "perfect_storm_bonus":    perfect_storm_bonus,
            "overall_grade":          overall_grade,
            "overall_color":          overall_color,
            "overall_label":          overall_label,
            "action_recommended":     action,
            "high_warning_count":     high_warnings,
            "critical_warning_count": critical_warnings,
        },
        "warnings": {
            "w1_liquidity": {
                "name":        "경고등 1: 주도주 압축",
                "icon":        "🔽",
                "score":       scores["liquidity"]["raw_score"],
                "grade":       scores["liquidity"]["grade"],
                "grade_color": scores["liquidity"]["grade_color"],
                "signals":     scores["liquidity"]["signals"],
                "key_metrics": scores["liquidity"]["key_metrics"],
                "raw_data":    raw_data["liquidity"],
            },
            "w2_rates": {
                "name":        "경고등 2: 채권 자경단 & 금리",
                "icon":        "📈",
                "score":       scores["rates"]["raw_score"],
                "grade":       scores["rates"]["grade"],
                "grade_color": scores["rates"]["grade_color"],
                "signals":     scores["rates"]["signals"],
                "key_metrics": scores["rates"]["key_metrics"],
                "raw_data":    raw_data["rates"],
            },
            "w3_credit": {
                "name":        "경고등 3: 사모 크레딧 환매",
                "icon":        "🔒",
                "score":       scores["credit"]["raw_score"],
                "grade":       scores["credit"]["grade"],
                "grade_color": scores["credit"]["grade_color"],
                "signals":     scores["credit"]["signals"],
                "key_metrics": scores["credit"]["key_metrics"],
                "raw_data":    raw_data["credit"],
            },
            "w4_ipo": {
                "name":        "경고등 4: 대어급 IPO 유동성",
                "icon":        "🐳",
                "score":       scores["ipo"]["raw_score"],
                "grade":       scores["ipo"]["grade"],
                "grade_color": scores["ipo"]["grade_color"],
                "signals":     scores["ipo"]["signals"],
                "key_metrics": scores["ipo"]["key_metrics"],
                "raw_data":    raw_data["ipo"],
            },
        },
        "algo_signal": algo_signal,
    }

    logger.info(f"✅ 스코어링 완료: {final_score:.1f}/100 [{overall_grade}]")
    return output


def generate_algo_signal(
    scores: Dict, final_score: float, raw_data: Dict
) -> Dict[str, Any]:

    rsp_trigger    = raw_data.get("liquidity", {}).get("rsp_is_negative_while_spy_positive", False)
    vig_trigger    = raw_data.get("rates", {}).get("vigilante_triggered", False)
    credit_trigger = raw_data.get("credit", {}).get("rollover_risk_elevated", False)

    if final_score >= 80 and sum([rsp_trigger, vig_trigger, credit_trigger]) >= 2:
        signal      = "STRONG_SELL"
        signal_color = "#CC0000"
        signal_desc  = "즉각 공격적 매도 — 퍼펙트 스톰 다중 트리거 발동"
        hedge_rec    = "SPY 풋옵션 매수, 국채 TLT 롱, 달러 현금 비중 확대"
    elif final_score >= 65:
        signal      = "SELL"
        signal_color = "#FF2200"
        signal_desc  = "포지션 축소 — 고위험 자산 비중 감축"
        hedge_rec    = "베타 축소, 방어주 로테이션, 변동성 헤지 검토"
    elif final_score >= 50:
        signal      = "REDUCE"
        signal_color = "#FF6600"
        signal_desc  = "신규 매수 자제 — 트레일링 스톱 설정"
        hedge_rec    = "동일가중 지수(RSP) 비중 확인, 개별 손절선 점검"
    elif final_score >= 35:
        signal      = "NEUTRAL_CAUTION"
        signal_color = "#FFAA00"
        signal_desc  = "중립 — 주간 단위 4대 지표 모니터링"
        hedge_rec    = "현재 포지션 유지, 경고등 추가 점등 시 즉시 재평가"
    elif final_score >= 20:
        signal      = "HOLD"
        signal_color = "#99CC00"
        signal_desc  = "보유 — 시장 정상 범위"
        hedge_rec    = "정상 운용, 월간 리밸런싱 유지"
    else:
        signal      = "BUY_OPPORTUNITY"
        signal_color = "#00CC44"
        signal_desc  = "매수 기회 탐색 — 위험 지표 낮음"
        hedge_rec    = "공격적 포지션 구축 가능"

    return {
        "signal":       signal,
        "signal_color": signal_color,
        "signal_desc":  signal_desc,
        "hedge_rec":    hedge_rec,
        "trigger_flags": {
            "rsp_negative_trigger":    rsp_trigger,
            "bond_vigilante_trigger":  vig_trigger,
            "credit_rollover_trigger": credit_trigger,
        },
        "generated_at": datetime.now().isoformat(),
    }
