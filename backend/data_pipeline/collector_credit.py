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
"""

import logging
from datetime import datetime, timezone

from backend.data_pipeline.fred_client import get_latest_value, fetch_series

logger = logging.getLogger(__name__)

# ── FRED 시리즈 ───────────────────────────────────────────
HY_SERIES_ID      = "BAMLH0A0HYM2"   # ICE BofA HY OAS (%)
IG_SERIES_ID      = "BAMLC0A0CM"     # ICE BofA IG OAS (%)
SLOOS_SERIES_ID   = "DRTSCILM"       # SLOOS: C&I 긴축 순비율 (분기, %)
CI_DELQ_SERIES_ID = "DRCCLBS"        # C&I 대출 연체율 (분기, %)

# ── Fallback (최근 관측값, 업데이트 시 수정) ─────────────
HY_FALLBACK:       float = 272.0   # bps (2026-05-28)
IG_FALLBACK:       float = 74.0    # bps (2026-05-25)
SLOOS_FALLBACK:    float = 14.5    # % (2025-Q4, 은행 긴축 소폭 진행 중)
CI_DELQ_FALLBACK:  float = 1.55    # % (2025-Q4)
LOOKBACK_DAYS:     int   = 22

# ── BDC NAV 할인율 (수동 업데이트) ───────────────────────
# 주요 상장 BDC(ARCC, OBDC, FSK 등) 평균 NAV 대비 주가 할인율
# 양수 = 할인(주가 < NAV), 음수 = 프리미엄(주가 > NAV)
# 정상: -5 ~ +5%  |  주의: +5 ~ +15%  |  경고: +15 ~ +25%  |  위험: +25% 이상
BDC_NAV_DISCOUNT_PCT: float = 3.5      # % (2026-05-30, ARCC/OBDC/FSK 평균)
BDC_NAV_UPDATE_DATE:  str   = "2026-05-30"


# ── 점수 헬퍼 ────────────────────────────────────────────

def _score_bdc_discount(discount_pct: float) -> int:
    """BDC NAV 할인율 → 0-100 점수. 할인이 클수록 위험."""
    if discount_pct >= 25:
        return 100
    if discount_pct >= 15:
        return 70
    if discount_pct >= 10:
        return 45
    if discount_pct >= 5:
        return 20
    return 5  # 프리미엄 또는 소폭 할인 → 시장이 운용사 NAV 신뢰


def _score_sloos(sloos_pct: float) -> int:
    """C&I 대출 긴축 순비율 → 0-100. 양수(긴축)일수록 위험."""
    if sloos_pct >= 50:
        return 100
    if sloos_pct >= 30:
        return 70
    if sloos_pct >= 15:
        return 40
    if sloos_pct >= 5:
        return 20
    if sloos_pct <= -10:
        return 0   # 완화 기조 → 긍정
    return 8


def _score_ci_delq(delq_pct: float) -> int:
    """C&I 대출 연체율 → 0-100. 높을수록 위험."""
    if delq_pct >= 5.0:
        return 100
    if delq_pct >= 3.0:
        return 70
    if delq_pct >= 2.0:
        return 40
    if delq_pct >= 1.5:
        return 20
    return 8


def _score_hy_level(hy_bps: float) -> int:
    if hy_bps >= 600:
        return 100
    if hy_bps >= 400:
        return 60
    if hy_bps >= 300:
        return 30
    if hy_bps >= 200:
        return 15
    return 5


def _score_hy_change(change_bps: float) -> int:
    if change_bps >= 100:
        return 100
    if change_bps >= 50:
        return 60
    if change_bps >= 20:
        return 30
    return 0


def _grade(score: int) -> tuple[str, str]:
    if score >= 80:
        return "위험", "red"
    if score >= 60:
        return "경고", "orange"
    if score >= 40:
        return "주의", "yellow"
    return "정상", "green"


# ── 메인 수집 함수 ────────────────────────────────────────

def collect_credit_data() -> dict:
    """
    사모크레딧 환매 위험 지표를 수집하고 종합 점수를 계산한다.

    점수 가중치:
      BDC NAV 할인율     25%  (주: 시장의 사모 마크 신뢰도)
      SLOOS C&I 긴축     25%  (주: 은행→NBFI 전이 경로)
      C&I 연체율         15%  (주: 기초 신용 품질)
      HY OAS 수준        20%  (보조: 공개시장 후행 지표)
      HY 1개월 변화      15%  (보조: 리스크오프 확인)
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

    # ── 4. BDC NAV 할인율 (수동 유지) ────────────────────
    bdc_discount = BDC_NAV_DISCOUNT_PCT

    # ── 5. 개별 점수 산출 ─────────────────────────────────
    s_bdc    = _score_bdc_discount(bdc_discount)
    s_sloos  = _score_sloos(sloos_pct)
    s_ci     = _score_ci_delq(ci_delq_pct)
    s_hy_lv  = _score_hy_level(hy_bps)
    s_hy_ch  = _score_hy_change(hy_change_bps)

    raw_score = round(
        s_bdc   * 0.25 +
        s_sloos * 0.25 +
        s_ci    * 0.15 +
        s_hy_lv * 0.20 +
        s_hy_ch * 0.15
    )
    raw_score = min(raw_score, 100)
    grade, color = _grade(raw_score)

    # ── 6. 시그널 메시지 ──────────────────────────────────
    signals: list[str] = []

    # BDC 할인율 시그널 (주 지표)
    if bdc_discount >= 25:
        signals.append(f"🚨 BDC NAV 할인율 {bdc_discount:.1f}% — 시장이 사모 마크를 극도로 불신")
    elif bdc_discount >= 15:
        signals.append(f"⚠️ BDC NAV 할인율 {bdc_discount:.1f}% — 환매 압력 심화 가능성")
    elif bdc_discount >= 5:
        signals.append(f"📢 BDC NAV 할인율 {bdc_discount:.1f}% — 소폭 불신, 추이 모니터링")
    else:
        signals.append(f"✅ BDC NAV 할인율 {bdc_discount:.1f}% — 시장이 사모 마크 신뢰")

    # SLOOS 시그널 (주 지표)
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

    # C&I 연체율 시그널
    if ci_delq_pct >= 3.0:
        signals.append(f"⚠️ C&I 연체율 {ci_delq_pct:.2f}% — 기초 신용 품질 악화")
    else:
        signals.append(f"✅ C&I 연체율 {ci_delq_pct:.2f}% — 정상 범위")

    # HY 시그널 (보조 지표)
    if hy_bps >= 400:
        signals.append(f"🚨 HY 스프레드 {hy_bps:.0f} bps — 리스크오프 확인 (후행)")
    elif hy_bps >= 300:
        signals.append(f"⚠️ HY 스프레드 {hy_bps:.0f} bps — 주의 구간 (후행)")
    else:
        signals.append(f"📊 HY 스프레드 {hy_bps:.0f} bps — 정상 (후행 보조)")

    if hy_change_bps >= 20:
        signals.append(f"📈 HY 1개월 변화: +{hy_change_bps:.0f} bps (리스크오프 진행)")

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
        # 개별 점수
        "s_bdc":              s_bdc,
        "s_sloos":            s_sloos,
        "s_ci":               s_ci,
        "s_hy_level":         s_hy_lv,
        "s_hy_change":        s_hy_ch,
        "signals":            signals,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
    }

    logger.info(
        "사모크레딧: BDC할인 %.1f%% | SLOOS %.1f%% | HY %.0f bps | 점수 %d점 (%s)",
        bdc_discount, sloos_pct, hy_bps, raw_score, grade,
    )
    return result
