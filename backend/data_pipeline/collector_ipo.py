"""
collector_ipo.py
IPO 파이프라인 데이터 수집 및 위험 점수 계산 모듈

수정: Google News RSS 비활성화 (데이터 오염 방지)
     EDGAR + Fallback 조합만 사용
"""

import socket
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

# feedparser는 Google News RSS 비활성화로 현재 미사용
# (오염된 기업가치/상태 파싱 방지)

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
    "상장완료": 0.0,
}

STATUS_PRIORITY: dict[str, int] = {
    "루머":     1,
    "검토중":   2,
    "신청완료": 3,
    "가격확정": 4,
    "상장완료": 5,
}

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

# ──────────────────────────────────────────────
# Fallback 데이터 (최우선 신뢰 소스)
# 출처: Reuters, Bloomberg, CNBC, Anthropic 공식 (2026-05-28 기준)
# Google News RSS는 오염 위험으로 사용하지 않음
# ──────────────────────────────────────────────
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
    if not raw:
        return None
    raw = raw.replace(",", "").strip()
    m = re.search(r"([\d.]+)\s*[Tt](?:rillion)?", raw)
    if m:
        return float(m.group(1)) * 1000
    m = re.search(r"([\d.]+)\s*[Bb](?:illion)?", raw)
    if m:
        return float(m.group(1))
    return None


def normalize_status(raw: str) -> str:
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
# EDGAR 수집 (신뢰 소스 — S-1 공식 제출만)
# ──────────────────────────────────────────────

def fetch_edgar_rss() -> list[dict]:
    """
    SEC EDGAR에서 S-1 제출 목록을 수집한다.
    공식 제출 데이터만 사용하므로 신뢰도 높음.
    단, 기업가치(valuation_bn)는 EDGAR에 없으므로 None 반환.
    → merge 시 fallback의 valuation_bn 유지됨.
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
                "valuation_bn": None,       # EDGAR에는 기업가치 없음
                "status":       "신청완료",
                "source":       "SEC EDGAR",
                "filed_date":   src.get("display_date_filed"),
                "listed_date":  None,
                "ticker":       None,
            })
        logger.info("EDGAR %d건 수집", len(results))
    except Exception as exc:
        logger.warning("EDGAR 수집 실패: %s", exc)
    return results


# ──────────────────────────────────────────────
# 데이터 병합
# EDGAR → Fallback 순서 (Google News RSS 제거)
# ──────────────────────────────────────────────

def merge_ipo_lists(
    edgar:    list[dict],
    fallback: list[dict],
) -> list[dict]:
    """
    EDGAR → Fallback 순서로 병합한다.
    - 같은 기업은 STATUS_PRIORITY 가 높은 값 채택
    - valuation_bn 은 None 이 아닌 값만 덮어씀
      (EDGAR는 valuation_bn=None 이므로 fallback 값 유지)
    """
    merged: dict[str, dict] = {}

    def _upsert(item: dict) -> None:
        if not isinstance(item, dict):
            logger.warning("merge_ipo_lists: dict 아닌 항목 무시 (%s)", type(item))
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
            # valuation_bn 은 None 이 아닐 때만 업데이트
            if new_val is None:
                merged[company]["valuation_bn"] = existing.get("valuation_bn")

    # EDGAR 먼저 (상태 업데이트용), Fallback 나중 (기업가치 보정용)
    for item in (edgar + fallback):
        _upsert(item)

    return list(merged.values())


# ──────────────────────────────────────────────
# 점수 계산
# ──────────────────────────────────────────────

def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    """
    IPO 파이프라인 리스트를 받아 위험 점수(0-100)를 계산한다.
    """
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

    bonus     = min(filed_count * 5 + priced_count * 3, 20)
    raw_score = min(base_score + bonus, 100)

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
# 메인 수집 함수
# ──────────────────────────────────────────────

def collect_ipo_data() -> dict:
    """
    IPO 데이터를 수집하고 점수를 계산해 반환한다.
    신뢰 소스: EDGAR(공식 S-1 제출) + Fallback(검증된 언론 데이터)
    Google News RSS는 데이터 오염 위험으로 사용하지 않음.
    """
    logger.info("IPO 데이터 수집 시작")

    edgar_data = fetch_edgar_rss()

    # ✅ Google News RSS 완전 비활성화
    # 이유: 기사 제목에서 잘못된 기업가치($3,000B)와
    #       잘못된 상태(가격확정, 상장완료)를 파싱하여 데이터 오염 발생
    news_data: list[dict] = []
    logger.info("Google News RSS 비활성화 — fallback 데이터 사용")

    merged = merge_ipo_lists(edgar_data, MEGA_IPO_FALLBACK)
    logger.info("병합 후 총 %d개 기업", len(merged))

    result = calculate_ipo_score(merged)
    logger.info(
        "IPO 점수: %d점 (%s) | 활성 파이프라인: $%.0fB",
        result["score"], result["grade"], result["total_valuation_bn"],
    )
    return result
