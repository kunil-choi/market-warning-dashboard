# ============================================================
# collector_liquidity.py  –  W1 주도주 압축
# 수정:
#   Bug3 – yfinance 단일 티커 MultiIndex 완전 방어
#   Bug4 – YTD 기준일(2025-12-31) 비거래일 문제 해결
# ============================================================

import logging
import socket
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

FALLBACK = {
    "spy_ytd":           11.24,
    "rsp_ytd":            9.48,
    "current_spread":     1.76,
    "spread_percentile":  55.0,
    "rsp_1w_return":      1.5,
}


def _extract_close(df: pd.DataFrame) -> pd.Series | None:
    """
    yfinance DataFrame에서 종가 시리즈 추출.
    단일/멀티 티커, MultiIndex/단일Index 모두 대응.
    """
    if df is None or df.empty:
        return None

    try:
        cols = df.columns

        # ── MultiIndex 처리 ───────────────────────────────
        if isinstance(cols, pd.MultiIndex):
            # ('Price', 'Ticker') 또는 ('Ticker', 'Price') 형태 모두 처리
            # level 0이 가격 종류인 경우
            level0 = [c[0] for c in cols]
            level1 = [c[1] for c in cols]

            if "Close" in level0:
                # ('Close', 'SPY') 형태
                close_cols = [c for c in cols if c[0] == "Close"]
                series = df[close_cols].iloc[:, 0].dropna()
                return series if not series.empty else None

            if "Close" in level1:
                # ('SPY', 'Close') 형태
                close_cols = [c for c in cols if c[1] == "Close"]
                series = df[close_cols].iloc[:, 0].dropna()
                return series if not series.empty else None

            # Price 레벨 탐색
            for keyword in ["Close", "Adj Close", "close"]:
                for c in cols:
                    if keyword in c:
                        series = df[c].dropna()
                        return series if not series.empty else None

            logger.warning(f"[유동성] MultiIndex에서 Close 컬럼 없음: {cols.tolist()[:6]}")
            return None

        # ── 단일 Index 처리 ───────────────────────────────
        for keyword in ["Close", "Adj Close", "close"]:
            if keyword in cols:
                series = df[keyword].dropna()
                return series if not series.empty else None

        logger.warning(f"[유동성] 단일Index에서 Close 컬럼 없음: {cols.tolist()}")
        return None

    except Exception as e:
        logger.warning(f"[유동성] 종가 추출 오류: {e}")
        return None


def _calc_ytd_return(ticker: str) -> float | None:
    """
    연초 대비 수익률(YTD) 계산.
    Bug4 수정: start를 2025-12-25로 설정해 연말 거래일을 반드시 포함.
    """
    try:
        # 2025-12-25 부터 받으면 12/26, 12/29, 12/31 중
        # 실제 거래일 첫 행이 연초 기준가가 됨
        df = yf.download(
            ticker,
            start="2025-12-25",
            auto_adjust=True,
            progress=False,
            actions=False,
        )

        if df is None or df.empty:
            logger.warning(f"[유동성] {ticker} 데이터 없음")
            return None

        close = _extract_close(df)
        if close is None or len(close) < 2:
            logger.warning(f"[유동성] {ticker} 종가 데이터 부족: {len(close) if close is not None else 0}행")
            return None

        # 2026년 이전 마지막 거래일을 기준가로 사용
        close_2025 = close[close.index.year == 2025]
        close_2026 = close[close.index.year >= 2026]

        if close_2025.empty or close_2026.empty:
            # 연도 구분이 안 되면 첫 행 / 마지막 행 사용
            start_price = float(close.iloc[0])
            end_price   = float(close.iloc[-1])
        else:
            start_price = float(close_2025.iloc[-1])   # 2025년 마지막 종가
            end_price   = float(close_2026.iloc[-1])   # 현재 최신 종가

        if start_price <= 0:
            return None

        ytd = round((end_price / start_price - 1) * 100, 2)
        logger.info(f"[유동성] {ticker} YTD: {ytd}% (기준가:{start_price:.2f} → 현재:{end_price:.2f})")
        return ytd

    except Exception as e:
        logger.warning(f"[유동성] {ticker} YTD 계산 실패: {e}")
        return None


def _calc_1w_return(ticker: str) -> float | None:
    """1주(5거래일) 수익률 계산."""
    try:
        df = yf.download(
            ticker,
            period="10d",
            auto_adjust=True,
            progress=False,
            actions=False,
        )
        if df is None or df.empty:
            return None

        close = _extract_close(df)
        if close is None or len(close) < 6:
            return None

        end_price   = float(close.iloc[-1])
        start_price = float(close.iloc[-6])

        if start_price <= 0:
            return None

        return round((end_price / start_price - 1) * 100, 2)

    except Exception as e:
        logger.warning(f"[유동성] {ticker} 1주 수익률 실패: {e}")
        return None


def collect_liquidity_data() -> dict:
    logger.info("[주도주압축] 데이터 수집 시작")

    spy_ytd = _calc_ytd_return("SPY")
    rsp_ytd = _calc_ytd_return("RSP")

    # fallback 적용
    if spy_ytd is None:
        spy_ytd = FALLBACK["spy_ytd"]
        logger.warning(f"[주도주압축] SPY YTD fallback: {spy_ytd}%")
    if rsp_ytd is None:
        rsp_ytd = FALLBACK["rsp_ytd"]
        logger.warning(f"[주도주압축] RSP YTD fallback: {rsp_ytd}%")

    spread = round(spy_ytd - rsp_ytd, 2)

    # 퍼센타일 간이 추정
    if spread >= 8.0:   percentile = 97
    elif spread >= 6.0: percentile = 93
    elif spread >= 4.0: percentile = 82
    elif spread >= 2.0: percentile = 65
    elif spread >= 1.0: percentile = 52
    else:               percentile = 38

    rsp_1w = _calc_1w_return("RSP")
    if rsp_1w is None:
        rsp_1w = FALLBACK["rsp_1w_return"]

    rsp_is_negative = rsp_1w < 0 and spy_ytd > 0

    # 점수 산출
    score = 0
    if spread >= 8.0:   score += 60
    elif spread >= 6.0: score += 50
    elif spread >= 4.0: score += 35
    elif spread >= 2.0: score += 22
    elif spread >= 1.0: score += 12
    else:               score += 5

    if rsp_is_negative:  score += 25
    elif rsp_1w < 0.5:   score += 8

    if percentile >= 95:   score += 15
    elif percentile >= 85: score += 10
    elif percentile >= 70: score += 5

    score = min(100, score)
    grade = "RED" if score >= 70 else "YELLOW" if score >= 40 else "GREEN"

    logger.info(
        f"[주도주압축] SPY:{spy_ytd}% RSP:{rsp_ytd}% "
        f"괴리:{spread}%p 퍼센타일:{percentile}%ile "
        f"RSP1w:{rsp_1w}% 점수:{score}"
    )

    return {
        "score":                              score,
        "grade":                              grade,
        "spy_ytd":                            spy_ytd,
        "rsp_ytd":                            rsp_ytd,
        "current_spread":                     spread,
        "spread_percentile":                  percentile,
        "rsp_1w_return":                      rsp_1w,
        "rsp_is_negative_while_spy_positive": rsp_is_negative,
        "timestamp":                          datetime.now(timezone.utc).isoformat(),
    }
