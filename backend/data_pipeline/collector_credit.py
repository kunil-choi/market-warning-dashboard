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
        fred       = Fred(api_key=os.getenv("FRED_API_KEY", ""))
        end_date   = datetime.today()
        start_date = end_date - timedelta(days=365 * 2)

        # ── FRED 스프레드 시리즈 ──
        series_ids = {
            "hy_spread": "BAMLH0A0HYM2",
            "ig_spread": "BAMLC0A0CM",
        }

        spread_data = {}
        for name, sid in series_ids.items():
            try:
                s = fred.get_series(
                    sid,
                    observation_start=start_date.strftime("%Y-%m-%d"),
                    observation_end=end_date.strftime("%Y-%m-%d")
                ).dropna()
                spread_data[name] = s
            except Exception as e:
                logger.warning(f"FRED {sid} 수집 실패: {e}")

        def latest_spread(name, fallback=0.0):
            s = spread_data.get(name)
            if s is not None and len(s) > 0:
                return float(s.iloc[-1])
            return fallback

        def prev_spread(name, n=22, fallback=None):
            s = spread_data.get(name)
            if s is not None and len(s) > n:
                return float(s.iloc[-n])
            return fallback if fallback is not None else latest_spread(name)

        hy_now     = latest_spread("hy_spread", 400.0)
        ig_now     = latest_spread("ig_spread", 120.0)
        hy_1m_ago  = prev_spread("hy_spread", n=22)
        ig_1m_ago  = prev_spread("ig_spread", n=22)

        hy_change_1m = hy_now - hy_1m_ago
        ig_change_1m = ig_now - ig_1m_ago

        # 1년 퍼센타일
        hy_series = spread_data.get("hy_spread")
        ig_series = spread_data.get("ig_spread")

        if hy_series is not None and len(hy_series) >= 60:
            hy_1y     = hy_series.tail(252)
            hy_1y_min = float(hy_1y.min())
            hy_1y_max = float(hy_1y.max())
            hy_pct    = float(hy_series.rank(pct=True).iloc[-1]) * 100
        else:
            hy_1y_min, hy_1y_max, hy_pct = 0.0, 0.0, 50.0

        if ig_series is not None and len(ig_series) >= 60:
            ig_1y     = ig_series.tail(252)
            ig_1y_min = float(ig_1y.min())
            ig_1y_max = float(ig_1y.max())
            ig_pct    = float(ig_series.rank(pct=True).iloc[-1]) * 100
        else:
            ig_1y_min, ig_1y_max, ig_pct = 0.0, 0.0, 50.0

        # ── HYG / LQD ETF 다운로드 ──
        raw_etf = yf.download(
            ["HYG", "LQD"],
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True
        )

        # MultiIndex 처리
        if isinstance(raw_etf.columns, pd.MultiIndex):
            etf_close  = raw_etf["Close"]
            etf_volume = raw_etf["Volume"]
        else:
            etf_close  = raw_etf
            etf_volume = pd.DataFrame()

        # fillna(method=) 대신 .ffill() 사용 (pandas 2.x 호환)
        etf_close  = etf_close.dropna(how="all")
        etf_close  = etf_close.ffill()
        etf_volume = etf_volume.dropna(how="all")
        etf_volume = etf_volume.fillna(0)

        # HYG / LQD 30일 수익률
        hyg_30d_return = 0.0
        lqd_30d_return = 0.0
        if "HYG" in etf_close.columns and len(etf_close["HYG"].dropna()) > 30:
            hyg_30d_return = float(
                (etf_close["HYG"].iloc[-1] / etf_close["HYG"].iloc[-30] - 1) * 100
            )
        if "LQD" in etf_close.columns and len(etf_close["LQD"].dropna()) > 30:
            lqd_30d_return = float(
                (etf_close["LQD"].iloc[-1] / etf_close["LQD"].iloc[-30] - 1) * 100
            )

        hyg_lqd_relative = hyg_30d_return - lqd_30d_return

        # HYG 거래량 급증 비율
        volume_spike_ratio = 1.0
        if "HYG" in etf_volume.columns:
            hyg_vol = etf_volume["HYG"].dropna()
            if len(hyg_vol) > 60:
                vol_5d  = float(hyg_vol.tail(5).mean())
                vol_60d = float(hyg_vol.tail(60).mean())
                if vol_60d > 0:
                    volume_spike_ratio = round(vol_5d / vol_60d, 2)

        # 환매 위험 플래그
        rollover_risk_elevated = bool(
            hy_change_1m > 50
            or hy_pct > 80
            or volume_spike_ratio > 1.5
        )

        # 히스토리
        def to_hist(s, n=180):
            if s is None or len(s) == 0:
                return {"dates": [], "values": []}
            tail = s.tail(n)
            return {
                "dates":  [d.strftime("%Y-%m-%d") for d in tail.index],
                "values": [round(float(v), 3) for v in tail.values]
            }

        return {
            "timestamp":              datetime.now().isoformat(),
            "hy_spread_current":      round(hy_now, 2),
            "ig_spread_current":      round(ig_now, 2),
            "hy_change_1m":           round(hy_change_1m, 2),
            "ig_change_1m":           round(ig_change_1m, 2),
            "hy_1y_min":              round(hy_1y_min, 2),
            "hy_1y_max":              round(hy_1y_max, 2),
            "hy_percentile":          round(hy_pct, 1),
            "ig_1y_min":              round(ig_1y_min, 2),
            "ig_1y_max":              round(ig_1y_max, 2),
            "ig_percentile":          round(ig_pct, 1),
            "hyg_30d_return":         round(hyg_30d_return, 2),
            "lqd_30d_return":         round(lqd_30d_return, 2),
            "hyg_lqd_relative":       round(hyg_lqd_relative, 2),
            "volume_spike_ratio":     round(volume_spike_ratio, 2),
            "rollover_risk_elevated": rollover_risk_elevated,
            "history": {
                "hy_spread": to_hist(spread_data.get("hy_spread")),
                "ig_spread": to_hist(spread_data.get("ig_spread")),
            },
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"[경고등3] 데이터 수집 실패: {e}")
        return {
            "status":                 "error",
            "message":                str(e),
            "timestamp":              datetime.now().isoformat(),
            "rollover_risk_elevated": False,
        }


def calculate_credit_score(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("status") == "error":
        return {
            "raw_score":   50,
            "grade":       "UNKNOWN",
            "grade_color": "#888888",
            "signals":     [],
            "key_metrics": {}
        }

    score   = 0.0
    signals = []

    hy_pct = data.get("hy_percentile", 50)
    if hy_pct > 80:
        score += 35
        signals.append({"level": "RED",    "msg": f"HY 스프레드 역대 상위 {100-hy_pct:.0f}% — 신용 경색 임박"})
    elif hy_pct > 65:
        score += 22
        signals.append({"level": "ORANGE", "msg": f"HY 스프레드 확대 경계 ({hy_pct:.0f}%ile)"})
    elif hy_pct > 50:
        score += 12
        signals.append({"level": "YELLOW", "msg": f"HY 스프레드 중간 이상 ({hy_pct:.0f}%ile)"})

    hy_change = data.get("hy_change_1m", 0)
    if hy_change > 100:
        score += 30
        signals.append({"level": "RED",    "msg": f"⚠️ HY 스프레드 1달 새 +{hy_change:.0f}bps — 패닉 매도 신호"})
    elif hy_change > 50:
        score += 20
        signals.append({"level": "RED",    "msg": f"HY 스프레드 급등 +{hy_change:.0f}bps"})
    elif hy_change > 20:
        score += 10
        signals.append({"level": "ORANGE", "msg": f"HY 스프레드 확대 +{hy_change:.0f}bps"})

    if data.get("rollover_risk_elevated"):
        score += 20
        signals.append({"level": "RED",    "msg": "🚨 사모 크레딧 환매 위험 — 복합 지표 임계값 초과"})

    relative = data.get("hyg_lqd_relative", 0)
    if relative < -5:
        score += 15
        signals.append({"level": "RED",    "msg": f"HYG-LQD 상대 성과 {relative:.1f}% — 하이일드 이탈 가속"})
    elif relative < -2:
        score += 8
        signals.append({"level": "ORANGE", "msg": f"HYG 상대 약세 ({relative:.1f}%)"})

    vol_spike = data.get("volume_spike_ratio", 1.0)
    if vol_spike > 2.0:
        score += 10
        signals.append({"level": "RED",    "msg": f"HYG 거래량 {vol_spike:.1f}배 급증 — 패닉 환매 감지"})
    elif vol_spike > 1.5:
        score += 5
        signals.append({"level": "ORANGE", "msg": f"HYG 거래량 증가 ({vol_spike:.1f}배)"})

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
            "HY 스프레드":     f"{data.get('hy_spread_current', 0):.0f}bps",
            "IG 스프레드":     f"{data.get('ig_spread_current', 0):.0f}bps",
            "HY 1개월 변화":   f"+{data.get('hy_change_1m', 0):.0f}bps",
            "HYG 거래량 배율": f"{data.get('volume_spike_ratio', 1):.1f}배",
        }
    }
