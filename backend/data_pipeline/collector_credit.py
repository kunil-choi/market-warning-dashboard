"""
collector_credit.py
W3 · 사모크레딧 환매 위험 모니터링

핵심 로직:
  - HY/IG OAS는 공개시장 스프레드 → 사모크레딧 환매 위험의 후행 보조 지표
  - 주 지표 3개:
      1. 상장 BDC NAV 할인율  (수동 업데이트, mark-to-model 신뢰도 게이지)
      2. SLOOS C&I 대출 긴축   (FRED DRTSCILM, 은행→NBFI 전이 경로)
      3. C&I 대출 연체율        (FRED DRCCLBS,  기초 신용 품질)
  - 보조 지표 2개:
      4. HY OAS 수준             (FRED BAMLH0A0HYM2)
      5. HY 1개월 변화           (리스크오프 확인용)
  - 추가 지표 3개 (Fix-KR1):
      6. 인터벌 펀드 환매 충족율  (수동 업데이트)
      7. PIK 이자 비중            (수동 업데이트)
      8. CLO BB 트랜치 스프레드   (FRED CLOBB 근사치)
  - Fix-News: Claude AI 웹검색으로 실질 환매 제한 뉴스 탐지
"""

import os
import logging
import re
from datetime import datetime, timezone

import anthropic

from backend.data_pipeline.fred_client import get_latest_value, fetch_series

logger = logging.getLogger(__name__)

# ── FRED 시리즈 ───────────────────────────────────────────
HY_SERIES_ID      = "BAMLH0A0HYM2"   # ICE BofA HY OAS (%)
IG_SERIES_ID      = "BAMLC0A0CM"     # ICE BofA IG OAS (%)
SLOOS_SERIES_ID   = "DRTSCILM"       # SLOOS: C&I 긴축 순비율 (분기, %)
CI_DELQ_SERIES_ID = "DRCCLBS"        # C&I 대출 연체율 (분기, %)
# CLO BB 근사: ICE BofA CCC/Below OAS (공개 가능한 가장 가까운 프록시)
CLO_PROXY_SERIES_ID = "BAMLH0A3HYCEY"  # ICE BofA CCC rated HY OAS

# ── Fallback (최근 관측값, 업데이트 시 수정) ─────────────
HY_FALLBACK:       float = 272.0   # bps (2026-05-28)
IG_FALLBACK:       float = 74.0    # bps (2026-05-25)
SLOOS_FALLBACK:    float = 14.5    # % (2025-Q4)
CI_DELQ_FALLBACK:  float = 1.55    # % (2025-Q4)
CLO_BB_FALLBACK:   float = 650.0   # bps (2026-05 추정, CLO BB 프록시)
LOOKBACK_DAYS:     int   = 22

# ── BDC NAV 할인율 (수동 업데이트) ───────────────────────
BDC_NAV_DISCOUNT_PCT: float = 3.5      # % (2026-05-30, ARCC/OBDC/FSK 평균)
BDC_NAV_UPDATE_DATE:  str   = "2026-05-30"

# ── 추가 수동 지표 (Fix-KR1) ─────────────────────────────
# 인터벌 펀드 환매 충족율: 분기 환매 요청 대비 실제 처리 비율
# 100% = 모든 환매 요청 처리, 50% = 절반만 처리(게이팅 진행 중)
INTERVAL_FUND_REDEMPTION_RATE: float = 95.0   # % (2026-Q1, SEC Form N-CEN 근거)
INTERVAL_FUND_UPDATE_DATE: str = "2026-03-31"

# PIK(Payment-in-Kind) 이자 비중: 현금 대신 추가 부채로 이자 지급 비율
# 2~5% = 정상, 5~10% = 주의, 10~15% = 경고, 15% 이상 = 위험
PIK_RATIO_PCT: float = 6.5   # % (2026-Q1, Cliffwater BDC Index 기준)
PIK_UPDATE_DATE: str = "2026-03-31"


# ── 점수 헬퍼 ────────────────────────────────────────────

def _score_bdc_discount(discount_pct: float) -> int:
    """BDC NAV 할인율 → 0-100 점수."""
    if discount_pct >= 25: return 100
    if discount_pct >= 15: return 70
    if discount_pct >= 10: return 45
    if discount_pct >= 5:  return 20
    return 5


def _score_sloos(sloos_pct: float) -> int:
    """C&I 대출 긴축 순비율 → 0-100."""
    if sloos_pct >= 50: return 100
    if sloos_pct >= 30: return 70
    if sloos_pct >= 15: return 40
    if sloos_pct >= 5:  return 20
    if sloos_pct <= -10: return 0
    return 8


def _score_ci_delq(delq_pct: float) -> int:
    """C&I 대출 연체율 → 0-100."""
    if delq_pct >= 5.0: return 100
    if delq_pct >= 3.0: return 70
    if delq_pct >= 2.0: return 40
    if delq_pct >= 1.5: return 20
    return 8


def _score_hy_level(hy_bps: float) -> int:
    if hy_bps >= 600: return 100
    if hy_bps >= 400: return 60
    if hy_bps >= 300: return 30
    if hy_bps >= 200: return 15
    return 5


def _score_hy_change(change_bps: float) -> int:
    if change_bps >= 100: return 100
    if change_bps >= 50:  return 60
    if change_bps >= 20:  return 30
    return 0


def _score_interval_fund(redemption_rate: float) -> int:
    """인터벌 펀드 환매 충족율 → 0-100 (낮을수록 위험)."""
    if redemption_rate <= 50:  return 100
    if redemption_rate <= 70:  return 70
    if redemption_rate <= 85:  return 40
    if redemption_rate <= 95:  return 15
    return 0   # 100% 충족 = 문제 없음


def _score_pik_ratio(pik_pct: float) -> int:
    """PIK 이자 비중 → 0-100 (높을수록 위험)."""
    if pik_pct >= 15: return 100
    if pik_pct >= 10: return 70
    if pik_pct >= 5:  return 35
    if pik_pct >= 2:  return 10
    return 0


def _score_clo_bb(clo_bps: float) -> int:
    """CLO BB 트랜치 스프레드 → 0-100."""
    if clo_bps >= 900:  return 100
    if clo_bps >= 700:  return 70
    if clo_bps >= 550:  return 40
    if clo_bps >= 400:  return 20
    return 5


def _grade(score: int) -> tuple[str, str]:
    if score >= 80: return "위험", "red"
    if score >= 60: return "경고", "orange"
    if score >= 40: return "주의", "yellow"
    return "정상", "green"


# ── Fix-News: Claude AI 웹검색으로 환매 제한 뉴스 탐지 ──

def search_redemption_gate_news() -> dict:
    """
    Claude AI + 웹검색으로 최근 사모크레딧 환매 제한 뉴스 탐지.
    반환: { "has_gate_event": bool, "summary": str, "events": list[str], "risk_bump": int }
    """
    try:
        client = anthropic.Anthropic()

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    "Search for the latest news (within the last 3 months) about "
                    "private credit redemption gates, suspension of redemptions, "
                    "interval fund redemption restrictions, or BDC NAV discounts widening. "
                    "Also search for 'private credit gating 2025 2026' and "
                    "'interval fund redemption queue 2025 2026'. "
                    "Return a JSON object with: "
                    "{\"has_gate_event\": bool, "
                    "\"events\": [list of brief event descriptions in Korean, max 3], "
                    "\"risk_level\": \"none\"|\"low\"|\"medium\"|\"high\", "
                    "\"summary\": \"one sentence in Korean\"}"
                )
            }],
        )

        # 텍스트 블록 추출
        full_text = " ".join(
            block.text for block in response.content
            if hasattr(block, "text")
        )

        # JSON 추출
        match = re.search(r"\{.*\}", full_text, re.S)
        if match:
            import json
            result = json.loads(match.group(0))
            risk_level = result.get("risk_level", "none")
            risk_bump = {"none": 0, "low": 5, "medium": 15, "high": 30}.get(risk_level, 0)
            return {
                "has_gate_event": bool(result.get("has_gate_event", False)),
                "events":         result.get("events", []),
                "summary":        result.get("summary", ""),
                "risk_level":     risk_level,
                "risk_bump":      risk_bump,
            }

    except Exception as e:
        logger.warning("환매 제한 뉴스 검색 실패: %s", e)

    return {
        "has_gate_event": False,
        "events": [],
        "summary": "뉴스 검색 불가",
        "risk_level": "none",
        "risk_bump": 0,
    }


# ── 메인 수집 함수 ────────────────────────────────────────

def collect_credit_data() -> dict:
    """
    사모크레딧 환매 위험 지표를 수집하고 종합 점수를 계산한다.

    점수 가중치:
      BDC NAV 할인율     20%  (주: 시장의 사모 마크 신뢰도)
      SLOOS C&I 긴축     20%  (주: 은행→NBFI 전이 경로)
      C&I 연체율         10%  (주: 기초 신용 품질)
      HY OAS 수준        10%  (보조: 공개시장 후행 지표)
      HY 1개월 변화      10%  (보조: 리스크오프 확인)
      인터벌펀드 환매율  10%  (추가: 직접 게이팅 신호)
      PIK 이자 비중      10%  (추가: 부실 은폐 신호)
      CLO BB 스프레드    10%  (추가: 레버리지론 스트레스)
      뉴스 이벤트 범프   (가산점, 최대 30점)
    """
    logger.info("사모크레딧 환매 위험 수집 시작")

    # ── 1. HY/IG OAS (FRED, 보조 지표) ──────────────────
    hy_pct = get_latest_value(HY_SERIES_ID, fallback=None)
    hy_bps = (hy_pct * 100) if hy_pct is not None else HY_FALLBACK
    if hy_pct is None:
        logger.warning("HY FRED 수집 실패 → fallback %.1f bps", HY_FALLBACK)

    ig_pct = get_latest_value(IG_SERIES_ID, fallback=None)
    ig_bps = (ig_pct * 100) if ig_pct is not None else IG_FALLBACK
    if ig_pct is None:
        logger.warning("IG FRED 수집 실패 → fallback %.1f bps", IG_FALLBACK)

    # HY 1개월 변화
    hy_change_bps: float = 0.0
    try:
        series = fetch_series(HY_SERIES_ID, limit=LOOKBACK_DAYS + 5, sort_order="asc")
        if series and len(series) >= 2:
            oldest = series[0].get("value")
            latest = series[-1].get("value")
            if oldest is not None and latest is not None:
                hy_change_bps = (float(latest) - float(oldest)) * 100
    except Exception as exc:
        logger.warning("HY 변화량 계산 실패: %s", exc)

    # ── 2. SLOOS C&I 긴축 (FRED, 분기) ──────────────────
    sloos_raw = get_latest_value(SLOOS_SERIES_ID, fallback=None)
    if sloos_raw is None:
        logger.warning("SLOOS FRED 수집 실패 → fallback %.1f%%", SLOOS_FALLBACK)
        sloos_pct = SLOOS_FALLBACK
        sloos_source = "fallback"
    else:
        sloos_pct = sloos_raw
        sloos_source = "FRED"

    # ── 3. C&I 대출 연체율 (FRED, 분기) ─────────────────
    ci_delq_raw = get_latest_value(CI_DELQ_SERIES_ID, fallback=None)
    if ci_delq_raw is None:
        logger.warning("C&I 연체율 FRED 수집 실패 → fallback %.2f%%", CI_DELQ_FALLBACK)
        ci_delq_pct = CI_DELQ_FALLBACK
        ci_delq_source = "fallback"
    else:
        ci_delq_pct = ci_delq_raw
        ci_delq_source = "FRED"

    # ── 4. CLO BB 프록시 (FRED) ──────────────────────────
    clo_proxy_raw = get_latest_value(CLO_PROXY_SERIES_ID, fallback=None)
    clo_bb_bps = (clo_proxy_raw * 100) if clo_proxy_raw is not None else CLO_BB_FALLBACK
    clo_bb_source = "FRED(CCC proxy)" if clo_proxy_raw is not None else "fallback"

    # ── 5. BDC NAV 할인율 (수동 유지) ────────────────────
    bdc_discount    = BDC_NAV_DISCOUNT_PCT

    # ── 6. 인터벌 펀드 환매 충족율 / PIK (수동) ──────────
    interval_rate   = INTERVAL_FUND_REDEMPTION_RATE
    pik_ratio       = PIK_RATIO_PCT

    # ── 7. Fix-News: 환매 제한 뉴스 탐지 ─────────────────
    gate_news = search_redemption_gate_news()

    # ── 8. 개별 점수 산출 ─────────────────────────────────
    s_bdc      = _score_bdc_discount(bdc_discount)
    s_sloos    = _score_sloos(sloos_pct)
    s_ci       = _score_ci_delq(ci_delq_pct)
    s_hy_lv    = _score_hy_level(hy_bps)
    s_hy_ch    = _score_hy_change(hy_change_bps)
    s_interval = _score_interval_fund(interval_rate)
    s_pik      = _score_pik_ratio(pik_ratio)
    s_clo      = _score_clo_bb(clo_bb_bps)

    raw_score = round(
        s_bdc      * 0.20 +
        s_sloos    * 0.20 +
        s_ci       * 0.10 +
        s_hy_lv    * 0.10 +
        s_hy_ch    * 0.10 +
        s_interval * 0.10 +
        s_pik      * 0.10 +
        s_clo      * 0.10
    )

    # 뉴스 이벤트 범프 가산
    raw_score = min(raw_score + gate_news["risk_bump"], 100)
    grade, color = _grade(raw_score)

    # ── 9. 시그널 메시지 ──────────────────────────────────
    signals: list[str] = []

    if bdc_discount >= 25:
        signals.append(f"🚨 BDC NAV 할인율 {bdc_discount:.1f}% — 시장이 사모 마크를 극도로 불신")
    elif bdc_discount >= 15:
        signals.append(f"⚠️ BDC NAV 할인율 {bdc_discount:.1f}% — 환매 압력 심화 가능성")
    elif bdc_discount >= 5:
        signals.append(f"📢 BDC NAV 할인율 {bdc_discount:.1f}% — 소폭 불신, 추이 모니터링")
    else:
        signals.append(f"✅ BDC NAV 할인율 {bdc_discount:.1f}% — 시장이 사모 마크 신뢰")

    if sloos_pct >= 30:
        signals.append(f"🚨 C&I 대출 긴축 {sloos_pct:.1f}% — 은행→NBFI 전이 위험 고조")
    elif sloos_pct >= 15:
        signals.append(f"⚠️ C&I 대출 긴축 {sloos_pct:.1f}% — 신용 공급 수축 진행")
    elif sloos_pct >= 5:
        signals.append(f"📢 C&I 대출 긴축 {sloos_pct:.1f}% — 소폭 긴축")
    elif sloos_pct <= -10:
        signals.append(f"✅ C&I 대출 완화 {sloos_pct:.1f}% — 은행 신용 공급 확장")
    else:
        signals.append(f"✅ C&I 대출 기준 중립 {sloos_pct:.1f}%")

    if ci_delq_pct >= 3.0:
        signals.append(f"⚠️ C&I 연체율 {ci_delq_pct:.2f}% — 기초 신용 품질 악화")
    else:
        signals.append(f"✅ C&I 연체율 {ci_delq_pct:.2f}% — 정상 범위")

    if interval_rate <= 70:
        signals.append(f"🚨 인터벌펀드 환매 충족율 {interval_rate:.0f}% — 게이팅 진행 중")
    elif interval_rate <= 85:
        signals.append(f"⚠️ 인터벌펀드 환매 충족율 {interval_rate:.0f}% — 대기열 증가")
    elif interval_rate <= 95:
        signals.append(f"📢 인터벌펀드 환매 충족율 {interval_rate:.0f}% — 소폭 지연")
    else:
        signals.append(f"✅ 인터벌펀드 환매 충족율 {interval_rate:.0f}% — 정상 처리")

    if pik_ratio >= 10:
        signals.append(f"🚨 PIK 이자 비중 {pik_ratio:.1f}% — 부실 은폐 가능성 높음")
    elif pik_ratio >= 5:
        signals.append(f"⚠️ PIK 이자 비중 {pik_ratio:.1f}% — 현금흐름 압박 신호")
    else:
        signals.append(f"✅ PIK 이자 비중 {pik_ratio:.1f}% — 정상 범위")

    if clo_bb_bps >= 700:
        signals.append(f"🚨 CLO BB 스프레드 {clo_bb_bps:.0f} bps — 레버리지론 시장 심각")
    elif clo_bb_bps >= 550:
        signals.append(f"⚠️ CLO BB 스프레드 {clo_bb_bps:.0f} bps — 경계 구간")
    else:
        signals.append(f"📊 CLO BB(프록시) {clo_bb_bps:.0f} bps — 정상")

    if hy_bps >= 400:
        signals.append(f"🚨 HY 스프레드 {hy_bps:.0f} bps — 리스크오프 확인 (후행)")
    elif hy_bps >= 300:
        signals.append(f"⚠️ HY 스프레드 {hy_bps:.0f} bps — 주의 구간 (후행)")
    else:
        signals.append(f"📊 HY 스프레드 {hy_bps:.0f} bps — 정상 (후행 보조)")

    if hy_change_bps >= 20:
        signals.append(f"📈 HY 1개월 변화: +{hy_change_bps:.0f} bps (리스크오프 진행)")

    # 뉴스 이벤트 시그널
    if gate_news["has_gate_event"]:
        signals.append(f"🚨 실질 환매 제한 이벤트 감지: {gate_news['summary']}")
        for ev in gate_news["events"][:2]:
            signals.append(f"   📰 {ev}")
    else:
        signals.append(f"✅ 실질 환매 제한 이벤트 미감지 ({gate_news['summary']})")

    result = {
        "score":              raw_score,
        "grade":              grade,
        "color":              color,
        # 주 지표
        "bdc_nav_discount":   round(bdc_discount, 1),
        "bdc_nav_date":       BDC_NAV_UPDATE_DATE,
        "sloos_ci_pct":       round(sloos_pct, 1),
        "sloos_source":       sloos_source,
        "ci_delq_pct":        round(ci_delq_pct, 2),
        "ci_delq_source":     ci_delq_source,
        # 보조 지표
        "hy_bps":             round(hy_bps, 1),
        "ig_bps":             round(ig_bps, 1),
        "hy_change_bps":      round(hy_change_bps, 1),
        # 추가 지표 (Fix-KR1)
        "interval_fund_redemption_rate": round(interval_rate, 1),
        "interval_fund_date": INTERVAL_FUND_UPDATE_DATE,
        "pik_ratio_pct":      round(pik_ratio, 1),
        "pik_update_date":    PIK_UPDATE_DATE,
        "clo_bb_bps":         round(clo_bb_bps, 1),
        "clo_bb_source":      clo_bb_source,
        # 뉴스 이벤트
        "gate_news":          gate_news,
        # 개별 점수
        "s_bdc":              s_bdc,
        "s_sloos":            s_sloos,
        "s_ci":               s_ci,
        "s_hy_level":         s_hy_lv,
        "s_hy_change":        s_hy_ch,
        "s_interval":         s_interval,
        "s_pik":              s_pik,
        "s_clo":              s_clo,
        "signals":            signals,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "사모크레딧: BDC할인 %.1f%% | SLOOS %.1f%% | HY %.0f bps | "
        "인터벌펀드 %.0f%% | PIK %.1f%% | CLO BB %.0f bps | 점수 %d점 (%s)",
        bdc_discount, sloos_pct, hy_bps,
        interval_rate, pik_ratio, clo_bb_bps,
        raw_score, grade,
    )
    return result
