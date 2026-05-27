import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

def collect_liquidity_funnel_data() -> Dict[str, Any]:
    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=252)
        tickers = ["SPY", "RSP", "QQQ", "DIA", "IWM", "NVDA"]

        raw = yf.download(
            tickers,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True
        )

        # ── MultiIndex 평탄화 처리 ──
        if isinstance(raw.columns, pd.MultiIndex):
            data = raw["Close"]
        else:
            data = raw

        # NaN 제거
        data = data.dropna()

        normalized = (data / data.iloc[0]) * 100

        spy_rsp_spread   = normalized["SPY"] - normalized["RSP"]
        rsp_20d_return   = (data["RSP"].iloc[-1] / data["RSP"].iloc[-20] - 1) * 100
        spy_20d_return   = (data["SPY"].iloc[-1] / data["SPY"].iloc[-20] - 1) * 100
        concentration_score = spy_20d_return - rsp_20d_return

        spy_ytd  = (data["SPY"].iloc[-1] / data["SPY"].iloc[0] - 1) * 100
        rsp_ytd  = (data["RSP"].iloc[-1] / data["RSP"].iloc[0] - 1) * 100
        qqq_ytd  = (data["QQQ"].iloc[-1] / data["QQQ"].iloc[0] - 1) * 100
        dia_ytd  = (data["DIA"].iloc[-1] / data["DIA"].iloc[0] - 1) * 100
        iwm_ytd  = (data["IWM"].iloc[-1] / data["IWM"].iloc[0] - 1) * 100
        nvda_ytd = (data["NVDA"].iloc[-1] / data["NVDA"].iloc[0] - 1) * 100

        rsp_1w_return  = (data["RSP"].iloc[-1] / data["RSP"].iloc[-5] - 1) * 100
        rsp_is_negative = bool(rsp_1w_return < 0 and spy_20d_return > 0)

        current_spread     = float(spy_rsp_spread.iloc[-1])
        spread_percentile  = float(spy_rsp_spread.rank(pct=True).iloc[-1]) * 100

        # ── 히스토리: float() 캐스팅으로 JSON 직렬화 오류 방지 ──
        tail90 = data.tail(90)
        norm90 = normalized.tail(90)

        history_90d = {
            "dates": [d.strftime("%Y-%m-%d") for d in tail90.index],
            "spy":   [round(float(v), 2) for v in norm90["SPY"].values],
            "rsp":   [round(float(v), 2) for v in norm90["RSP"].values],
            "qqq":   [round(float(v), 2) for v in norm90["QQQ"].values],
            "dia":   [round(float(v), 2) for v in norm90["DIA"].values],
            "iwm":   [round(float(v), 2) for v in norm90["IWM"].values],
        }

        return {
            "timestamp":   datetime.now().isoformat(),
            "spy_ytd":     round(float(spy_ytd), 2),
            "rsp_ytd":     round(float(rsp_ytd), 2),
            "qqq_ytd":     round(float(qqq_ytd), 2),
            "dia_ytd":     round(float(dia_ytd), 2),
            "iwm_ytd":     round(float(iwm_ytd), 2),
            "nvda_ytd":    round(float(nvda_ytd), 2),
            "spy_20d_return":  round(float(spy_20d_return), 2),
            "rsp_20d_return":  round(float(rsp_20d_return), 2),
            "rsp_1w_return":   round(float(rsp_1w_return), 2),
            "concentration_score": round(float(concentration_score), 2),
            "current_spread":      round(current_spread, 2),
            "spread_percentile":   round(spread_percentile, 1),
            "rsp_is_negative_while_spy_positive": rsp_is_negative,
            "history_90d": history_90d,
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"[경고등1] 데이터 수집 실패: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }


def calculate_liquidity_score(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("status") == "error":
        return {"raw_score": 50, "grade": "UNKNOWN", "signals": [], "key_metrics": {}}

    score   = 0.0
    signals = []

    spread_pct = data.get("spread_percentile", 50)
    if spread_pct > 90:
        score += 35
        signals.append({"level": "RED",    "msg": f"SPY-RSP 괴리 역대 상위 {100-spread_pct:.0f}% — 극단적 주도주 집중"})
    elif spread_pct > 75:
        score += 25
        signals.append({"level": "ORANGE", "msg": f"SPY-RSP 괴리 상위 {100-spread_pct:.0f}% — 주도주 압축 진행 중"})
    elif spread_pct > 60:
        score += 15
        signals.append({"level": "YELLOW", "msg": "SPY-RSP 괴리 확대 주시 필요"})

    if data.get("rsp_is_negative_while_spy_positive"):
        score += 30
        signals.append({"level": "RED", "msg": "⚠️ TRIGGER: RSP 음수 전환, SPY 양수 유지 — 닷컴 버블 패턴"})

    qqq = data.get("qqq_ytd", 0)
    dia = data.get("dia_ytd", 0)
    iwm = data.get("iwm_ytd", 0)
    breadth_gap = qqq - (dia + iwm) / 2

    if breadth_gap > 30:
        score += 20
        signals.append({"level": "RED",    "msg": f"나스닥 vs 다우/러셀 괴리 {breadth_gap:.1f}pt — 시장 폭 극단 축소"})
    elif breadth_gap > 15:
        score += 12
        signals.append({"level": "ORANGE", "msg": f"기술주 집중도 심화 ({breadth_gap:.1f}pt)"})

    conc = data.get("concentration_score", 0)
    if conc > 10:
        score += 15
        signals.append({"level": "RED",    "msg": f"단기 주도주 집중도 {conc:.1f}pt — FOMO 자금 한계 근접"})
    elif conc > 5:
        score += 8
        signals.append({"level": "YELLOW", "msg": f"주도주 가속 이탈 ({conc:.1f}pt)"})

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
            "SPY-RSP 괴리 퍼센타일": f"{spread_pct:.0f}%ile",
            "RSP 1주 수익률":        f"{data.get('rsp_1w_return', 0):.2f}%",
            "SPY YTD":              f"{data.get('spy_ytd', 0):.2f}%",
            "RSP YTD":              f"{data.get('rsp_ytd', 0):.2f}%",
        }
    }
