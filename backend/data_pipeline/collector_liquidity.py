# ============================================================
# collector_liquidity.py  –  W1 주도주 압축 데이터 수집
# 수정: yfinance MultiIndex 컬럼 처리 완전 방어
# ============================================================

import logging
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# ── Fallback 기본값 ───────────────────────────────────────
FALLBACK = {
    "spy_ytd":           11.24,
    "rsp_ytd":            9.48,
    "current_spread":     1.76,
    "spread_percentile":  55.0,
    "rsp_1w_return":      1.5,
}


def _get_close(df: pd.DataFrame, ticker: str) -> pd.Series | None:
    """
    yfinance MultiIndex / 단일Index 모두 대응하는 종가 추출.
    """
    try:
        # MultiIndex 컬럼: ('Close', 'SPY') 형태
        if isinstance(df.columns, pd.MultiIndex):
            if ("Close", ticker) in df.columns:
                return df[("Close", ticker)].dropna()
            # ticker 없이 Close만 있는 경우
            close_cols = [c for c in df.columns if c[0] == "Close"]
            if close_cols:
                return df[close_cols[0]].dropna()

        # 단일 Index 컬럼: 'Close' 형태
        if "Close" in df.columns:
            return df["Close"].dropna()

        # Adj Close 폴백
        if "Adj Close" in df.columns:
            return df["Adj Close"].dropna()

        logger.warning(f"[유동성] {ticker} Close 컬럼 없음: {df.columns.tolist()}")
        return None

    except Exception as e:
        logger.warning(f"[유동성] {ticker} 컬럼 추출 오류: {e}")
        return None


def _calc_ytd_return(ticker: str) -> float | None:
    """연초 대비 수익률(YTD) 계산."""
    try:
        df = yf.download(
            ticker,
            start="2025-12-31",
            auto_adjust=True,
            progress=False,
            actions=False,
        )
        if df is None or df.empty:
            logger.warning(f"[유동성] {ticker} 데이터 없음")
            return None

        close = _get_close(df, ticker)
        if close is None or len(close) < 2:
            return None

        start_price = float(close.iloc[0])
        end_price   = float(close.iloc[-1])

        if start_price <= 0:
            return None

        ytd = round((end_price / start_price - 1) * 100, 2)
        logger.info(f"[유동성] {ticker} YTD: {ytd}%")
        return ytd

    except Exception as e:
        logger.warning(f"[유동성] {ticker} YTD 계산 실패: {e}")
        return None


def _calc_1w_return(ticker: str) -> float | None:
    """1주 수익률 계산."""
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

        close = _get_close(df, ticker)
        if close is None or len(close) < 6:
            return None

        end_price   = float(close.iloc[-1])
        start_price = float(close.iloc[-6])   # 약 5거래일 전

        if start_price <= 0:
            return None

        return round((end_price / start_price - 1) * 100, 2)

    except Exception as e:
        logger.warning(f"[유동성] {ticker} 1주 수익률 계산 실패: {e}")
        return None


def collect_liquidity_data() -> dict:
    """W1 주도주 압축 데이터 수집 및 점수 산출."""
    logger.info("[주도주압축] 데이터 수집 시작")

    # ── YTD 수익률 ────────────────────────────────────────
    spy_ytd = _calc_ytd_return("SPY") or FALLBACK["spy_ytd"]
    rsp_ytd = _calc_ytd_return("RSP") or FALLBACK["rsp_ytd"]

    # ── 괴리율 ────────────────────────────────────────────
    spread = round(spy_ytd - rsp_ytd, 2)

    # ── 퍼센타일 추정 (히스토리 없는 경우 간이 추정) ─────
    # 괴리율 기준 간이 퍼센타일 매핑
    if spread >= 8.0:
        percentile = 97
    elif spread >= 6.0:
        percentile = 93
    elif spread >= 4.0:
        percentile = 82
    elif spread >= 2.0:
        percentile = 65
    elif spread >= 1.0:
        percentile = 52
    else:
        percentile = 38

    # ── RSP 1주 수익률 ────────────────────────────────────
    rsp_1w = _calc_1w_return("RSP") or FALLBACK["rsp_1w_return"]
    rsp_is_negative = rsp_1w < 0 and spy_ytd > 0

    # ── 점수 산출 ─────────────────────────────────────────
    score = 0

    # 괴리율 기반 (0~60점)
    if spread >= 8.0:
        score += 60
    elif spread >= 6.0:
        score += 50
    elif spread >= 4.0:
        score += 35
    elif spread >= 2.0:
        score += 22
    elif spread >= 1.0:
        score += 12
    else:
        score += 5

    # RSP 음수 트리거 보너스 (0~25점)
    if rsp_is_negative:
        score += 25
    elif rsp_1w < 0.5:
        score += 8

    # 퍼센타일 보너스 (0~15점)
    if percentile >= 95:
        score += 15
    elif percentile >= 85:
        score += 10
    elif percentile >= 70:
        score += 5

    score = min(100, score)
    grade = "RED" if score >= 70 else "YELLOW" if score >= 40 else "GREEN"

    logger.info(
        f"[주도주압축] SPY YTD:{spy_ytd}% RSP YTD:{rsp_ytd}% "
        f"괴리:{spread}%p 퍼센타일:{percentile}%ile "
        f"RSP1w:{rsp_1w}% 점수:{score}"
    )

    return {
        "score":                            score,
        "grade":                            grade,
        "spy_ytd":                          spy_ytd,
        "rsp_ytd":                          rsp_ytd,
        "current_spread":                   spread,
        "spread_percentile":                percentile,
        "rsp_1w_return":                    rsp_1w,
        "rsp_is_negative_while_spy_positive": rsp_is_negative,
        "timestamp":                        datetime.now(timezone.utc).isoformat(),
    }
