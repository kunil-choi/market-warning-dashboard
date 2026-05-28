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

# ──────────────────────────────────────────────
# 1. 상태별 가중치
# ──────────────────────────────────────────────
STATUS_WEIGHT = {
    "Filed":       1.0,
    "Priced":      1.0,
    "Considering": 0.3,
    "Rumored":     0.1,
    "Trading":     0.0,
}

# ──────────────────────────────────────────────
# 2. 백업 리스트 (자동 파싱 실패 시 사용)
#    2026-05-28 기준 최신 기업가치 반영
# ──────────────────────────────────────────────
MEGA_IPO_FALLBACK = [
    {"company": "SpaceX",     "est_valuation_bn": 1750, "status": "Filed",       "sector": "AI/Space"},
    {"company": "OpenAI",     "est_valuation_bn": 852,  "status": "Considering", "sector": "AI"},
    {"company": "Anthropic",  "est_valuation_bn": 851,  "status": "Considering", "sector": "AI"},
    {"company": "Stripe",     "est_valuation_bn": 159,  "status": "Considering", "sector": "Fintech"},
    {"company": "Databricks", "est_valuation_bn": 134,  "status": "Considering", "sector": "AI/Data"},
]

# ──────────────────────────────────────────────
# 3. 자동 감지 대상 키워드 / 기업명
# ──────────────────────────────────────────────
IPO_KEYWORDS = [
    "IPO", "initial public offering", "going public",
    "S-1", "filed with SEC", "public listing",
    "valuation", "billion", "unicorn",
]
MEGA_COMPANIES = [
    "SpaceX", "OpenAI", "Anthropic", "Stripe", "Databricks",
    "Klarna", "Chime", "Plaid", "Discord", "Canva",
    "Shein", "ByteDance", "TikTok", "Figma", "Instacart",
]

# ──────────────────────────────────────────────
# 4. 뉴스 RSS 소스
# ──────────────────────────────────────────────
RSS_URLS = [
    # Google News – IPO 관련 최신 뉴스
    "https://news.google.com/rss/search?q=IPO+S-1+SEC+billion+valuation&hl=en-US&gl=US&ceid=US:en",
    # Google News – 메가 테크 기업 IPO 특화
    "https://news.google.com/rss/search?q=SpaceX+OpenAI+Anthropic+Stripe+IPO+2026&hl=en-US&gl=US&ceid=US:en",
]

# ──────────────────────────────────────────────
# 5. 헬퍼 – 기업가치 파싱
# ──────────────────────────────────────────────
def parse_valuation(text: str) -> float:
    """텍스트에서 기업가치(Bn USD)를 추출합니다."""
    text = text.replace(",", "")
    patterns = [
        r"\$\s*([\d\.]+)\s*trillion",
        r"\$\s*([\d\.]+)\s*T\b",
        r"([\d\.]+)\s*trillion\s*dollar",
        r"\$\s*([\d\.]+)\s*billion",
        r"\$\s*([\d\.]+)\s*B\b",
        r"([\d\.]+)\s*billion\s*dollar",
        r"valued\s+at\s+\$?\s*([\d\.]+)\s*B",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if "trillion" in pat.lower() or pat.endswith(r"T\b"):
                val *= 1000
            if val > 5:      # 5Bn 미만은 메가 IPO 아님
                return round(val, 1)
    return 0.0


# ──────────────────────────────────────────────
# 6. SEC EDGAR RSS – S-1 제출 자동 감지
# ──────────────────────────────────────────────
def fetch_sec_edgar_ipo_rss() -> List[Dict]:
    """SEC EDGAR RSS에서 최근 90일 내 S-1 제출을 감지합니다."""
    results = []
    url = (
        "https://efts.sec.gov/LATEST/search-index?q=%22S-1%22&dateRange=custom"
        f"&startdt={(datetime.today()-timedelta(days=90)).strftime('%Y-%m-%d')}"
        f"&enddt={datetime.today().strftime('%Y-%m-%d')}"
        "&forms=S-1&hits.hits._source=display_names,file_date,entity_name,period_of_report"
    )
    try:
        headers = {"User-Agent": "market-warning-dashboard contact@example.com"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            logger.warning(f"SEC EDGAR 응답 오류: {resp.status_code}")
            return results
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits[:20]:
            src = hit.get("_source", {})
            # display_names 는 리스트로 반환됨
            names = src.get("display_names", [])
            company = names[0] if names else src.get("entity_name", "Unknown")
            file_date = src.get("file_date", "")
            # 메가 기업 여부 확인
            for mega in MEGA_COMPANIES:
                if mega.lower() in company.lower():
                    results.append({
                        "company": mega,
                        "status": "Filed",
                        "sector": "Unknown",
                        "est_valuation_bn": 0.0,
                        "source": "SEC_EDGAR",
                        "file_date": file_date,
                    })
                    break
    except Exception as e:
        logger.warning(f"SEC EDGAR RSS 수집 실패: {e}")
    return results


# ──────────────────────────────────────────────
# 7. Google News RSS – IPO 뉴스 자동 파싱
# ──────────────────────────────────────────────
def fetch_google_news_ipo_rss() -> List[Dict]:
    """Google News RSS에서 IPO 관련 기업명·기업가치를 파싱합니다."""
    results = []
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    for url in RSS_URLS:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"RSS 응답 오류({resp.status_code}): {url}")
                continue
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            for item in items[:30]:
                title = item.findtext("title", "")
                desc  = item.findtext("description", "")
                text  = f"{title} {desc}"
                # IPO 키워드 포함 여부
                if not any(kw.lower() in text.lower() for kw in IPO_KEYWORDS):
                    continue
                # 메가 기업 매칭
                matched_company = None
                for mega in MEGA_COMPANIES:
                    if mega.lower() in text.lower():
                        matched_company = mega
                        break
                if not matched_company:
                    continue
                valuation = parse_valuation(text)
                # 상태 판별
                if any(w in text.lower() for w in ["filed s-1", "s-1 filed", "filed with the sec"]):
                    status = "Filed"
                elif any(w in text.lower() for w in ["rumored", "reportedly considering", "might go public"]):
                    status = "Rumored"
                else:
                    status = "Considering"
                results.append({
                    "company":          matched_company,
                    "status":           status,
                    "sector":           "Unknown",
                    "est_valuation_bn": valuation,
                    "source":           "Google_News",
                })
        except ET.ParseError as e:
            logger.warning(f"RSS XML 파싱 실패: {e}")
        except Exception as e:
            logger.warning(f"Google News RSS 수집 실패: {e}")
    return results


# ──────────────────────────────────────────────
# 8. 리스트 병합 (뉴스 + 백업)
# ──────────────────────────────────────────────
def merge_ipo_lists(
    news_items: List[Dict],
    fallback: List[Dict]
) -> List[Dict]:
    """
    백업 리스트를 기준으로, 뉴스에서 더 최신 정보가 있으면 갱신합니다.
    Trading(이미 상장) 상태는 제외합니다.
    """
    merged = {item["company"]: dict(item) for item in fallback}
    for item in news_items:
        company = item["company"]
        if company in merged:
            # 기업가치가 뉴스에서 파싱됐으면 업데이트
            if item.get("est_valuation_bn", 0) > 0:
                merged[company]["est_valuation_bn"] = item["est_valuation_bn"]
            # Filed 상태는 우선 적용
            if item.get("status") == "Filed":
                merged[company]["status"] = "Filed"
        else:
            if item.get("est_valuation_bn", 0) > 10:   # 10Bn 이상만 추가
                merged[company] = item

    # Trading(상장 완료) 항목 제거
    return [v for v in merged.values() if v.get("status") != "Trading"]


# ──────────────────────────────────────────────
# 9. 메인 수집 함수
# ──────────────────────────────────────────────
def collect_ipo_data() -> Dict[str, Any]:
    try:
        end   = datetime.today()
        start = end - timedelta(days=180)

        # ── 9-1. 자동 IPO 파이프라인 수집 ──
        sec_items  = fetch_sec_edgar_ipo_rss()
        news_items = fetch_google_news_ipo_rss()
        all_news   = sec_items + news_items

        pipeline = merge_ipo_lists(all_news, MEGA_IPO_FALLBACK)
        auto_detected_count = len([i for i in all_news if i.get("company") in
                                   [p["company"] for p in pipeline]])
        logger.info(f"IPO 파이프라인: {len(pipeline)}개 기업 (자동감지 {auto_detected_count}건)")

        # ── 9-2. 가중 파이프라인 계산 ──
        total_pipeline_bn = sum(
            p["est_valuation_bn"] for p in pipeline
        )
        weighted_pipeline_bn = sum(
            p["est_valuation_bn"] * STATUS_WEIGHT.get(p["status"], 0.1)
            for p in pipeline
        )
        estimated_market_impact_bn = weighted_pipeline_bn * 0.20
        korea_gdp_bn               = 1700
        pipeline_vs_korea_gdp      = total_pipeline_bn / korea_gdp_bn

        # ── 9-3. IPO ETF 수익률 ──
        ipo_etf_90d = {}
        try:
            raw_ipo = yf.download(
                ["IPO", "IPOS"],
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                progress=False, auto_adjust=True
            )
            ipo_etf = raw_ipo["Close"] if isinstance(raw_ipo.columns, pd.MultiIndex) else raw_ipo
            ipo_etf = ipo_etf.ffill().dropna(how="all")
            for t in ["IPO", "IPOS"]:
                if t in ipo_etf.columns and len(ipo_etf[t].dropna()) > 5:
                    s        = ipo_etf[t].dropna()
                    lookback = min(63, len(s) - 1)
                    ipo_etf_90d[t] = round(
                        float(s.iloc[-1] / s.iloc[-lookback] - 1) * 100, 2
                    )
        except Exception as e:
            logger.warning(f"IPO ETF 수집 실패: {e}")

        # ── 9-4. 최근 대형 IPO 성과 ──
        recent_large_ipos = {
            "ARM":  "ARM Holdings",
            "RDDT": "Reddit",
            "ALAB": "Astera Labs",
            "KLAR": "Klarna",      # 2025-09 상장
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

        # ── 9-5. VIX ──
        try:
            raw_vix = yf.download("^VIX", period="3mo", progress=False, auto_adjust=True)
            # MultiIndex 또는 단일 컬럼 모두 처리
            if isinstance(raw_vix.columns, pd.MultiIndex):
                vix_col = raw_vix["Close"].squeeze()
            elif "Close" in raw_vix.columns:
                vix_col = raw_vix["Close"].squeeze()
            else:
                vix_col = raw_vix.iloc[:, 0].squeeze()

            # squeeze() 후에도 DataFrame이면 첫 컬럼 선택
            if isinstance(vix_col, pd.DataFrame):
                vix_col = vix_col.iloc[:, 0]

            vix_series   = vix_col.dropna()
            if len(vix_series) == 0:
                raise ValueError("VIX 데이터가 비어 있습니다.")
            vix_current  = float(vix_series.iloc[-1])
            vix_avg_3m   = float(vix_series.mean())
            vix_is_low   = vix_current < 15
        except Exception as e:
            logger.warning(f"VIX 수집 실패: {e}")
            vix_current = 20.0
            vix_avg_3m  = 20.0
            vix_is_low  = False

        # ── 9-6. IPO 히트 인덱스 ──
        ipo_heat_index = 0
        if vix_is_low:
            ipo_heat_index += 30
        if ipo_etf_90d.get("IPO", 0) > 20:
            ipo_heat_index += 25
        if weighted_pipeline_bn > 500:
            ipo_heat_index += 30
        if auto_detected_count >= 2:
            ipo_heat_index += 15

        active_count      = sum(1 for c in pipeline if c["status"] == "Filed")
        considering_count = sum(1 for c in pipeline if c["status"] == "Considering")

        return {
            "timestamp":                  datetime.now().isoformat(),
            "mega_ipo_pipeline":          pipeline,
            "total_pipeline_bn":          round(float(total_pipeline_bn), 0),
            "weighted_pipeline_bn":       round(float(weighted_pipeline_bn), 0),
            "estimated_market_impact_bn": round(float(estimated_market_impact_bn), 0),
            "pipeline_vs_korea_gdp_ratio": round(float(pipeline_vs_korea_gdp), 2),
            "ipo_etf_90d_returns":         ipo_etf_90d,
            "recent_ipo_performance":      ipo_performance,
            "vix_current":                 round(vix_current, 2),
            "vix_avg_3m":                  round(vix_avg_3m, 2),
            "vix_is_extreme_low":          bool(vix_is_low),
            "ipo_heat_index":              min(100, int(ipo_heat_index)),
            "active_ipo_count":            active_count,
            "considering_ipo_count":       considering_count,
            "auto_detected_count":         auto_detected_count,
            "status":                      "ok",
        }

    except Exception as e:
        logger.error(f"[경고등4] 데이터 수집 실패: {e}")
        return {
            "status":    "error",
            "message":   str(e),
            "timestamp": datetime.now().isoformat(),
        }


# ──────────────────────────────────────────────
# 10. 점수 계산
# ──────────────────────────────────────────────
def calculate_ipo_score(data: Dict[str, Any]) -> Dict[str, Any]:
    if data.get("status") == "error":
        return {"raw_score": 50, "grade": "UNKNOWN", "signals": [], "key_metrics": {}}

    score   = 0.0
    signals = []

    # 가중 파이프라인 기준으로 점수 산정 (Filed=1.0, Considering=0.3 반영)
    w_pipeline = data.get("weighted_pipeline_bn", 0)
    t_pipeline = data.get("total_pipeline_bn", 0)

    if w_pipeline > 1500:
        score += 40
        signals.append({"level": "RED",
                         "msg": f"⚠️ 가중 IPO 파이프라인 ${w_pipeline:.0f}Bn — 역사적 유동성 블랙홀"})
    elif w_pipeline > 700:
        score += 35
        signals.append({"level": "RED",
                         "msg": f"메가 IPO 파이프라인 ${w_pipeline:.0f}Bn — 유동성 흡수 경계"})
    elif w_pipeline > 300:
        score += 22
        signals.append({"level": "ORANGE",
                         "msg": f"대규모 IPO 파이프라인 대기 (${w_pipeline:.0f}Bn)"})
    elif w_pipeline > 100:
        score += 12
        signals.append({"level": "YELLOW",
                         "msg": f"IPO 파이프라인 주목 (${w_pipeline:.0f}Bn)"})

    # VIX 저점
    if data.get("vix_is_extreme_low"):
        score += 25
        signals.append({"level": "RED",
                         "msg": f"⚠️ VIX {data.get('vix_current', 20):.1f} 극단적 저점 — IPO 흥행 마지막 조건 충족"})

    # IPO ETF 수익률
    ipo_ret = data.get("ipo_etf_90d_returns", {}).get("IPO", 0)
    if ipo_ret > 30:
        score += 25
        signals.append({"level": "RED",
                         "msg": f"IPO ETF 90일 +{ipo_ret:.0f}% — 파티의 마지막 신호"})
    elif ipo_ret > 15:
        score += 15
        signals.append({"level": "ORANGE",
                         "msg": f"IPO 시장 과열 (+{ipo_ret:.0f}%)"})

    # 실제 S-1 제출 건수
    active = data.get("active_ipo_count", 0)
    if active >= 2:
        score += 15
        signals.append({"level": "RED",
                         "msg": f"대어급 IPO {active}건 S-1 제출 — 스펀지 효과 임박"})
    elif active == 1:
        score += 8
        signals.append({"level": "YELLOW",
                         "msg": "대어급 IPO 1건 S-1 제출 완료 — 청약 일정 주시"})

    # 자동 감지 뉴스 건수 보너스
    auto = data.get("auto_detected_count", 0)
    if auto >= 3:
        score += 5
        signals.append({"level": "YELLOW",
                         "msg": f"IPO 관련 뉴스 자동 감지 {auto}건"})

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
            "총 IPO 파이프라인":  f"${t_pipeline:.0f}Bn",
            "가중 파이프라인":    f"${w_pipeline:.0f}Bn",
            "한국 GDP 대비":      f"{data.get('pipeline_vs_korea_gdp_ratio', 0):.1f}배",
            "VIX":               f"{data.get('vix_current', 0):.1f}",
            "IPO ETF 90일":      f"+{ipo_ret:.1f}%",
            "S-1 제출 건수":     f"{active}건",
        },
    }
