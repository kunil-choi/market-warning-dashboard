import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fredapi import Fred
from typing import Dict, Any
import logging
import os

logger = logging.getLogger(__name__)

# 시리즈별 lookback 기간 분리
T10Y_LOOKBACK_DAYS   = 66   # 약 3개월 거래일 (일간 시리즈)
FED_LOOKBACK_MONTHS  = 3    # 3개월 (월간 시리즈)


def collect_rates_data() -> Dict[str, Any]:
    try:
        fred       = Fred(api_key=os.getenv("FRED_API_KEY", ""))
        end_date   = datetime.today()
        start_date = end_date - timedelta(days=365 * 2)

        series_ids = {
            "fed_funds": "FEDFUNDS",
            "t10y":      "DGS10",
            "t2y":       "DGS2",
            "real10y":   "DFII10",
            "cpi":       "CPIAUCSL",
        }

        rate_data = {}
        for name, sid in series_ids.items():
            try:
                s = fred.get_series(
                    sid,
                    observation_start=start_date.strftime("%Y-%m-%d"),
                    observation_end=end_date.strftime("%Y-%m-%d")
                ).dropna()
                rate_data[name] = s
            except Exception as e:
                logger.warning(f"FRED {sid} 수집 실패: {e}")

        def latest(name, fallback=0.0):
            s = rate_data.get(name)
            if s is not None and len(s) > 0:
                return float(s.iloc[-1])
            return fallback

        # ── 일간 시리즈 (DGS10, DGS2, DFII10): 거래일 기준 lookback ──
        def prev_daily(name, n=T10Y_LOOKBACK_DAYS, fallback=None):
            s = rate_data.get(name)
            if s is not None and len(s) > n:
                return float(s.iloc[-n])
            return fallback if fallback is not None else latest(name)

        # ── 월간 시리즈 (FEDFUNDS, CPIAUCSL): 월 단위 lookback ──
        def prev_monthly(name, n=FED_LOOKBACK_MONTHS, fallback=None):
            s = rate_data.get(name)
            if s is not None and len(s) > n:
                return float(s.iloc[-n])
            return fallback if fallback is not None else latest(name)

        t10y_now    = latest("t10y",      4.5)
        t2y_now     = latest("t2y",       4.2)
        fed_now     = latest("fed_funds", 4.25)
        real10y     = latest("real10y",   2.0)

        # 각 시리즈에 맞는 lookback 적용
        t10y_3m_ago = prev_daily("t10y",      T10Y_LOOKBACK_DAYS)
        fed_3m_ago  = prev_monthly("fed_funds", FED_LOOKBACK_MONTHS)

        yield_curve        = t10y_now - t2y_now
        vigilante_spread   = t10y_now - fed_now
        vigilante_triggered = (
            float(fed_now) < float(fed_3m_ago)
        ) and (
            float(t10y_now) > float(t10y_3m_ago)
        )

        # CPI YoY (월간 시리즈: 12개월 전과 비교)
        cpi_series = rate_data.get("cpi")
        cpi_yoy = None
        if cpi_series is not None and len(cpi_series) >= 13:
            cpi_yoy = float(
                (cpi_series.iloc[-1] / cpi_series.iloc[-13] - 1) * 100
            )

        def to_hist(s, n=180):
            if s is None or len(s) == 0:
                return {"dates": [], "values": []}
            tail = s.tail(n)
            return {
                "dates":  [d.strftime("%Y-%m-%d") for d in tail.index],
                "values": [round(float(v), 3) for v in tail.values]
            }

        checklist = {
            "fiscal_debt_excess":      True,
            "inflation_control_weak":  (cpi_yoy or 0) > 2.5,
            "fed_independence_risk":   vigilante_triggered,
        }

        return {
            "timestamp":           datetime.now().isoformat(),
            "t10y_current":        round(t10y_now, 3),
            "t2y_current":         round(t2y_now, 3),
            "fed_funds_current":   round(fed_now, 3),
            "real10y_current":     round(real10y, 3),
            "yield_curve_10y2y":   round(yield_curve, 3),
            "vigilante_spread":    round(vigilante_spread, 3),
            "vigilante_triggered": bool(vigilante_triggered),
            "cpi_yoy":             round(cpi_yoy, 2) if cpi_yoy is not None else None,
            "bond_vigilante_checklist": checklist,
            "checklist_met_count": int(sum(checklist.values())),
            "history": {
                "t10y":      to_hist(rate_data.get("t10y")),
                "t2y":       to_hist(rate_data.get("t2y")),
                "fed_funds": to_hist(rate_data.get("fed_funds")),
                "real10y":   to_hist(rate_data.get("real10y")),
            },
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"[경고등2] 데이터 수집 실패: {e}")
        return {
            "status":    "error",
            "message":   str(e),
            "timestamp": datetime.now().isoformat()
        }


def calculate_rates_score(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("status") == "error":
        return {"raw_score": 50, "grade": "UNKNOWN", "signals": [], "key_metrics": {}}

    score   = 0.0
    signals = []

    checklist_count = data.get("checklist_met_count", 0)
    if checklist_count >= 3:
        score += 40
        signals.append({"level": "RED",    "msg": "🚨 채권 자경단 3요소 모두 충족 — 국채 투매 위험 최고조"})
    elif checklist_count == 2:
        score += 25
        signals.append({"level": "ORANGE", "msg": f"채권 자경단 {checklist_count}/3 조건 충족"})
    elif checklist_count == 1:
        score += 10
        signals.append({"level": "YELLOW", "msg": f"채권 자경단 {checklist_count}/3 조건 — 모니터링 필요"})

    if data.get("vigilante_triggered"):
        score += 30
        signals.append({"level": "RED", "msg": "⚠️ 연준 금리 인하에도 10Y 국채 상승 — 채권 자경단 현실화"})

    real10y = data.get("real10y_current", 0)
    if real10y > 2.5:
        score += 20
        signals.append({"level": "RED",    "msg": f"실질 10년 금리 {real10y:.2f}% — 주식 밸류에이션 직격탄"})
    elif real10y > 1.5:
        score += 12
        signals.append({"level": "ORANGE", "msg": f"실질 금리 상승 압력 ({real10y:.2f}%)"})

    cpi = data.get("cpi_yoy") or 2.0
    if cpi > 3.5:
        score += 10
        signals.append({"level": "ORANGE", "msg": f"CPI {cpi:.1f}% — 조기 금리 인하 명분 취약"})

    score = min(100.0, score)

    if score >= 70:
        grade, grade_color = "CRITICAL", "#FF0000"
    elif score >= 50:
        grade, grade_color = "HIGH",     "#FF6600"
    elif score >= 30:
        grade, grade_color = "MEDIUM",   "#FFAA00"
    else:
        grade, grade_color = "LOW",      "#00CC44"

    return {
        "raw_score":   round(score, 1),
        "grade":       grade,
        "grade_color": grade_color,
        "signals":     signals,
        "key_metrics": {
            "10년 국채금리":    f"{data.get('t10y_current', 0):.2f}%",
            "자경단 스프레드":  f"{data.get('vigilante_spread', 0):.2f}%p",
            "실질 10년 금리":  f"{data.get('real10y_current', 0):.2f}%",
            "CPI YoY":         f"{cpi:.1f}%",
        }
    }
