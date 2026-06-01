# ============================================================
# collector_ipo.py
# IPO 파이프라인 데이터 수집 및 위험 점수 계산 모듈
#
# Fix8  – 절대금액 → 미국 시총 대비 비율 방식
# Fix9  – 기산 시점 2026-05-01 이후 액션 기업만 포함
# Fix10 – 대형 IPO 기준 $50B 이상
# Fix11 – 가중치 재설계
# Fix12 – EDGAR 호출 제거
# Fix13 – '신청완료' → '제출완료' 용어 통일
# Fix15 – 상장완료 후 경과 기간 기반 누적 위험 가중치
# Fix16 – yfinance 티커 확인으로 상장완료 자동 감지
# Fix17 – GNews + Claude AI로 IPO 상태 변화 자동 탐지
# ============================================================

import os
import json
import socket
import logging
import re
import time
import requests
import yfinance as yf
import anthropic

from datetime import datetime, timezone, date
from typing import Optional

socket.setdefaulttimeout(15)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 상수
# ──────────────────────────────────────────────
US_MARKET_CAP_BN: float       = 69_000.0
LARGE_IPO_THRESHOLD_BN: float = 50.0
ACTIVE_FROM: date              = date(2026, 5, 1)

STATUS_WEIGHT_BASE: dict[str, float] = {
    "루머":     0.0,
    "검토중":   0.1,
    "제출완료": 0.7,
    "신청완료": 0.7,
    "가격확정": 1.0,
}

STATUS_PRIORITY: dict[str, int] = {
    "루머":     1,
    "검토중":   2,
    "제출완료": 3,
    "신청완료": 3,
    "가격확정": 4,
    "상장완료": 5,
}

# GNews API 키 (환경변수, 없으면 뉴스 수집 스킵)
GNEWS_API_KEY: str = os.getenv("GNEWS_API_KEY", "")

# ──────────────────────────────────────────────
# Fallback 기준 데이터 (수동 관리 최소화)
# 뉴스 수집 실패 시 이 데이터를 기준으로 사용
# ──────────────────────────────────────────────
MEGA_IPO_FALLBACK: list[dict] = [
    {
        "company":      "SpaceX",
        "valuation_bn": 1800,
        "status":       "가격확정",
        "active_date":  "2026-05-20",
        "source":       "SEC EDGAR S-1 공개 2026-05-20",
        "filed_date":   "2026-05-20",
        "listed_date":  "2026-06-12",   # 예정 상장일 → 이후 자동 전환
        "ticker":       "SPCX",         # Fix16: 티커 확인용
    },
    {
        "company":      "OpenAI",
        "valuation_bn": 852,
        "status":       "제출완료",
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
        "source":       "Anthropic 공식 / Reuters 2026-05-28 / 10월 상장 목표",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
    {
        "company":      "Databricks",
        "valuation_bn": 134,
        "status":       "검토중",
        "active_date":  "2026-05-01",
        "source":       "tech-insider.org 2026-05 / Q3 S-1 예정",
        "filed_date":   None,
        "listed_date":  None,
        "ticker":       None,
    },
]

# ──────────────────────────────────────────────
# Fix16: yfinance 티커 실거래 확인
# ──────────────────────────────────────────────
def check_ticker_listed(ticker: str) -> bool:
    """
    yfinance로 해당 티커가 실제 거래 중인지 확인.
    거래량이 존재하면 상장완료로 판단.
    """
    if not ticker:
        return False
    try:
        info = yf.Ticker(ticker).fast_info
        # market_cap 또는 last_price 가 존재하면 상장된 것
        mc = getattr(info, "market_cap", None)
        lp = getattr(info, "last_price", None)
        if mc and mc > 0:
            logger.info("티커 %s: 시가총액 $%.0fB 확인 → 상장완료", ticker, mc / 1e9)
            return True
        if lp and lp > 0:
            logger.info("티커 %s: 가격 $%.2f 확인 → 상장완료", ticker, lp)
            return True
        return False
    except Exception as e:
        logger.debug("티커 %s 확인 실패 (미상장 또는 오류): %s", ticker, e)
        return False


# ──────────────────────────────────────────────
# Fix17: GNews API로 뉴스 검색
# ──────────────────────────────────────────────
def fetch_ipo_news(company: str) -> list[str]:
    """
    GNews API로 회사명 + IPO 키워드 뉴스 검색.
    API 키가 없으면 빈 리스트 반환.
    제목 + 설명을 합쳐서 반환 (Claude 분석용).
    """
    if not GNEWS_API_KEY:
        logger.debug("GNEWS_API_KEY 없음 — 뉴스 수집 스킵")
        return []

    query   = f"{company} IPO"
    url     = "https://gnews.io/api/v4/search"
    params  = {
        "q":        query,
        "lang":     "en",
        "country":  "us",
        "max":      5,
        "sortby":   "publishedAt",
        "apikey":   GNEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        snippets = []
        for a in articles:
            title       = a.get("title", "")
            description = a.get("description", "")
            published   = a.get("publishedAt", "")
            snippets.append(f"[{published[:10]}] {title} — {description}")
        logger.info("%s 뉴스 %d건 수집", company, len(snippets))
        return snippets
    except Exception as e:
        logger.warning("%s 뉴스 수집 실패: %s", company, e)
        return []


# ──────────────────────────────────────────────
# Fix17: Claude AI로 뉴스 분석 → 상태 추출
# ──────────────────────────────────────────────
def analyze_ipo_news_with_ai(
    company: str,
    current_status: str,
    current_valuation: float,
    news_snippets: list[str],
) -> dict:
    """
    수집된 뉴스를 Claude로 분석해
    최신 IPO 상태와 기업가치를 추출.

    반환 예시:
    {
        "status": "제출완료",
        "valuation_bn": 852,
        "filed_date": "2026-05-20",
        "listed_date": null,
        "ticker": null,
        "confidence": "high",
        "summary": "OpenAI가 비공개 S-1을 제출했으며 9월 상장을 목표로 함"
    }
    """
    if not news_snippets:
        return {}

    client = anthropic.Anthropic()

    prompt = f"""You are an IPO status analyst. Based on the news snippets below,
extract the latest IPO status for {company}.

Current data:
- status: {current_status}
- valuation: ${current_valuation}B

News snippets (newest first):
{chr(10).join(f'  {i+1}. {s}' for i, s in enumerate(news_snippets))}

Return ONLY a JSON object with these fields:
{{
  "status": one of ["루머", "검토중", "제출완료", "가격확정", "상장완료"],
  "valuation_bn": number or null (if mentioned, in billions USD),
  "filed_date": "YYYY-MM-DD" or null,
  "listed_date": "YYYY-MM-DD" or null,
  "ticker": "TICKER" or null,
  "confidence": "high" | "medium" | "low",
  "summary": "one sentence summary in Korean"
}}

Status mapping rules:
- "루머": only rumors, no official confirmation
- "검토중": officially considering IPO, no filing yet
- "제출완료": S-1 filed (confidential or public)
- "가격확정": IPO priced, trading imminent
- "상장완료": shares actively trading on exchange

If news does not clearly indicate a status change, keep the current status.
Respond with ONLY the JSON, no other text."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # JSON 추출 (앞뒤 마크다운 제거)
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            result = json.loads(match.group(0))
            logger.info(
                "%s AI 분석 완료: %s → %s (신뢰도: %s) | %s",
                company,
                current_status,
                result.get("status", current_status),
                result.get("confidence", "?"),
                result.get("summary", ""),
            )
            return result
    except Exception as e:
        logger.warning("%s AI 뉴스 분석 실패: %s", company, e)

    return {}


# ──────────────────────────────────────────────
# Fix17: fallback 데이터를 뉴스 분석 결과로 업데이트
# ──────────────────────────────────────────────
def update_ipo_list_with_news(base_list: list[dict]) -> list[dict]:
    """
    1. yfinance 티커 확인 → 상장완료 자동 감지
    2. GNews 뉴스 수집 → Claude 분석
    3. 신뢰도 high/medium 인 경우에만 상태 업데이트
    4. 기존 상태보다 낮은 단계로는 절대 역행하지 않음
       (가격확정 → 검토중 으로 내려가는 것 방지)
    """
    updated = []
    today   = date.today()

    for item in base_list:
        item    = dict(item)  # 원본 보호
        company = item.get("company", "")
        ticker  = item.get("ticker")
        current = item.get("status", "루머")

        # ── Step 1: yfinance 티커 실거래 확인 ──────────────
        if ticker and check_ticker_listed(ticker):
            if item.get("status") != "상장완료":
                logger.info("%s: 티커 %s 거래 확인 → 상장완료 자동 전환", company, ticker)
                item["status"]      = "상장완료"
                item["listed_date"] = item.get("listed_date") or today.isoformat()
                item["source"]     += f" / yfinance 상장 확인 {today}"
            updated.append(item)
            continue

        # ── Step 2: listed_date 날짜 기반 자동 전환 ────────
        listed_raw = item.get("listed_date")
        if listed_raw:
            try:
                if date.fromisoformat(str(listed_raw)[:10]) <= today:
                    if item["status"] != "상장완료":
                        logger.info(
                            "%s: listed_date %s 도달 → 상장완료 자동 전환",
                            company, listed_raw,
                        )
                        item["status"] = "상장완료"
            except ValueError:
                pass

        # ── Step 3: GNews + Claude 뉴스 분석 ───────────────
        news = fetch_ipo_news(company)
        if news:
            ai_result = analyze_ipo_news_with_ai(
                company            = company,
                current_status     = item["status"],
                current_valuation  = item.get("valuation_bn", 0),
                news_snippets      = news,
            )

            if ai_result and ai_result.get("confidence") in ("high", "medium"):
                new_status = ai_result.get("status")

                # 상태가 더 진행된 경우에만 업데이트 (역행 방지)
                if (new_status and
                    STATUS_PRIORITY.get(new_status, 0) >=
                    STATUS_PRIORITY.get(item["status"], 0)):

                    if new_status != item["status"]:
                        logger.info(
                            "%s: 상태 업데이트 %s → %s",
                            company, item["status"], new_status,
                        )

                    item["status"] = new_status

                    # 기업가치 업데이트 (AI가 추출했고 현재보다 클 때만)
                    ai_val = ai_result.get("valuation_bn")
                    if ai_val and ai_val > item.get("valuation_bn", 0):
                        logger.info(
                            "%s: 기업가치 $%.0fB → $%.0fB 업데이트",
                            company, item["valuation_bn"], ai_val,
                        )
                        item["valuation_bn"] = ai_val

                    # 날짜 정보 업데이트 (없던 것만)
                    if ai_result.get("filed_date") and not item.get("filed_date"):
                        item["filed_date"] = ai_result["filed_date"]
                    if ai_result.get("listed_date") and not item.get("listed_date"):
                        item["listed_date"] = ai_result["listed_date"]
                    if ai_result.get("ticker") and not item.get("ticker"):
                        item["ticker"] = ai_result["ticker"]

                    item["source"] += f" / AI 업데이트 {today}: {ai_result.get('summary', '')}"

            # API 속도 제한 방지
            time.sleep(1)

        updated.append(item)

    return updated


# ──────────────────────────────────────────────
# Fix15: 상장 후 경과 기간 기반 가중치
# ──────────────────────────────────────────────
def get_status_weight(item: dict) -> tuple[float, str]:
    """
    상장완료 후 경과 기간에 따라 누적 위험 가중치 반환.
    상장 완료가 위험 해소가 아닌 누적 충격임을 반영.

    0~3개월   → 0.9 (매물 최대 출회, 락업 해제 전)
    3~6개월   → 0.6 (락업 해제, 기관 매도 지속)
    6~12개월  → 0.3 (점진적 시장 소화)
    12개월 초과 → 0.0 (흡수 완료)
    """
    today  = date.today()
    status = item.get("status", "루머")

    if status != "상장완료":
        return STATUS_WEIGHT_BASE.get(status, 0.0), status

    listed_raw = item.get("listed_date")
    if not listed_raw:
        return 0.0, "상장완료"

    try:
        listed_date  = date.fromisoformat(str(listed_raw)[:10])
        months_since = (today - listed_date).days / 30.0

        if months_since <= 3:
            return 0.9, "상장완료(0~3개월)"
        elif months_since <= 6:
            return 0.6, "상장완료(3~6개월)"
        elif months_since <= 12:
            return 0.3, "상장완료(6~12개월)"
        else:
            return 0.0, "상장완료(소화완료)"
    except ValueError:
        return 0.0, "상장완료"


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────
def _is_active(item: dict) -> bool:
    for key in ("active_date", "filed_date", "listed_date"):
        val = item.get(key)
        if val:
            try:
                if date.fromisoformat(str(val)[:10]) >= ACTIVE_FROM:
                    return True
            except ValueError:
                continue
    has_any_date = any(item.get(k) for k in ("active_date", "filed_date", "listed_date"))
    return not has_any_date


def _is_large(item: dict) -> bool:
    return (item.get("valuation_bn") or 0.0) >= LARGE_IPO_THRESHOLD_BN


# ──────────────────────────────────────────────
# 점수 계산
# ──────────────────────────────────────────────
def calculate_ipo_score(ipo_list: list[dict]) -> dict:
    if not isinstance(ipo_list, list):
        ipo_list = []

    total_valuation_bn: float = 0.0
    filed_count:   int = 0
    priced_count:  int = 0
    listed_count:  int = 0
    signals:  list[str] = []
    alerts:   list[str] = []

    for item in ipo_list:
        if not isinstance(item, dict):
            continue

        company = item.get("company", "알 수 없음")
        val_bn  = item.get("valuation_bn") or 0.0

        if not _is_active(item):
            signals.append(f"⏸ {company}: 2026-05-01 이전 액션 — 제외")
            continue
        if not _is_large(item):
            signals.append(f"⏸ {company}: ${val_bn:.0f}B — $50B 미만 제외")
            continue

        weight, status_label = get_status_weight(item)
        weighted_val         = val_bn * weight
        total_valuation_bn  += weighted_val

        original_status = item.get("status", "루머")

        if "상장완료" in status_label:
            listed_count += 1
            if weight > 0:
                signals.append(
                    f"📊 {company}: {status_label} — "
                    f"매물 출회 위험 (${val_bn:.0f}B × {weight})"
                )
            else:
                signals.append(f"✅ {company}: 상장완료 (시장 소화 완료, 점수 제외)")

        elif original_status == "가격확정":
            priced_count += 1
            signals.append(
                f"🚨 {company}: 가격 확정 — 상장 임박 (${val_bn:.0f}B × {weight})"
            )
        elif original_status in ("제출완료", "신청완료"):
            filed_count += 1
            signals.append(
                f"📋 {company}: S-1 제출 완료 (${val_bn:.0f}B × {weight})"
            )
        elif original_status == "검토중":
            signals.append(
                f"🔍 {company}: IPO 검토 중 (${val_bn:.0f}B × {weight})"
            )
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
        "listed_count":       listed_count,
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
    Fix16/17: 뉴스 기반 자동 상태 갱신 파이프라인.
    1. fallback 기준 데이터 로드
    2. yfinance 티커 확인 → 상장완료 자동 감지
    3. GNews + Claude AI → 상태 변화 자동 탐지
    4. 업데이트된 리스트로 점수 계산
    """
    logger.info("IPO 데이터 수집 시작")

    # 뉴스 기반 업데이트 시도
    try:
        updated_list = update_ipo_list_with_news(MEGA_IPO_FALLBACK)
        logger.info("뉴스 기반 업데이트 완료: %d개 기업", len(updated_list))
    except Exception as e:
        logger.warning("뉴스 업데이트 실패, fallback 사용: %s", e)
        updated_list = MEGA_IPO_FALLBACK

    return calculate_ipo_score(updated_list)
