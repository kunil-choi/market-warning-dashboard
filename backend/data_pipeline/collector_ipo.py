# ============================================================
# collector_ipo.py
# IPO 파이프라인 데이터 수집 및 위험 점수 계산 모듈
#
# 수정:
#   Fix8  – 절대금액 → 미국 시총 대비 비율 방식
#   Fix9  – 기산 시점 2026-05-01 이후 액션 기업만 포함
#   Fix10 – 대형 IPO 기준 $50B 이상
#   Fix11 – 가중치 재설계: 루머 0.0 / 검토중 0.1 / 신청완료 0.7 / 가격확정 1.0
#   Fix12 – EDGAR 403 로그 레벨 WARNING → INFO
# ============================================================

import socket
import logging
import re
from datetime import datetime, timezone, date
from typing import Optional

import requests

socket.setdefaulttimeout(15)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수 정의
# ──────────────────────────────────────────────

US_MARKET_CAP_BN: float = 69_000.0
LARGE_IPO_THRESHOLD_BN: float = 50.0
ACTIVE_FROM: date = date(2026, 5, 1)

STATUS_WEIGHT: dict[str, float] = {
    "루머":     0.0,
    "검토중":   0.1,
    "신청완료": 0.7,
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
# Fallback 데이터
# ──────────────────────────────────────────────
MEGA_IPO_FALLBACK: list[dict] = [
    {
        "company":      "SpaceX",
        "valuation_bn": 1800,
        "status":       "가격확정",
        "active_date":  "2026-05-20",
        "source":       "SEC EDGAR S-1 공개 2026-05-20 / 상장 예정 2026-06-12",
        "filed_date":   "2026-05-20",
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "OpenAI",
        "valuation_bn": 852,
        "status":       "신청완료",
        "active_date":  "2026-05-20",
        "source":       "CNBC / NYT 2026-05-20 비공개 S-1 제출",
        "filed_date":   "2026-05-20",
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "Anthropic",
        "valuation_bn": 965,
        "status":       "검토중",
        "active_date":  "2026-05-28",
        "source":       "Anthropic 공식 / Reuters 2026-05-28",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "Databricks",
        "valuation_bn": 134,
        "status":       "검토중",
        "active_date":  "2026-05-01",
        "source":       "tech-insider.org 2026-05",
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

def _is_active(item: dict) -> bool:
    for key in ("active_date", "filed_date", "listed_date"):
        val = item.get(key)
        if val:
            try:
                d = date.fromisoformat(str(val)[:10])
                if d >= ACTIVE_FROM:
                    return True
            except ValueError:
                continue
    has_any_date = any(item.get(k) for k in ("active_date", "filed_date", "listed_date"))
    return not has_any_date

def _is_large(item: dict) -> bool:
    val = item.get("valuation_bn") or 0.0
    return val >= LARGE_IPO_THRESHOLD_BN

# ──────────────────────────────────────────────
# EDGAR 수집
# ──────────────────────────────────────────────

def fetch_edgar_rss() -> list[dict]:
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        "?q=%22S-1%22"
        "&dateRange=custom"
        "&startdt=2026-05-01"
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
                "active_date":  src.get("display_date_filed"),
                "source":       "SEC EDGAR",
                "filed_date":   src.get("display_date_filed"),
                "listed_date":  None,
                "ticker":       None,
            })
        logger.info("EDGAR %d건 수집", len(results))
    except Exception as exc:
        # Fix12: EDGAR 403 등 수집 실패는 INFO 레벨 (fallback으로 정상 처리됨)
        logger.info("EDGAR 수집 실패 (fallback 사용): %s", exc)
    return results

# ──────────────────────────────────────────────
# 데이터 병합
# ──────────────────────────────────────────────

def merge_ipo_lists(edgar: list[dict], fallback: list[dict]) -> list[dict]:
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
# 점수 계산
# ──────────────────────────────────────────────

def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    if not isinstance(ipo_list, list):
        logger.error("calculate_ipo_score: list 를 받아야 하지만 %s 수신", type(ipo_list))
        ipo_list = []

    total_valuation_bn: float = 0.0
    filed_count:  int = 0
    priced_count: int = 0
    signals:      list[str] = []
    alerts:       list[str] = []

    for item in ipo_list:
        if not isinstance(item, dict):
            continue

        company = item.get("company", "알 수 없음")
        status  = item.get("status", "루머")
        val_bn  = item.get("valuation_bn") or 0.0

        # 상장완료 제외
        if status == "상장완료":
            signals.append(f"✅ {company}: 상장 완료 (점수 제외)")
            continue

        # Fix9: 기산 시점 이전 액션 제외
        if not _is_active(item):
            signals.append(f"⏸ {company}: 2026-05-01 이전 액션 — 제외")
            continue

        # Fix10: $50B 미만 소형 IPO 제외
        if not _is_large(item):
            signals.append(f"⏸ {company}: ${val_bn:.0f}B — $50B 미만 제외")
            continue

        weight       = STATUS_WEIGHT.get(status, 0.0)
        weighted_val = val_bn * weight
        total_valuation_bn += weighted_val

        if status == "가격확정":
            priced_count += 1
            signals.append(f"🚨 {company}: 가격 확정 — 상장 임박 (${val_bn:.0f}B × {weight})")
        elif status == "신청완료":
            filed_count += 1
            signals.append(f"📋 {company}: S-1 제출 완료 (${val_bn:.0f}B × {weight})")
        elif status == "검토중":
            signals.append(f"🔍 {company}: IPO 검토 중 (${val_bn:.0f}B × {weight})")
        else:
            signals.append(f"💬 {company}: 루머 단계 — 점수 제외")

    # Fix8: 시총 대비 비율 계산
    pipeline_ratio_pct = round(total_valuation_bn / US_MARKET_CAP_BN * 100, 4)

    # 비율 기반 기본 점수
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

    # 보너스: 가격확정 × 10점, 신청완료 × 5점 (최대 20점)
    bonus     = min(priced_count * 10 + filed_count * 5, 20)
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
        "score":              raw_score,
        "grade":              grade,
        "color":              color,
        "total_valuation_bn": round(total_valuation_bn, 1),
        "pipeline_ratio_pct": pipeline_ratio_pct,
        "us_market_cap_bn":   US_MARKET_CAP_BN,
        "filed_count":        filed_count,
        "priced_count":       priced_count,
        "signals":            signals,
        "alerts":             alerts,
        "ipo_list":           ipo_list,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }

# ──────────────────────────────────────────────
# 메인 수집 함수
# ──────────────────────────────────────────────

def collect_ipo_data() -> dict:
    logger.info("IPO 데이터 수집 시작")
    edgar_data = fetch_edgar_rss()
    logger.info("Google News RSS 비활성화 — fallback 데이터 사용")
    merged = merge_ipo_lists(edgar_data, MEGA_IPO_FALLBACK)
    logger.info("병합 후 총 %d개 기업", len(merged))
    result = calculate_ipo_score(merged)
    return result
