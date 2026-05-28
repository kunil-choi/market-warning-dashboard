import yfinance as yf
import pandas as pd
import numpy as np
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

# ── 백업 기준 리스트 (뉴스 파싱 실패 시 사용) ──
MEGA_IPO_FALLBACK = [
    {"company": "SpaceX",     "est_valuation_bn": 350, "status": "Considering", "sector": "AI/Space"},
    {"company": "OpenAI",     "est_valuation_bn": 300, "status": "Considering", "sector": "AI"},
    {"company": "Anthropic",  "est_valuation_bn": 60,  "status": "Considering", "sector": "AI"},
    {"company": "Stripe",     "est_valuation_bn": 65,  "status": "Considering", "sector": "Fintech"},
    {"company": "Databricks", "est_valuation_bn": 62,  "status": "Considering", "sector": "AI/Data"},
]

# ── 상태별 가중치 ──
STATUS_WEIGHT = {
    "Filed":       1.0,   # S-1 실제 제출
    "Priced":      1.0,   # 공모가 확정
    "Considering": 0.3,   # 검토 중 (언론 추정)
    "Rumored":     0.1,   # 루머
    "Trading":     0.0,   # 이미 상장 완료
}

# ── IPO 관련 키워드 ──
IPO_KEYWORDS = [
    "IPO", "initial public offering", "going public",
    "S-1", "filed with SEC", "public listing",
    "valuation", "billion", "unicorn"
]

# ── 대형 테크 기업 감지 키워드 ──
MEGA_COMPANIES = [
    "SpaceX", "OpenAI", "Anthropic", "Stripe", "Databricks",
    "Klarna", "Chime", "Plaid", "Instacart", "Reddit",
    "Discord", "Canva", "Shein", "ByteDance", "TikTok"
]


def fetch_sec_edgar_ipo_rss() -> List[Dict]:
    """SEC EDGAR에서 실제 S-1 제출 건 감지"""
    results = []
    try:
        url = "https://efts.sec.gov/LATEST/search-index?q=%22S-1%22&dateRange=custom&startdt={}&enddt={}&forms=S-1".format(
            (datetime.today() - timedelta(days=90)).strftime("%Y-%m-%d"),
            datetime.today().strftime("%Y-%m-%d")
        )
        headers = {"User-Agent": "market-dashboard research@example.com"}
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            hits = data.get("hits", {}).get("hits", [])
            for hit in hits[:10]:
                src = hit.get("_source", {})
                entity = src.get("entity_name", "")
                filed  = src.get("file_date", "")

                # 대형 기업 여부 확인
                for company in MEGA_COMPANIES:
                    if company.lower() in entity.lower():
                        results.append({
                            "company":          company,
                            "est_valuation_bn": 0,   # 별도 파싱
                            "status":           "Filed",
                            "sector":           "Unknown",
                            "source":           "SEC EDGAR",
                            "filed_date":       filed,
                        })
                        logger.info(f"[IPO감지] SEC S-1 제출: {entity} ({filed})")

    except Exception as e:
        logger.warning(f"SEC EDGAR RSS 수집 실패: {e}")

    return results


def fetch_yahoo_finance_ipo_news() -> List[Dict]:
    """Yahoo Finance RSS에서 IPO 관련 뉴스 파싱"""
    results = []
    try:
        rss_urls = [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US",
            "https://finance.yahoo.com/rss/topstories",
        ]

        headers = {"User-Agent": "Mozilla/5.0"}

        for rss_url in rss_urls:
            try:
                resp = requests.get(rss_url, headers=headers, timeout=8)
                if resp.status_code != 200:
                    continue

                root = ET.fromstring(resp.content)
                items = root.findall(".//item")

                for item in items[:30]:
                    title = item.findtext("title", "")
                    desc  = item.findtext("description", "")
                    text  = f"{title} {desc}".lower()

                    # IPO 키워드 포함 여부
                    has_ipo_keyword = any(
                        kw.lower() in text for kw in IPO_KEYWORDS
                    )
                    if not has_ipo_keyword:
                        continue

                    # 기업명 감지
                    for company in MEGA_COMPANIES:
                        if company.lower() in text:
                            # 기업가치 파싱 (예: "$350 billion", "350B")
                            valuation = parse_valuation(text)

                            # 상태 판단
                            status = "Considering"
                            if any(w in text for w in ["filed s-1", "s-1 filing", "filed with sec"]):
                                status = "Filed"
                            elif any(w in text for w in ["priced", "set price", "ipo price"]):
                                status = "Priced"
                            elif any(w in text for w in ["rumor", "consider", "explore"]):
                                status = "Considering"

                            results.append({
                                "company":          company,
                                "est_valuation_bn": valuation,
                                "status":           status,
                                "sector":           "Unknown",
                                "source":           "Yahoo Finance RSS",
                                "title":            title[:80],
                            })
                            logger.info(
                                f"[IPO감지] {company} | "
                                f"상태:{status} | "
                                f"기업가치:${valuation}Bn | "
                                f"제목:{title[:50]}"
                            )

            except Exception as e:
                logger.warning(f"Yahoo RSS 파싱 실패 ({rss_url}): {e}")

    except Exception as e:
        logger.warning(f"Yahoo Finance 뉴스 수집 실패: {e}")

    return results


def parse_valuation(text: str) -> float:
    """텍스트에서 기업가치 파싱 (단위: Bn USD)"""
    try:
        # 패턴 1: "$350 billion" / "$350B"
        patterns = [
            r'\$\s*(\d+(?:\.\d+)?)\s*(?:billion|bn)\b',
            r'(\d+(?:\.\d+)?)\s*(?:billion|bn)\s*(?:valuation|dollar)',
            r'valued?\s+at\s+\$?\s*(\d+(?:\.\d+)?)\s*(?:billion|bn)',
            r'(\d+(?:\.\d+)?)\s*billion[- ]dollar',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = float(match.group(1))
                if 1 < val < 2000:   # 1Bn ~ 2000Bn 범위만 유효
                    return round(val, 1)
    except Exception:
        pass
    return 0.0


def merge_ipo_lists(
    news_items: List[Dict],
    fallback: List[Dict]
) -> List[Dict]:
    """뉴스 파싱 결과와 백업 리스트 병합 (중복 제거, 뉴스 우선)"""
    merged = {}

    # 백업 리스트 먼저 추가
    for item in fallback:
        key = item["company"].lower()
        merged[key] = item.copy()
        merged[key]["source"] = "manual"

    # 뉴스 항목으로 덮어쓰기 (더 최신 정보)
    for item in news_items:
        key = item["company"].lower()
        if key in merged:
            # 기존 항목 업데이트
            if item["status"] in ["Filed", "Priced"]:
                merged[key]["status"] = item["status"]
            if item.get("est_valuation_bn", 0) > 0:
                merged[key]["est_valuation_bn"] = item["est_valuation_bn"]
            merged[key]["source"] = item.get("source", "news")
            merged[key]["last_news"] = item.get("title", "")
        else:
            # 새로운 기업 추가 (기업가치 0이면 제외)
            if item.get("est_valuation_bn", 0) > 0:
                merged[key] = item

    result = list(merged.values())
    # Trading 상태 제외
    result = [r for r in result if r.get("status") != "Trading"]
    return result


def collect_ipo_data() -> Dict[str, Any]:
    try:
        end   = datetime.today()
        start = end - timedelta(days=180)

        # ── 1. 뉴스 자동 수집 ──
        sec_items   = fetch_sec_edgar_ipo_rss()
        yahoo_items = fetch_yahoo_finance_ipo_news()
        all_news    = sec_items + yahoo_items

        # ── 2. 백업 리스트와 병합 ──
        pipeline = merge_ipo_lists(all_news, MEGA_IPO_FALLBACK)

        # ── 3. 상태별 가중치 적용 파이프라인 집계 ──
        total_pipeline_bn   = sum(
            c["est_valuation_bn"]
            for c in pipeline
            if c["status"] in ["Considering", "Filed", "Priced"]
        )
        # 가중치 적용 유효 파이프라인
        weighted_pipeline_bn = sum(
            c["est_valuation_bn"] * STATUS_WEIGHT.get(c["status"], 0.1)
            for c in pipeline
        )
        estimated_market_impact_bn = weighted_pipeline_bn * 0.20
        korea_gdp_bn               = 1700
        pipeline_vs_korea_gdp      = weighted_pipeline_bn / korea_gdp_bn

        # ── 4. IPO ETF 다운로드 ──
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
            if t in ipo_etf.columns:
                s = ipo_etf[t].dropna()
                if len(s) > 5:
                    lookback = min(63, len(s) - 1)
                    ipo_etf_90d[t] = round(
                        float(s.iloc[-1] / s.iloc[-lookback] - 1) * 100, 2
                    )

        # ── 5. 최근 대형 IPO 성과 ──
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

        # ── 6. VIX ──
        raw_vix = yf.download(
            "^VIX", period="3mo", progress=False, auto_adjust=True
        )

        if isinstance(raw_vix.columns, pd.MultiIndex):
            vix_col = raw_vix["Close"]
        else:
            vix_col = raw_vix["Close"] if "Close" in raw_vix.columns else raw_vix.iloc[:, 0]

        if isinstance(vix_col, pd.DataFrame):
            vix_col = vix_col.squeeze()

        vix_series  = vix_col.dropna()
        vix_current = float(vix_series.iloc[-1])
        vix_avg_3m  = float(vix_series.mean())
        vix_is_low  = vix_current < 15

        # ── 7. IPO 과열 지수 ──
        ipo_heat_index = 0
        if vix_is_low:
            ipo_heat_index += 30
        if ipo_etf_90d.get("IPO", 0) > 20:
            ipo_heat_index += 25
        if weighted_pipeline_bn > 200:
            ipo_heat_index += 30

        active_count      = sum(1 for c in pipeline if c["status"] in ["Filed", "Priced"])
        considering_count = sum(1 for c in pipeline if c["status"] == "Considering")
        news_detected     = len([c for c in pipeline if c.get("source") != "manual"])

        logger.info(
            f"[경고등4] 파이프라인: ${total_pipeline_bn:.0f}Bn (가중: ${weighted_pipeline_bn:.0f}Bn) | "
            f"Filed:{active_count} | 뉴스감지:{news_detected}건 | VIX:{vix_current:.1f}"
        )

        return {
            "timestamp":                   datetime.now().isoformat(),
            "mega_ipo_pipeline":           pipeline,
            "total_pipeline_bn":           round(float(total_pipeline_bn), 0),
            "weighted_pipeline_bn":        round(float(weighted_pipeline_bn), 0),
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
            "news_detected_count":         news_detected,
            "data_freshness":              "auto" if news_detected > 0 else "manual_fallback",
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
        return {
            "raw_score":   50,
            "grade":       "UNKNOWN",
            "grade_color": "#888888",
            "signals":     [],
            "key_metrics": {}
        }

    score   = 0.0
    signals = []

    # ── 가중 파이프라인 기준으로 점수 계산 ──
    weighted = data.get("weighted_pipeline_bn", 0)
    total    = data.get("total_pipeline_bn", 0)

    if weighted > 300:
        score += 35
        signals.append({"level": "RED",    "msg": f"메가 IPO 유효 파이프라인 ${weighted:.0f}Bn — 유동성 블랙홀"})
    elif weighted > 150:
        score += 22
        signals.append({"level": "ORANGE", "msg": f"대규모 IPO 파이프라인 대기 (유효 ${weighted:.0f}Bn)"})
    elif weighted > 80:
        score += 12
        signals.append({"level": "YELLOW", "msg": f"IPO 파이프라인 주목 (유효 ${weighted:.0f}Bn)"})

    # Filed/Priced 건수 (즉각적 위험)
    active = data.get("active_ipo_count", 0)
    if active >= 2:
        score += 25
        signals.append({"level": "RED",    "msg": f"🚨 S-1 제출 대어급 IPO {active}건 — 유동성 흡수 임박"})
    elif active == 1:
        score += 15
        signals.append({"level": "ORANGE", "msg": f"S-1 제출 대어급 IPO {active}건 진행 중"})

    if data.get("vix_is_extreme_low"):
        score += 20
        signals.append({
            "level": "RED",
            "msg":   f"⚠️ VIX {data.get('vix_current', 20):.1f} 극단적 저점 — IPO 흥행 마지막 조건 충족"
        })

    ipo_ret = data.get("ipo_etf_90d_returns", {}).get("IPO", 0)
    if ipo_ret > 30:
        score += 20
        signals.append({"level": "RED",    "msg": f"IPO ETF 90일 +{ipo_ret:.0f}% — 파티의 마지막 신호"})
    elif ipo_ret > 15:
        score += 12
        signals.append({"level": "ORANGE", "msg": f"IPO 시장 과열 (+{ipo_ret:.0f}%)"})

    # 뉴스 자동 감지 건수
    news_count = data.get("news_detected_count", 0)
    if news_count >= 3:
        score += 10
        signals.append({"level": "ORANGE", "msg": f"IPO 관련 뉴스 {news_count}건 자동 감지"})

    # 데이터 신선도 표시
    freshness = data.get("data_freshness", "manual_fallback")
    if freshness == "manual_fallback":
        signals.append({"level": "YELLOW", "msg": "ℹ️ 뉴스 자동 감지 없음 — 수동 백업 리스트 사용 중"})

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
            "IPO 파이프라인 (전체)": f"${total:.0f}Bn",
            "IPO 파이프라인 (유효)": f"${weighted:.0f}Bn",
            "VIX":                  f"{data.get('vix_current', 0):.1f}",
            "IPO ETF 90일":         f"+{ipo_ret:.1f}%",
        }
    }
