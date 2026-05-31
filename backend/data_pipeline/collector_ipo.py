# ============================================================
# collector_ipo.py  –  IPO 데이터 수집 및 점수 산출
# 수정사항:
#   Bug Fix 1 – Anthropic 기업가치 $900B 반영 (Bloomberg 2026-05-12)
#   Bug Fix 2 – Stripe 기업가치 $159B 유지 확인 (Reuters 2026-02-24)
#   Bug Fix 3 – OpenAI $852B 유지 확인 (OpenAI 공식 2026-03-31)
#   + EDGAR alias 매칭 로직 (기존 유지)
#   + Korean 상태 레이블 (기존 유지)
# ============================================================

import feedparser
import requests
import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── 상태별 가중치 (Korean 키) ──────────────────────────────
STATUS_WEIGHT = {
    "루머":       0.1,
    "검토중":     0.3,
    "신청완료":   1.0,
    "공모가확정": 1.0,
    "거래중":     0.0,
}

# ── 영문 → 한글 상태 변환 맵 ──────────────────────────────
STATUS_KR_MAP = {
    "rumored":    "루머",
    "rumour":     "루머",
    "considering":"검토중",
    "filed":      "신청완료",
    "priced":     "공모가확정",
    "trading":    "거래중",
    "listed":     "거래중",
}

# ── EDGAR 회사명 별칭 매핑 ────────────────────────────────
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

# ── 모니터링 대상 메가 IPO 기업 목록 ─────────────────────
MEGA_COMPANIES = [
    "SpaceX", "OpenAI", "Anthropic", "Stripe",
    "Databricks", "ByteDance", "Discord", "Canva",
    "Cerebras", "Revolut", "Anduril",
]

# ── Fallback 데이터 (외부 API 장애 시 사용) ──────────────
# 출처:
#   SpaceX   – Reuters 2026-05-15, CNBC 2026-05-20 → $1,750B, 신청완료
#   OpenAI   – OpenAI 공식 발표 2026-03-31 → $852B, 검토중
#   Anthropic– Bloomberg 2026-05-12 → $900B, 검토중  ← Bug Fix 1
#   Stripe   – Reuters/Bloomberg 2026-02-24 → $159B, 검토중
#   Databricks–Databricks 공식 2026-02-09 → $134B, 검토중
MEGA_IPO_FALLBACK = [
    {
        "company":      "SpaceX",
        "valuation_bn": 1750,
        "status":       "신청완료",
        "source":       "Reuters 2026-05-15",
        "filed_date":   "2026-04-01",
    },
    {
        "company":      "OpenAI",
        "valuation_bn": 852,
        "status":       "검토중",
        "source":       "OpenAI 공식 2026-03-31",
        "filed_date":   None,
    },
    {
        "company":      "Anthropic",
        "valuation_bn": 900,          # ← Bug Fix 1: 851 → 900
        "status":       "검토중",
        "source":       "Bloomberg 2026-05-12",
        "filed_date":   None,
    },
    {
        "company":      "Stripe",
        "valuation_bn": 159,          # ← 확인: $159B 유지 (Reuters 2026-02-24)
        "status":       "검토중",
        "source":       "Reuters 2026-02-24",
        "filed_date":   None,
    },
    {
        "company":      "Databricks",
        "valuation_bn": 134,
        "status":       "검토중",
        "source":       "Databricks 공식 2026-02-09",
        "filed_date":   None,
    },
    {
        "company":      "Cerebras",
        "valuation_bn": 49,
        "status":       "신청완료",
        "source":       "CNBC 2026-05-11",
        "filed_date":   "2026-04-17",
    },
    {
        "company":      "Discord",
        "valuation_bn": 15,
        "status":       "신청완료",
        "source":       "업계 보도 2026",
        "filed_date":   None,
    },
    {
        "company":      "Revolut",
        "valuation_bn": 75,
        "status":       "신청완료",
        "source":       "업계 보도 2026",
        "filed_date":   None,
    },
]


# ════════════════════════════════════════════════════════════
# 유틸리티 함수
# ════════════════════════════════════════════════════════════

def parse_valuation(text: str) -> float | None:
    """
    텍스트에서 기업가치(십억 달러 단위)를 추출.
    우선순위: 조(trillion) → 십억(billion) → 현실적 범위 검증
    """
    if not text:
        return None

    text_lower = text.lower()

    # 1순위: trillion 패턴 (예: $1.75 trillion, 2T)
    t_match = re.search(
        r'\$?\s*([\d,]+(?:\.\d+)?)\s*(?:trillion|t\b)', text_lower
    )
    if t_match:
        val = float(t_match.group(1).replace(',', '')) * 1000  # → 십억 단위
        if 100 <= val <= 10_000:  # 현실적 범위: $100B ~ $10T
            return val

    # 2순위: billion 패턴 (예: $852 billion, 159B)
    b_match = re.search(
        r'\$?\s*([\d,]+(?:\.\d+)?)\s*(?:billion|b\b)', text_lower
    )
    if b_match:
        val = float(b_match.group(1).replace(',', ''))
        if 1 <= val <= 9_999:  # 현실적 범위: $1B ~ $9.999T
            return val

    return None


def normalize_status(raw_status: str) -> str:
    """영문 상태값을 한글로 변환. 이미 한글이면 그대로 반환."""
    if not raw_status:
        return "루머"
    s = raw_status.strip().lower()
    return STATUS_KR_MAP.get(s, raw_status)  # 매핑 없으면 원본 반환


# ════════════════════════════════════════════════════════════
# SEC EDGAR RSS 수집
# ════════════════════════════════════════════════════════════

def fetch_sec_edgar_ipo_rss() -> list[dict]:
    """
    SEC EDGAR RSS에서 S-1 신규 제출 파일을 수집.
    회사명 매칭: exact → alias 2단계 처리.
    """
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=S-1&dateb=&owner=include&count=40&search_text=&action=getcompany"
    headers = {"User-Agent": "IPO-Monitor/1.0 contact@example.com"}

    results = []
    try:
        feed = feedparser.parse(
            "https://www.sec.gov/cgi-bin/browse-edgar"
            "?action=getcurrent&type=S-1&dateb=&owner=include&count=40&output=atom",
            request_headers=headers,
        )

        for entry in feed.entries:
            company_raw = entry.get("title", "")
            company_lower = company_raw.lower()
            matched_company = None

            # 1순위: MEGA_COMPANIES 직접 매칭
            for mega in MEGA_COMPANIES:
                if mega.lower() in company_lower:
                    matched_company = mega
                    break

            # 2순위: EDGAR_ALIAS 별칭 매칭 (SpaceX = "Space Exploration Technologies" 등)
            if not matched_company:
                for alias, canonical in EDGAR_ALIAS.items():
                    if alias in company_lower:
                        matched_company = canonical
                        break

            if not matched_company:
                continue

            filed_date = entry.get("updated", "")[:10]
            results.append({
                "company":      matched_company,
                "valuation_bn": None,   # EDGAR에는 기업가치 없음 → fallback 병합 시 채워짐
                "status":       "신청완료",
                "source":       "SEC EDGAR",
                "filed_date":   filed_date,
            })
            logger.info(f"[EDGAR] 매칭: {company_raw} → {matched_company} ({filed_date})")

    except Exception as e:
        logger.warning(f"[EDGAR] RSS 수집 실패: {e}")

    return results


# ════════════════════════════════════════════════════════════
# Google News RSS 수집
# ════════════════════════════════════════════════════════════

def fetch_google_news_ipo_rss() -> list[dict]:
    """
    Google News RSS에서 IPO 관련 기사를 수집.
    403/빈 응답 시 빈 리스트 반환 (fallback으로 처리).
    """
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
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        try:
            feed = feedparser.parse(url, request_headers=headers)
            if not feed.entries:
                logger.warning(f"[GoogleNews] 빈 응답: {query}")
                continue

            for entry in feed.entries:
                title = entry.get("title", "")
                title_lower = title.lower()
                matched_company = None

                # 회사명 매칭
                for mega in MEGA_COMPANIES:
                    if mega.lower() in title_lower:
                        matched_company = mega
                        break
                if not matched_company:
                    for alias, canonical in EDGAR_ALIAS.items():
                        if alias in title_lower:
                            matched_company = canonical
                            break
                if not matched_company:
                    continue

                # 상태 추론 (키워드 기반)
                if any(k in title_lower for k in ["filed", "s-1", "prospectus", "신청"]):
                    status = "신청완료"
                elif any(k in title_lower for k in ["priced", "pricing", "공모가"]):
                    status = "공모가확정"
                elif any(k in title_lower for k in ["trading", "listed", "debut", "상장"]):
                    status = "거래중"
                elif any(k in title_lower for k in ["considering", "preparing", "plan", "검토"]):
                    status = "검토중"
                else:
                    status = "루머"

                valuation = parse_valuation(title)

                results.append({
                    "company":      matched_company,
                    "valuation_bn": valuation,
                    "status":       status,
                    "source":       "Google News",
                    "filed_date":   entry.get("published", "")[:10],
                })

        except Exception as e:
            logger.warning(f"[GoogleNews] 수집 실패 ({query}): {e}")

    return results


# ════════════════════════════════════════════════════════════
# 데이터 병합
# ════════════════════════════════════════════════════════════

def merge_ipo_lists(*lists) -> list[dict]:
    """
    여러 소스의 IPO 데이터를 병합.
    - 동일 기업: 상태 우선순위 높은 것 유지 (신청완료 > 공모가확정 > 검토중 > 루머)
    - 거래중 항목은 점수 산출에서 제외
    - 기업가치: None이면 이전 소스 값 유지
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
        for item in ipo_list:
            company = item["company"]
            # 영문 상태가 섞여 들어올 경우 정규화
            item["status"] = normalize_status(item["status"])

            if company not in merged:
                merged[company] = item.copy()
            else:
                existing = merged[company]
                new_priority = STATUS_PRIORITY.get(item["status"], 0)
                old_priority = STATUS_PRIORITY.get(existing["status"], 0)

                # 더 높은 우선순위 상태로 업데이트
                if new_priority > old_priority:
                    existing["status"]     = item["status"]
                    existing["filed_date"] = item.get("filed_date") or existing.get("filed_date")
                    existing["source"]     = item["source"]

                # 기업가치: 기존이 None이면 새 값으로 채움
                if existing["valuation_bn"] is None and item.get("valuation_bn"):
                    existing["valuation_bn"] = item["valuation_bn"]

    # 거래중 제외
    return [v for v in merged.values() if v["status"] != "거래중"]


# ════════════════════════════════════════════════════════════
# IPO 점수 산출
# ════════════════════════════════════════════════════════════

def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    """
    IPO 파이프라인 기반 위험 점수 산출 (0~100).

    점수 구성:
      - 총 가중 파이프라인 규모 (최대 50점)
      - 신청완료 건수 보너스 (건당 8점)
      - 공모가확정 건수 보너스 (건당 5점)
    """
    total_weighted_bn = 0.0
    filed_count       = 0
    priced_count      = 0
    signals           = []

    for item in ipo_list:
        company      = item["company"]
        valuation_bn = item.get("valuation_bn") or 0
        status       = item["status"]
        weight       = STATUS_WEIGHT.get(status, 0.1)
        weighted_bn  = valuation_bn * weight

        total_weighted_bn += weighted_bn

        if status == "신청완료":
            filed_count += 1
        elif status == "공모가확정":
            priced_count += 1

        signals.append(
            f"{company} {valuation_bn:,.0f}B [{status}] "
            f"가중={weighted_bn:,.0f}B"
        )

    # 점수 계산
    # 가중 파이프라인: $1,500B 초과 시 최대 50점
    pipeline_score = min(50, (total_weighted_bn / 1_500) * 50)
    filed_score    = min(24, filed_count  * 8)   # 최대 3건 × 8점
    priced_score   = min(15, priced_count * 5)   # 최대 3건 × 5점
    raw_score      = pipeline_score + filed_score + priced_score
    final_score    = min(100, round(raw_score, 1))

    # 등급 판정
    if final_score >= 70:
        grade, color = "RED",    "#e74c3c"
    elif final_score >= 40:
        grade, color = "YELLOW", "#f39c12"
    else:
        grade, color = "GREEN",  "#27ae60"

    # 경고 메시지 생성
    alert_messages = []
    if total_weighted_bn >= 1_500:
        alert_messages.append(
            f"🔴 대어급 IPO 파이프라인 {total_weighted_bn:,.0f}B — "
            f"임계값 1,500B 초과, 유동성 흡수 위험"
        )
    if filed_count >= 1:
        alert_messages.append(
            f"⚠️ S-1 신청완료 {filed_count}건 — "
            f"공모 일정 확정 임박"
        )
    if priced_count >= 1:
        alert_messages.append(
            f"⚠️ 공모가 확정 {priced_count}건 — "
            f"청약 자금 이탈 진행 중"
        )

    return {
        "score":              final_score,
        "grade":              grade,
        "color":              color,
        "total_weighted_bn":  round(total_weighted_bn, 1),
        "filed_count":        filed_count,
        "priced_count":       priced_count,
        "signals":            signals,
        "alert_messages":     alert_messages,
        "ipo_list":           ipo_list,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }


# ════════════════════════════════════════════════════════════
# 메인 진입점
# ════════════════════════════════════════════════════════════

def collect_ipo_data() -> dict:
    """
    전체 IPO 데이터 수집 → 병합 → 점수 산출.
    외부 API 실패 시 MEGA_IPO_FALLBACK으로 안전하게 폴백.
    """
    logger.info("[IPO] 데이터 수집 시작")

    # 1단계: 외부 소스 수집
    edgar_data  = fetch_sec_edgar_ipo_rss()
    news_data   = fetch_google_news_ipo_rss()

    # 2단계: fallback과 병합 (외부 데이터 우선, fallback은 보완)
    merged = merge_ipo_lists(
        MEGA_IPO_FALLBACK,   # 기준값 (가장 먼저)
        edgar_data,          # EDGAR 덮어씀
        news_data,           # 뉴스 덮어씀
    )

    if not merged:
        logger.warning("[IPO] 모든 소스 실패 → fallback 단독 사용")
        merged = [item.copy() for item in MEGA_IPO_FALLBACK
                  if item["status"] != "거래중"]

    logger.info(f"[IPO] 최종 {len(merged)}개 기업 병합 완료")

    # 3단계: 점수 산출
    result = calculate_ipo_score(merged)
    logger.info(
        f"[IPO] 점수={result['score']} "
        f"등급={result['grade']} "
        f"가중파이프라인={result['total_weighted_bn']}B"
    )
    return result
