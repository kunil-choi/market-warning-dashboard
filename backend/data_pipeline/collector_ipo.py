"""
collector_ipo.py
IPO 파이프라인 데이터 수집 및 위험 점수 계산 모듈
"""

import socket
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import feedparser
import requests

# feedparser 전역 타임아웃 설정 (hang 방지)
socket.setdefaulttimeout(15)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수 정의
# ──────────────────────────────────────────────

STATUS_WEIGHT: dict[str, float] = {
    "루머":     0.1,
    "검토중":   0.3,
    "신청완료": 1.0,
    "가격확정": 1.0,
    "상장완료": 0.0,  # 상장 완료 기업은 점수 계산 제외
}

STATUS_PRIORITY: dict[str, int] = {
    "루머":     1,
    "검토중":   2,
    "신청완료": 3,
    "가격확정": 4,
    "상장완료": 5,
}

# EDGAR 별칭 매핑 (SEC 등록명 → 표준명)
EDGAR_ALIAS: dict[str, str] = {
    "Space Exploration Technologies Corp": "SpaceX",
    "Space Exploration Technologies":      "SpaceX",
    "OpenAI OpCo LLC":                     "OpenAI",
    "OpenAI Inc":                          "OpenAI",
    "Anthropic PBC":                       "Anthropic",
    "Anthropic, PBC":                      "Anthropic",
    "Databricks Inc":                      "Databricks",
    "Stripe Inc":                          "Stripe",
    "Cerebras Systems Inc":                "Cerebras",
    "Revolut Ltd":                         "Revolut",
    "Discord Inc":                         "Discord",
}

MEGA_COMPANIES: set[str] = {
    "SpaceX", "OpenAI", "Anthropic",
    "Databricks", "Stripe", "Cerebras",
    "Revolut", "Discord",
}

# fallback 데이터 (EDGAR / News 수집 실패 시 사용)
# 출처: aifundingtracker.com, Reuters, Bloomberg, CNBC (2026-05-28 기준)
MEGA_IPO_FALLBACK: list[dict] = [
    {
        "company":      "SpaceX",
        "valuation_bn": 1800,
        "status":       "신청완료",
        "source":       "Reuters/Bloomberg 2026-05-15",
        "filed_date":   "2026-04-01",
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "OpenAI",
        "valuation_bn": 852,
        "status":       "검토중",
        "source":       "Bloomberg 2026-03-31",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        # ✅ 수정: $900B → $965B (Anthropic Series H 완료, Anthropic 공식 / Reuters 2026-05-28)
        "company":      "Anthropic",
        "valuation_bn": 965,
        "status":       "검토중",
        "source":       "Anthropic 공식 / Reuters 2026-05-28",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "Databricks",
        "valuation_bn": 134,
        "status":       "검토중",
        "source":       "CNBC 2026-02-09",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "Stripe",
        "valuation_bn": 159,
        "status":       "검토중",
        "source":       "Reuters 2026-02-24",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        # ✅ 수정: 신청완료 → 상장완료 (Nasdaq CBRS 2026-05-14 상장, 첫날 +68%)
        "company":      "Cerebras",
        "valuation_bn": 95,
        "status":       "상장완료",
        "source":       "CNBC / Reuters 2026-05-14",
        "filed_date":   "2026-04-17",
        "listed_date":  "2026-05-14",
        "ticker":       "CBRS",
    },
    {
        "company":      "Revolut",
        "valuation_bn": 75,
        "status":       "신청완료",
        "source":       "Bloomberg 2026",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "Discord",
        "valuation_bn": 15,
        "status":       "신청완료",
        "source":       "Bloomberg 2026",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
]

HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; MarketDashboard/1.0; "
        "+https://github.com/your-repo)"
    )
}


# ──────────────────────────────────────────────
# 유틸리티 함수
# ──────────────────────────────────────────────

def parse_valuation(raw: str) -> Optional[float]:
    """
    문자열에서 기업가치(십억 달러 단위)를 추출한다.
    예) '$1.8T' → 1800.0,  '$965B' → 965.0,  '$134 billion' → 134.0
    """
    if not raw:
        return None
    raw = raw.replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*[Tt](?:rillion)?", raw)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r"([\d.]+)\s*[Bb](?:illion)?", raw)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)", raw)
    if m:
        return float(m.group(1))
    return None


def normalize_status(raw: str) -> str:
    """
    다양한 영문/국문 상태 표현을 표준 한국어 상태로 변환한다.
    """
    if not raw:
        return "루머"
    r = raw.lower().strip()
    if any(k in r for k in ("trading", "listed", "상장완료", "ipo complete")):
        return "상장완료"
    if any(k in r for k in ("priced", "pricing", "가격확정")):
        return "가격확정"
    if any(k in r for k in ("filed", "s-1", "신청완료", "confidential")):
        return "신청완료"
    if any(k in r for k in ("considering", "검토", "talks", "in discussion", "preparing")):
        return "검토중"
    return "루머"


# ──────────────────────────────────────────────
# 데이터 수집 함수
# ──────────────────────────────────────────────

def fetch_edgar_rss() -> list[dict]:
    """
    SEC EDGAR에서 최근 S-1 / S-1A 제출 목록을 수집한다.
    """
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22S-1%22&dateRange=custom&startdt=2026-01-01"
        "&forms=S-1,S-1/A&hits.hits._source=period_of_report,"
        "display_date_filed,entity_name"
    )
    results: list[dict] = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", {}).get("hits", [])
        for hit in hits:
            src     = hit.get("_source", {})
            entity  = src.get("entity_name", "")
            company = EDGAR_ALIAS.get(entity, entity)
            if company not in MEGA_COMPANIES:
                continue
            results.append({
                "company":      company,
                "valuation_bn": None,
                "status":       "신청완료",
                "source":       "SEC EDGAR",
                "filed_date":   src.get("display_date_filed"),
                "listed_date":  None,
                "ticker":       None,
            })
    except Exception as exc:
        logger.warning("EDGAR 수집 실패: %s", exc)
    return results


def fetch_google_news_rss(company: str) -> list[dict]:
    """
    Google News RSS로 특정 기업의 IPO 관련 기사를 수집한다.
    """
    query = f"{company} IPO valuation 2026"
    url = (
        "https://news.google.com/rss/search"
        f"?q={requests.utils.quote(query)}&hl=en-US&gl=US&ceid=US:en"
    )
    results: list[dict] = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            title      = entry.get("title", "") + " " + entry.get("summary", "")
            valuation  = parse_valuation(title)
            status_raw = ""
            if any(k in title.lower() for k in ("filed", "s-1", "confidential")):
                status_raw = "filed"
            elif any(k in title.lower() for k in ("trading", "listed", "debut")):
                status_raw = "trading"
            elif any(k in title.lower() for k in ("pricing", "priced")):
                status_raw = "priced"
            elif any(k in title.lower() for k in ("ipo", "listing", "going public")):
                status_raw = "considering"
            if not status_raw:
                continue
            results.append({
                "company":      company,
                "valuation_bn": valuation,
                "status":       normalize_status(status_raw),
                "source":       "Google News RSS",
                "filed_date":   None,
                "listed_date":  None,
                "ticker":       None,
            })
    except Exception as exc:
        logger.warning("%s Google News RSS 수집 실패: %s", company, exc)
    return results


# ──────────────────────────────────────────────
# 데이터 병합
# ──────────────────────────────────────────────

def merge_ipo_lists(
    edgar:    list[dict],
    news:     list[dict],
    fallback: list[dict],
) -> list[dict]:
    """
    EDGAR → News → Fallback 순서로 병합한다.
    - 같은 기업은 STATUS_PRIORITY 가 높은 값 채택
    - valuation_bn 은 None 이 아닌 값만 덮어씀
    """
    merged: dict[str, dict] = {}

    def _upsert(item: dict) -> None:
        if not isinstance(item, dict):
            logger.warning("merge_ipo_lists: dict 가 아닌 항목 무시 (%s)", type(item))
            return
        company = item.get("company", "")
        if not company:
            return
        existing = merged.get(company)
        if existing is None:
            merged[company] = dict(item)
            return
        new_pri = STATUS_PRIORITY.get(item.get("status", "루머"), 0)
        cur_pri = STATUS_PRIORITY.get(existing.get("status", "루머"), 0)
        if new_pri >= cur_pri:
            new_val = item.get("valuation_bn")
            merged[company] = dict(item)
            # ✅ valuation_bn 은 None 이 아닐 때만 업데이트
            if new_val is None:
                merged[company]["valuation_bn"] = existing.get("valuation_bn")

    for item in (edgar + news + fallback):
        _upsert(item)

    return list(merged.values())


# ──────────────────────────────────────────────
# 점수 계산
# ──────────────────────────────────────────────

def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    """
    IPO 파이프라인 리스트를 받아 위험 점수(0-100)를 계산한다.
    scoring_engine 이 이 함수를 직접 호출하지 않도록 주의.
    collect_ipo_data() 를 통해 간접 호출할 것.
    """
    # ── 타입 방어
    if not isinstance(ipo_list, list):
        logger.error(
            "calculate_ipo_score: list 를 받아야 하지만 %s 수신", type(ipo_list)
        )
        ipo_list = []

    total_valuation_bn: float = 0.0
    filed_count:  int = 0
    priced_count: int = 0
    signals:      list[str] = []
    alerts:       list[str] = []

    for item in ipo_list:
        if not isinstance(item, dict):
            logger.warning("calculate_ipo_score: dict 아닌 항목 무시 (%s)", type(item))
            continue

        company = item.get("company", "알 수 없음")
        status  = item.get("status",  "루머")
        val_bn  = item.get("valuation_bn") or 0.0
        weight  = STATUS_WEIGHT.get(status, 0.0)

        # 상장 완료 기업은 파이프라인 합산 제외
        if status == "상장완료":
            signals.append(f"✅ {company}: 상장 완료 (점수 제외)")
            continue

        weighted_val = val_bn * weight
        total_valuation_bn += weighted_val

        if status == "신청완료":
            filed_count += 1
            signals.append(f"📋 {company}: S-1 제출 완료 (${val_bn:.0f}B)")
        elif status == "가격확정":
            priced_count += 1
            signals.append(f"💰 {company}: 가격 확정 (${val_bn:.0f}B)")
        elif status == "검토중":
            signals.append(f"🔍 {company}: IPO 검토 중 (${val_bn:.0f}B)")
        else:
            signals.append(f"💬 {company}: 루머 단계 (${val_bn:.0f}B)")

    # ── 기본 점수 (파이프라인 총 기업가치 기준)
    if total_valuation_bn >= 3_000:
        base_score = 80
        alerts.append(f"🚨 활성 파이프라인 ${total_valuation_bn:.0f}B — 역대 최대")
    elif total_valuation_bn >= 2_000:
        base_score = 65
        alerts.append(f"⚠️ 활성 파이프라인 ${total_valuation_bn:.0f}B — 매우 높음")
    elif total_valuation_bn >= 1_000:
        base_score = 45
        alerts.append(f"📢 활성 파이프라인 ${total_valuation_bn:.0f}B — 주의")
    elif total_valuation_bn >= 500:
        base_score = 25
    else:
        base_score = 10

    # ── 보너스: S-1 제출 / 가격확정 건수
    bonus      = min(filed_count * 5 + priced_count * 3, 20)
    raw_score  = min(base_score + bonus, 100)

    # ── 등급
    if raw_score >= 80:
        grade, color = "위험", "red"
    elif raw_score >= 60:
        grade, color = "경고", "orange"
    elif raw_score >= 40:
        grade, color = "주의", "yellow"
    else:
        grade, color = "정상", "green"

    return {
        "score":               raw_score,
        "grade":               grade,
        "color":               color,
        "total_valuation_bn":  round(total_valuation_bn, 1),
        "filed_count":         filed_count,
        "priced_count":        priced_count,
        "signals":             signals,
        "alerts":              alerts,
        "ipo_list":            ipo_list,
        "timestamp":           datetime.now(timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────
# 메인 수집 함수 (scoring_engine 에서 호출)
# ──────────────────────────────────────────────

def collect_ipo_data() -> dict:
    """
    전체 IPO 데이터를 수집하고 점수를 계산해 반환한다.
    scoring_engine.py 는 반환값의 'score' 키를 직접 사용하면 된다.
    """
    logger.info("IPO 데이터 수집 시작")

    edgar_data: list[dict] = fetch_edgar_rss()
    logger.info("EDGAR %d건 수집", len(edgar_data))

    news_data: list[dict] = []
    for company in MEGA_COMPANIES:
        news_data.extend(fetch_google_news_rss(company))
    logger.info("Google News %d건 수집", len(news_data))

    merged = merge_ipo_lists(edgar_data, news_data, MEGA_IPO_FALLBACK)
    logger.info("병합 후 총 %d개 기업", len(merged))

    result = calculate_ipo_score(merged)
    logger.info(
        "IPO 점수: %d점 (%s) | 활성 파이프라인: $%.0fB",
        result["score"], result["grade"], result["total_valuation_bn"],
    )
    return result
