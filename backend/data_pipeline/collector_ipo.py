import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

MEGA_IPO_WATCHLIST = [
    {"company": "SpaceX",      "est_valuation_bn": 350, "status": "Considering", "sector": "AI/Space"},
    {"company": "OpenAI",      "est_valuation_bn": 300, "status": "Considering", "sector": "AI"},
    {"company": "Anthropic",   "est_valuation_bn": 60,  "status": "Considering", "sector": "AI"},
    {"company": "Stripe",      "est_valuation_bn": 65,  "status": "Considering", "sector": "Fintech"},
    {"company": "Databricks",  "est_valuation_bn": 62,  "status": "Considering", "sector": "AI/Data"},
]


def collect_ipo_data() -> Dict[str, Any]:
    try:
        end   = datetime.today()
        start = end - timedelta(days=180)

        # ── IPO ETF 다운로드 (MultiIndex 처리) ──
        raw_ipo = yf.download(
            ["IPO", "IPOS"],
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True
        )

        if isinstance(raw_ipo.columns, pd.MultiIndex):
            ipo_etf = raw_ipo["Close"]
        else:
            ipo_etf = raw_ipo

        ipo_etf = ipo_etf.dropna(how="all")

        ipo_etf_90d = {}
        for t in ["IPO", "IPOS"]:
            if t in ipo_etf.columns and len(ipo_etf[t].dropna()) > 5:
                s = ipo_etf[t].dropna()
                lookback = min(63, len(s) - 1)
                ipo_etf_90d[t] = round(
                    float(s.iloc[-1] / s.iloc[-lookback] - 1) * 100, 2
                )

        # ── 최근 대형 IPO 성과 ──
        recent_large_ipos = {
            "ARM":  "ARM Holdings",
            "RDDT": "Reddit",
            "ALAB": "Astera Labs"
        }
        ipo_performance = {}
        for ticker, name in recent_large_ipos.items():
            try:
                hist = yf.Ticker(ticker).history(period="6mo")
                if len(hist) > 0:
                    ipo_performance[ticker] = {
                        "name":          name,
                        "current_price": round(float(hist["Close"].iloc[-1]), 2),
                        "6m_return":     round(
                            float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2
                        ),
                    }
            except Exception as e:
                logger.warning(f"IPO 성과 수집 실패 ({ticker}): {e}")

        # ── 파이프라인 집계 ──
        total_pipeline_bn = sum(
            c["est_valuation_bn"]
            for c in MEGA_IPO_WATCHLIST
            if c["status"] in ["Considering", "Filed"]
        )
        estimated_market_impact_bn = total_pipeline_bn * 0.20
        korea_gdp_bn               = 1700
        pipeline_vs_korea_gdp      = total_pipeline_bn / korea_gdp_bn

        # ── VIX (NaN 처리 추가) ──
        raw_vix = yf.download("^VIX", period="3mo", progress=False, auto_adjust=True)

        if isinstance(raw_vix.columns, pd.MultiIndex):
            vix_series = raw_vix["Close"].dropna()
        else:
            vix_series = raw_vix["Close"].dropna() if "Close" in raw_vix.columns else raw_vix.iloc[:, 0].dropna()

        if len(vix_series) == 0:
            raise ValueError("VIX 데이터가 비어 있습니다.")

        vix_current  = float(vix_series.iloc[-1])
        vix_avg_3m   = float(vix_series.mean())
        vix_is_low   = vix_current < 15

        # ── IPO 과열 지수 ──
        ipo_heat_index = 0
        if vix_is_low:
            ipo_heat_index += 30
        if ipo_etf_90d.get("IPO", 0) > 20:
            ipo_heat_index += 25
        if total_pipeline_bn > 500:
            ipo_heat_index += 30

        active_count     = sum(1 for c in MEGA_IPO_WATCHLIST if c["status"] == "Filed")
        considering_count = sum(1 for c in MEGA_IPO_WATCHLIST if c["status"] == "Considering")

        return {
            "timestamp":                   datetime.now().isoformat(),
            "mega_ipo_pipeline":           MEGA_IPO_WATCHLIST,
            "total_pipeline_bn":           round(float(total_pipeline_bn), 0),
            "estimated_market_impact_bn":  round(float(estimated_market_impact_bn), 0),
            "pipeline_vs_korea_gdp_ratio": round(float(pipeline_vs_korea_gdp), 2),
            "ipo_etf_90d_returns":         ipo_etf_90d,
            "recent_ipo_performance":      ipo_performance,
            "vix_current":                 round(vix_current, 2),
            "vix_avg_3m":                  round(vix_avg_3m, 2),
            "vix_is_extreme_low":          bool(vix_is_low),
            "ipo_heat_index":              min(100, int(ipo_heat_index)),
            "active_ipo_count":            active_count,
            "considering_ipo_count":       considering_count,
            "status": "ok"
        }

    except Exception as e:
        logger.error(f"[경고등4] 데이터 수집 실패: {e}")
        return {
            "status":    "error",
            "message":   str(e),
            "timestamp": datetime.now().isoformat()
        }


def calculate_ipo_score(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("status") == "error":
        return {"raw_score": 50, "grade": "UNKNOWN", "signals": [], "key_metrics": {}}

    score   = 0.0
    signals = []

    pipeline = data.get("total_pipeline_bn", 0)
    if pipeline > 700:
        score += 35
        signals.append({"level": "RED",    "msg": f"메가 IPO 파이프라인 ${pipeline:.0f}Bn — 유동성 블랙홀"})
    elif pipeline > 400:
        score += 22
        signals.append({"level": "ORANGE", "msg": f"대규모 IPO 파이프라인 대기 (${pipeline:.0f}Bn)"})
    elif pipeline > 200:
        score += 12
        signals.append({"level": "YELLOW", "msg": f"IPO 파이프라인 주목 (${pipeline:.0f}Bn)"})

    if data.get("vix_is_extreme_low"):
        score += 25
        signals.append({
            "level": "RED",
            "msg":   f"⚠️ VIX {data.get('vix_current', 20):.1f} 극단적 저점 — IPO 흥행 마지막 조건 충족"
        })

    ipo_ret = data.get("ipo_etf_90d_returns", {}).get("IPO", 0)
    if ipo_ret > 30:
        score += 25
        signals.append({"level": "RED",    "msg": f"IPO ETF 90일 +{ipo_ret:.0f}% — 파티의 마지막 신호"})
    elif ipo_ret > 15:
        score += 15
        signals.append({"level": "ORANGE", "msg": f"IPO 시장 과열 (+{ipo_ret:.0f}%)"})

    active = data.get("active_ipo_count", 0)
    if active >= 2:
        score += 15
        signals.append({"level": "RED",    "msg": f"대어급 IPO {active}건 동시 진행 — 스펀지 효과 임박"})
    elif active == 1:
        score += 8
        signals.append({"level": "YELLOW", "msg": "대어급 IPO 청약 진행 중"})

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
            "IPO 파이프라인":  f"${pipeline:.0f}Bn",
            "한국 GDP 대비":   f"{data.get('pipeline_vs_korea_gdp_ratio', 0):.1f}배",
            "VIX":            f"{data.get('vix_current', 0):.1f}",
            "IPO ETF 90일":   f"+{ipo_ret:.1f}%",
        }
    }
