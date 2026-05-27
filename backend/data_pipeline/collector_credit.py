import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fredapi import Fred
from typing import Dict, Any
import logging
import os

logger = logging.getLogger(__name__)


def collect_credit_data() -> Dict[str, Any]:
    try:
        fred = Fred(api_key=os.getenv("FRED_API_KEY", ""))

        end_date = datetime.today()
        start_date = end_date - timedelta(days=365 * 2)

        hy_spread_series = fred.get_series(
            "BAMLH0A0HYM2",
            observation_start=start_date.strftime("%Y-%m-%d")
        ).dropna()

        ig_spread_series = fred.get_series(
            "BAMLC0A0CM",
            observation_start=start_date.strftime("%Y-%m-%d")
        ).dropna()

        hy_current = float(hy_spread_series.iloc[-1])
        hy_1m_ago  = float(hy_spread_series.iloc[-22]) if len(hy_spread_series) > 22 else hy_current
        hy_min_1y  = float(hy_spread_series.tail(252).min())
        hy_max_1y  = float(hy_spread_series.tail(252).max())
        hy_pct     = float(hy_spread_series.rank(pct=True).iloc[-1]) * 100

        ig_current = float(ig_spread_series.iloc[-1])
        ig_1m_ago  = float(ig_spread_series.iloc[-22]) if len(ig_spread_series) > 22 else ig_current

        credit_etfs = yf.download(
            ["HYG", "LQD"],
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True
        )["Close"]

        hyg_30d = (credit_etfs["HYG"].iloc[-1] / credit_etfs["HYG"].iloc[-22] - 1) * 100
        lqd_30d = (credit_etfs["LQD"].iloc[-1] / credit_etfs["LQD"].iloc[-22] - 1) * 100
        hyg_lqd_relative = hyg_30d - lqd_30d

        hyg_full = yf.download("HYG", period="3mo", progress=False, auto_adjust=True)
        hyg_vol_avg = float(hyg_full["Volume"].mean())
        hyg_vol_now = float(hyg_full["Volume"].iloc[-1])
        hyg_vol_spike = hyg_vol_now / hyg_vol_avg if hyg_vol_avg > 0 else 1.0

        def to_hist(s, n=180):
            if s is None or len(s) == 0:
                return {"dates": [], "values": []}
            tail = s.tail(n)
            return {
                "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
                "values": [round(float(v), 3) for v in tail.values]
            }

        return {
            "timestamp": datetime.now().isoformat(),
            "hy_spread_current": round(hy_current, 2),
            "hy_spread_1m_ago": round(hy_1m_ago, 2),
            "hy_spread_1m_change": round(hy_current - hy_1m_ago, 2),
            "hy_spread_1y_min": round(hy_min_1y, 2),
            "hy_spread_1y_max": round(hy_max_1y, 2),
            "hy_spread_percentile": round(hy_pct, 1),
            "ig_spread_current": round(ig_current, 2),
            "ig_spread_1m_change": round(ig_current - ig_1m_ago, 2),
            "hyg_30d_return": round(float(hyg_30d), 2),
            "lqd_30d_return": round(float(lqd_30d), 2),
            "hyg_lqd_relative": round(float(hyg_lqd_relative), 2),
            "hyg_volume_spike_ratio": round(hyg_vol_spike, 2),
            "rollover_risk_elevated": hyg_vol_spike > 1.5 or hy_current > hy_1m_ago * 1.15,
            "history": {
                "hy_spread": to_hist(hy_spread_series),
                "ig_spread": to_hist(ig_spread_series),
            },
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"[경고등3] 데이터 수집 실패: {e}")
        return {"status": "error", "message": str(e), "timestamp": datetime.now().isoformat()}


def calculate_credit_score(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("status") == "error":
        return {"raw_score": 50, "grade": "UNKNOWN", "signals": [], "key_metrics": {}}

    score = 0.0
    signals = []

    hy_pct = data.get("hy_spread_percentile", 50)
    hy_now = data.get("hy_spread_current", 400)

    if hy_pct > 80:
        score += 35
        signals.append({"level": "RED", "msg": f"HY 스프레드 {hy_now:.0f}bps — 크레딧 시장 공황 수준"})
    elif hy_pct > 65:
        score += 22
        signals.append({"level": "ORANGE", "msg": f"HY 스프레드 확대 ({hy_now:.0f}bps)"})
    elif hy_pct > 50:
        score += 12
        signals.append({"level": "YELLOW", "msg": f"HY 스프레드 주의 구간 ({hy_now:.0f}bps)"})
    elif hy_pct < 15:
        score += 15
        signals.append({"level": "ORANGE", "msg": f"HY 스프레드 과도 압축 ({hy_now:.0f}bps) — 사모 크레딧 버블 경고"})

    hy_change = data.get("hy_spread_1m_change", 0)
    if hy_change > 100:
        score += 25
        signals.append({"level": "RED", "msg": f"HY 스프레드 1개월 +{hy_change:.0f}bps 급등 — 환매 연쇄 가능성"})
    elif hy_change > 50:
        score += 15
        signals.append({"level": "ORANGE", "msg": f"HY 스프레드 상승 중 (+{hy_change:.0f}bps)"})

    if data.get("rollover_risk_elevated"):
        vol_ratio = data.get("hyg_volume_spike_ratio", 1)
        score += 25
        signals.append({"level": "RED", "msg": f"⚠️ HYG 거래량 {vol_ratio:.1f}배 급증 — 환매 중단 조기 경보"})

    rel = data.get("hyg_lqd_relative", 0)
    if rel < -3:
        score += 15
        signals.append({"level": "RED", "msg": f"HY채권 IG 대비 {abs(rel):.1f}%p 언더퍼폼 — 품질 도피"})
    elif rel < -1.5:
        score += 8
        signals.append({"level": "YELLOW", "msg": f"크레딧 품질 차별화 시작 ({rel:.1f}%p)"})

    score = min(100.0, score)

    if score >= 70:
        grade, grade_color = "CRITICAL", "#FF0000"
    elif score >= 50:
        grade, grade_color = "HIGH", "#FF6600"
    elif score >= 30:
        grade, grade_color = "MEDIUM", "#FFAA00"
    else:
        grade, grade_color = "LOW", "#00CC44"

    return {
        "raw_score": round(score, 1),
        "grade": grade,
        "grade_color": grade_color,
        "signals": signals,
        "key_metrics": {
            "HY 스프레드": f"{hy_now:.0f}bps ({hy_pct:.0f}%ile)",
            "1개월 변화": f"{hy_change:+.0f}bps",
            "HYG 거래량 배율": f"{data.get('hyg_volume_spike_ratio', 1):.2f}x",
            "HYG vs LQD": f"{data.get('hyg_lqd_relative', 0):.2f}%p",
        }
    }
