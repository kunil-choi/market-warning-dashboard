"""
collector_ipo.py
IPO 파이프라인 데이터 수집 및 위험 점수 계산 모듈

수정:
  Fix8 – calculate_ipo_score(): 절대금액 임계치 → 미국 시총 대비 비율 방식으로 전환
          근거: Jay R. Ritter IPO 통계(UF 2026) · Siblis Research 시총 데이터
                < 0.15%  → 정상  (2010~16년 회복기 수준)
                0.15~0.25% → 주의  (2021년 SPAC 붐 수준)
                0.25~0.45% → 경고  (1999~2000년 닷컴버블 수준)
                0.45% 이상 → 위험  (닷컴버블 초과, 전례 없음)
"""

import socket
import logging
import re
from datetime import datetime, timezone
from typing import Optional

import requests

socket.setdefaulttimeout(15)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수 정의
# ──────────────────────────────────────────────

# 미국 전체 주식시장 시가총액 (Siblis Research 2026-01-01 기준, 단위: B$)
US_MARKET_CAP_BN: float = 69_000.0

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
        "+https://github.com/kunil-choi/market-warning-dashboard)"
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
# EDGAR 수집
# ──────────────────────────────────────────────

def fetch_edgar_rss() -> list[dict]:
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22S-1%22"
        "&dateRange=custom"
        "&startdt=2026-01-01"
        "&forms=S-1%2CS-1%2FA"
    )

    headers = {
        "User-Agent": (
            "MarketDashboard/1.0 (contact: dashboard@example.com; "
            "https://github.com/kunil-choi/market-warning-dashboard)"
        ),
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }

    results: list[dict] = []
    try:
        resp = requests.get(url, headers=headers, timeout=15)
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
        logger.info("EDGAR %d건 수집", len(results))
    except Exception as exc:
        logger.warning("EDGAR 수집 실패: %s", exc)
    return results


# ──────────────────────────────────────────────
# 데이터 병합
# ──────────────────────────────────────────────

def merge_ipo_lists(
    edgar:    list[dict],
    fallback: list[dict],
) -> list[dict]:
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
            if new_val is None:
                merged[company]["valuation_bn"] = existing.get("valuation_bn")

    for item in (edgar + fallback):
        _upsert(item)

    return list(merged.values())


# ──────────────────────────────────────────────
# 점수 계산 (Fix8: 시총 대비 비율 방식)
# ──────────────────────────────────────────────

def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    """
    IPO 파이프라인 리스트를 받아 위험 점수(0-100)를 계산한다.

    Fix8: 절대금액 임계치 → 미국 시총 대비 비율 방식으로 전환
    역사적 근거:
      1999 닷컴버블:  IPO $64.8B / 시총 $17.6조 = 0.37%
      2000 버블붕괴:  IPO $64.8B / 시총 $14.2조 = 0.45%
      2021 SPAC 붐:   IPO $119.4B / 시총 $52.3조 = 0.23%
      2026 현재:      가중 $2,523B / 시총 $69조  = 3.66%
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

    # ✅ Fix8: 시총 대비 비율 계산
    pipeline_ratio_pct = round(total_valuation_bn / US_MARKET_CAP_BN * 100, 4)

    # ✅ Fix8: 비율 기반 기본 점수
    # < 0.15%  → 정상  (2010~16년 회복기)
    # 0.15~0.25% → 주의  (2021 SPAC 붐)
    # 0.25~0.45% → 경고  (1999~2000 닷컴버블)
    # 0.45% 이상 → 위험  (닷컴버블 초과, 전례 없음)
    if pipeline_ratio_pct >= 0.45:
        base_score = 75
        alerts.append(
            f"🚨 파이프라인 비율 {pipeline_ratio_pct:.2f}% — "
            f"닷컴버블(0.45%) 초과, 전례 없는 수준"
        )
    elif pipeline_ratio_pct >= 0.25:
        base_score = 50
        alerts.append(
            f"⚠️ 파이프라인 비율 {pipeline_ratio_pct:.2f}% — "
            f"1999~2000년 닷컴버블 수준"
        )
    elif pipeline_ratio_pct >= 0.15:
        base_score = 30
        alerts.append(
            f"📢 파이프라인 비율 {pipeline_ratio_pct:.2f}% — "
            f"2021년 SPAC 붐 수준"
        )
    else:
        base_score = 10

    # 보너스: 신청완료·가격확정 건수 (각 5점, 최대 20점)
    bonus     = min(filed_count * 5 + priced_count * 5, 20)
    raw_score = min(base_score + bonus, 100)

    if raw_score >= 80:
        grade, color = "위험", "red"
    elif raw_score >= 60:
        grade, color = "경고", "orange"
    elif raw_score >= 40:
        grade, color = "주의", "yellow"
    else:
        grade, color = "정상", "green"

    logger.info(
        "IPO 점수: %d점 (%s) | 가중파이프라인: $%.0fB | 시총대비: %.4f%%",
        raw_score, grade, total_valuation_bn, pipeline_ratio_pct,
    )

    return {
        "score":                raw_score,
        "grade":                grade,
        "color":                color,
        "total_valuation_bn":   round(total_valuation_bn, 1),
        "pipeline_ratio_pct":   pipeline_ratio_pct,
        "us_market_cap_bn":     US_MARKET_CAP_BN,
        "filed_count":          filed_count,
        "priced_count":         priced_count,
        "signals":              signals,
        "alerts":               alerts,
        "ipo_list":             ipo_list,
        "timestamp":            datetime.now(timezone.utc).isoformat(),
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
    logger.info("Google News RSS 비활성화 — fallback 데이터 사용")

    merged = merge_ipo_lists(edgar_data, MEGA_IPO_FALLBACK)
    logger.info("병합 후 총 %d개 기업", len(merged))

    result = calculate_ipo_score(merged)
    return result
