# ============================================================
# collector_ipo.py
# IPO 파이프라인 데이터 수집 및 위험 점수 계산 모듈
#
# 수정:
#   Fix8  – 절대금액 → 미국 시총 대비 비율 방식
#   Fix9  – 기산 시점 2026-05-01 이후 액션 기업만 포함
#   Fix10 – 대형 IPO 기준 $50B 이상
#   Fix11 – 가중치 재설계: 루머 0.0 / 검토중 0.1 / 신청완료 0.7 / 가격확정 1.0
#   Fix12 – EDGAR 호출 완전 제거 (클라우드 IP 차단으로 매번 실패)
# ============================================================

import socket
import logging
import re
from datetime import datetime, timezone, date
from typing import Optional

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

# ──────────────────────────────────────────────
# Fallback 데이터
# 출처: Reuters, Bloomberg, CNBC, SEC EDGAR (2026-05 기준)
# 포함 기준: 2026-05-01 이후 액션 + $50B 이상
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

        if status == "상장완료":
            signals.append(f"✅ {company}: 상장 완료 (점수 제외)")
            continue

        if not _is_active(item):
            signals.append(f"⏸ {company}: 2026-05-01 이전 액션 — 제외")
            continue

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

    pipeline_ratio_pct = round(total_valuation_bn / US_MARKET_CAP_BN * 100, 4)

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
    """
    Fix12: EDGAR 호출 완전 제거.
    GitHub Actions Azure IP가 SEC에 의해 차단되며,
    어차피 EDGAR에는 기업가치 데이터가 없어 fallback이 덮어쓰므로
    fallback 데이터만 사용하는 것이 더 정확하고 안정적.
    """
    logger.info("IPO 데이터 수집 시작 (fallback 전용)")
    logger.info("수집 기업 수: %d개", len(MEGA_IPO_FALLBACK))
    result = calculate_ipo_score(MEGA_IPO_FALLBACK)
    return result
