# ============================================================
# collector_ipo.py  –  W4 대어급 IPO
# 수정:
#   Bug2 – feedparser 타임아웃 없음 → socket.setdefaulttimeout
#   Bug8 – merge 시 valuation_bn 우선순위 로직 보완
# ============================================================

import socket
import feedparser
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# feedparser 전역 타임아웃 설정 (Bug2 수정)
socket.setdefaulttimeout(15)

# ── 상태별 가중치 ─────────────────────────────────────────
STATUS_WEIGHT = {
    "루머":       0.1,
    "검토중":     0.3,
    "신청완료":   1.0,
    "공모가확정": 1.0,
    "거래중":     0.0,
}

STATUS_KR_MAP = {
    "rumored":     "루머",
    "rumour":      "루머",
    "considering": "검토중",
    "filed":       "신청완료",
    "priced":      "공모가확정",
    "trading":     "거래중",
    "listed":      "거래중",
}

EDGAR_ALIAS = {
    "space exploration": "SpaceX",
    "spacex":            "SpaceX",
    "openai":            "OpenAI",
    "anthropic":         "Anthropic",
    "stripe":            "Stripe",
    "databricks":        "Databricks",
    "bytedance":         "ByteDance",
    "discord":           "Discord",
    "canva":             "Canva",
    "cerebras":          "Cerebras",
    "revolut":           "Revolut",
    "anduril":           "Anduril",
}

MEGA_COMPANIES = [
    "SpaceX", "OpenAI", "Anthropic", "Stripe",
    "Databricks", "ByteDance", "Discord", "Canva",
    "Cerebras", "Revolut", "Anduril",
]

MEGA_IPO_FALLBACK = [
    {"company": "SpaceX",     "valuation_bn": 1800, "status": "신청완료",
     "source": "Bloomberg 2026-05-29", "filed_date": "2026-05-20"},
    {"company": "OpenAI",     "valuation_bn": 852,  "status": "검토중",
     "source": "OpenAI 공식 2026-03-31", "filed_date": None},
    {"company": "Anthropic",  "valuation_bn": 900,  "status": "검토중",
     "source": "Bloomberg 2026-05-12", "filed_date": None},
    {"company": "Stripe",     "valuation_bn": 159,  "status": "검토중",
     "source": "Reuters 2026-02-24", "filed_date": None},
    {"company": "Databricks", "valuation_bn": 134,  "status": "검토중",
     "source": "Databricks 공식 2026-02-09", "filed_date": None},
    {"company": "Cerebras",   "valuation_bn": 49,   "status": "신청완료",
     "source": "CNBC 2026-05-11", "filed_date": "2026-04-17"},
    {"company": "Discord",    "valuation_bn": 15,   "status": "신청완료",
     "source": "업계 보도 2026", "filed_date": None},
    {"company": "Revolut",    "valuation_bn": 75,   "status": "신청완료",
     "source": "업계 보도 2026", "filed_date": None},
]


# ════════════════════════════════════════════════════════════
# 유틸리티
# ════════════════════════════════════════════════════════════

def parse_valuation(text: str) -> float | None:
    if not text:
        return None
    t = text.lower()
    m = re.search(r'\$?\s*([\d,]+(?:\.\d+)?)\s*(?:trillion|t\b)', t)
    if m:
        val = float(m.group(1).replace(',', '')) * 1000
        if 100 <= val <= 10_000:
            return val
    m = re.search(r'\$?\s*([\d,]+(?:\.\d+)?)\s*(?:billion|b\b)', t)
    if m:
        val = float(m.group(1).replace(',', ''))
        if 1 <= val <= 9_999:
            return val
    return None


def normalize_status(raw: str) -> str:
    if not raw:
        return "루머"
    return STATUS_KR_MAP.get(raw.strip().lower(), raw)


# ════════════════════════════════════════════════════════════
# 데이터 수집
# ════════════════════════════════════════════════════════════

def fetch_sec_edgar_ipo_rss() -> list[dict]:
    """SEC EDGAR S-1 RSS 수집. 타임아웃은 socket 전역 설정으로 처리."""
    headers = {"User-Agent": "IPO-Monitor/1.0 contact@example.com"}
    results = []
    try:
        feed = feedparser.parse(
            "https://www.sec.gov/cgi-bin/browse-edgar"
            "?action=getcurrent&type=S-1&dateb=&owner=include"
            "&count=40&output=atom",
            request_headers=headers,
        )
        if feed.bozo and not feed.entries:
            logger.warning(f"[EDGAR] 피드 파싱 오류: {feed.bozo_exception}")
            return []

        for entry in feed.entries:
            raw   = entry.get("title", "")
            lower = raw.lower()
            matched = None
            for mega in MEGA_COMPANIES:
                if mega.lower() in lower:
                    matched = mega
                    break
            if not matched:
                for alias, canonical in EDGAR_ALIAS.items():
                    if alias in lower:
                        matched = canonical
                        break
            if not matched:
                continue
            results.append({
                "company":      matched,
                "valuation_bn": None,
                "status":       "신청완료",
                "source":       "SEC EDGAR",
                "filed_date":   entry.get("updated", "")[:10],
            })
            logger.info(f"[EDGAR] 매칭: {raw} → {matched}")

    except Exception as e:
        logger.warning(f"[EDGAR] RSS 수집 실패: {e}")
    return results


def fetch_google_news_ipo_rss() -> list[dict]:
    """Google News RSS 수집. 타임아웃은 socket 전역 설정으로 처리."""
    queries = [
        "SpaceX+OpenAI+Anthropic+Stripe+IPO+2026",
        "IPO+S-1+SEC+billion+valuation+2026",
    ]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    results = []
    for query in queries:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={query}&hl=en-US&gl=US&ceid=US:en"
        )
        try:
            feed = feedparser.parse(url, request_headers=headers)
            if not feed.entries:
                logger.warning(f"[GoogleNews] 빈 응답: {query}")
                continue
            for entry in feed.entries:
                title = entry.get("title", "")
                tl    = title.lower()
                matched = None
                for mega in MEGA_COMPANIES:
                    if mega.lower() in tl:
                        matched = mega
                        break
                if not matched:
                    for alias, canonical in EDGAR_ALIAS.items():
                        if alias in tl:
                            matched = canonical
                            break
                if not matched:
                    continue
                if any(k in tl for k in ["filed", "s-1", "prospectus"]):
                    status = "신청완료"
                elif any(k in tl for k in ["priced", "pricing"]):
                    status = "공모가확정"
                elif any(k in tl for k in ["trading", "listed", "debut"]):
                    status = "거래중"
                elif any(k in tl for k in ["considering", "preparing", "plan"]):
                    status = "검토중"
                else:
                    status = "루머"
                results.append({
                    "company":      matched,
                    "valuation_bn": parse_valuation(title),
                    "status":       status,
                    "source":       "Google News",
                    "filed_date":   entry.get("published", "")[:10],
                })
        except Exception as e:
            logger.warning(f"[GoogleNews] 수집 실패 ({query}): {e}")
    return results


# ════════════════════════════════════════════════════════════
# 병합  (Bug8 수정)
# ════════════════════════════════════════════════════════════

def merge_ipo_lists(*lists) -> list[dict]:
    """
    Bug8 수정:
    - valuation_bn 우선순위: fallback > None (외부 데이터가 None이면 fallback 유지)
    - 상태 우선순위는 기존대로 (신청완료 > 검토중 > 루머)
    """
    STATUS_PRIORITY = {
        "신청완료":   4,
        "공모가확정": 3,
        "검토중":     2,
        "루머":       1,
        "거래중":     0,
    }
    merged: dict[str, dict] = {}

    for ipo_list in lists:
        if not isinstance(ipo_list, list):
            continue
        for item in ipo_list:
            if not isinstance(item, dict):
                continue
            company = item.get("company")
            if not company:
                continue
            item = item.copy()
            item["status"] = normalize_status(item.get("status", ""))

            if company not in merged:
                merged[company] = item
            else:
                existing     = merged[company]
                new_priority = STATUS_PRIORITY.get(item["status"], 0)
                old_priority = STATUS_PRIORITY.get(existing["status"], 0)

                if new_priority > old_priority:
                    existing["status"]     = item["status"]
                    existing["filed_date"] = (
                        item.get("filed_date") or existing.get("filed_date")
                    )
                    existing["source"] = item["source"]

                # Bug8 수정: 새 값이 None이 아닐 때만 덮어씀
                # (fallback의 정확한 valuation_bn을 외부 None이 지우지 않도록)
                if item.get("valuation_bn") is not None:
                    existing["valuation_bn"] = item["valuation_bn"]

    return [v for v in merged.values() if v.get("status") != "거래중"]


# ════════════════════════════════════════════════════════════
# 점수 산출
# ════════════════════════════════════════════════════════════

def calculate_ipo_score(ipo_list: list) -> dict:
    if not isinstance(ipo_list, list):
        logger.error(
            f"[IPO] 잘못된 입력 타입: {type(ipo_list).__name__} → 빈 리스트 대체"
        )
        ipo_list = []

    total_weighted_bn = 0.0
    filed_count       = 0
    priced_count      = 0
    signals           = []

    for item in ipo_list:
        if not isinstance(item, dict):
            logger.warning(f"[IPO] dict 아닌 아이템 스킵: {type(item).__name__}")
            continue
        company      = item.get("company", "Unknown")
        valuation_bn = item.get("valuation_bn") or 0
        status       = item.get("status", "루머")
        weight       = STATUS_WEIGHT.get(status, 0.1)
        weighted_bn  = valuation_bn * weight

        total_weighted_bn += weighted_bn

        if status == "신청완료":   filed_count  += 1
        elif status == "공모가확정": priced_count += 1

        signals.append(
            f"{company} {valuation_bn:,.0f}B [{status}] 가중={weighted_bn:,.0f}B"
        )

    pipeline_score = min(50, (total_weighted_bn / 1_500) * 50)
    filed_score    = min(24, filed_count  * 8)
    priced_score   = min(15, priced_count * 5)
    final_score    = min(100, round(pipeline_score + filed_score + priced_score, 1))

    grade = "RED" if final_score >= 70 else "YELLOW" if final_score >= 40 else "GREEN"
    color = {"RED": "#e74c3c", "YELLOW": "#f39c12", "GREEN": "#27ae60"}[grade]

    alert_messages = []
    if total_weighted_bn >= 1_500:
        alert_messages.append(
            f"🔴 IPO 파이프라인 {total_weighted_bn:,.0f}B — 임계값 1,500B 초과"
        )
    if filed_count  >= 1: alert_messages.append(f"⚠️ S-1 신청완료 {filed_count}건")
    if priced_count >= 1: alert_messages.append(f"⚠️ 공모가 확정 {priced_count}건")

    return {
        "score":             final_score,
        "grade":             grade,
        "color":             color,
        "total_weighted_bn": round(total_weighted_bn, 1),
        "filed_count":       filed_count,
        "priced_count":      priced_count,
        "signals":           signals,
        "alert_messages":    alert_messages,
        "ipo_list":          ipo_list,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════
# 메인 진입점
# ════════════════════════════════════════════════════════════

def collect_ipo_data() -> dict:
    logger.info("[IPO] 데이터 수집 시작")

    edgar_data = fetch_sec_edgar_ipo_rss()
    news_data  = fetch_google_news_ipo_rss()

    merged = merge_ipo_lists(
        MEGA_IPO_FALLBACK,
        edgar_data,
        news_data,
    )

    if not merged:
        logger.warning("[IPO] 병합 결과 없음 → fallback 단독 사용")
        merged = [
            item.copy() for item in MEGA_IPO_FALLBACK
            if item.get("status") != "거래중"
        ]

    logger.info(f"[IPO] 최종 {len(merged)}개 기업 병합 완료")

    result = calculate_ipo_score(merged)
    logger.info(
        f"[IPO] 점수={result['score']} "
        f"등급={result['grade']} "
        f"가중파이프라인={result['total_weighted_bn']}B"
    )
    return result
