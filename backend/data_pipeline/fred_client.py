# ============================================================
# fred_client.py  –  FRED API 공통 클라이언트
# - 호출 간 딜레이 (분당 120회 제한 → 호출당 0.6초 간격)
# - 자동 재시도 (최대 3회, 지수 백오프)
# - 429/에러 시 fallback 값 반환
# ============================================================

import os
import time
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

FRED_API_KEY   = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL  = "https://api.stlouisfed.org/fred/series/observations"

# 호출 간 최소 간격 (초) — 분당 120회 제한 기준 0.5초, 안전 여유 포함 0.6초
_MIN_INTERVAL  = 0.6
_last_call_ts  = 0.0   # 마지막 호출 시각 (module-level 공유)


def _throttle():
    """호출 간격이 _MIN_INTERVAL 미만이면 슬립."""
    global _last_call_ts
    elapsed = time.time() - _last_call_ts
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_ts = time.time()


def fetch_series(
    series_id: str,
    limit: int = 5,
    sort_order: str = "desc",
    max_retries: int = 3,
) -> list[dict]:
    """
    FRED 시계열 최근 N개 관측값 반환.

    반환 형식:
        [{"date": "2026-05-28", "value": "4.45"}, ...]

    실패 시 빈 리스트 반환 (파이프라인 중단 없음).
    """
    if not FRED_API_KEY:
        logger.error("[FRED] API 키 없음 — FRED_API_KEY 환경변수를 설정하세요")
        return []

    params = {
        "series_id":    series_id,
        "api_key":      FRED_API_KEY,
        "file_type":    "json",
        "limit":        limit,
        "sort_order":   sort_order,
        "observation_start": "2020-01-01",
    }

    for attempt in range(1, max_retries + 1):
        _throttle()
        try:
            resp = requests.get(
                FRED_BASE_URL,
                params=params,
                timeout=15,
            )

            if resp.status_code == 429:
                wait = 2 ** attempt  # 지수 백오프: 2초, 4초, 8초
                logger.warning(
                    f"[FRED] {series_id} Rate Limit (429) — "
                    f"{wait}초 대기 후 재시도 ({attempt}/{max_retries})"
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            obs  = data.get("observations", [])

            # "." 값(결측) 제거
            valid = [o for o in obs if o.get("value") not in (".", "", None)]

            if not valid:
                logger.warning(f"[FRED] {series_id} 유효 데이터 없음")
                return []

            logger.info(
                f"[FRED] {series_id} 수집 완료 — "
                f"최신: {valid[0]['date']} = {valid[0]['value']}"
            )
            return valid

        except requests.exceptions.Timeout:
            logger.warning(
                f"[FRED] {series_id} 타임아웃 "
                f"({attempt}/{max_retries})"
            )
            time.sleep(2 ** attempt)

        except requests.exceptions.RequestException as e:
            logger.warning(
                f"[FRED] {series_id} 요청 실패: {e} "
                f"({attempt}/{max_retries})"
            )
            time.sleep(2 ** attempt)

    logger.error(f"[FRED] {series_id} {max_retries}회 재시도 모두 실패")
    return []


def get_latest_value(
    series_id: str,
    fallback: float | None = None,
    multiplier: float = 1.0,
) -> float | None:
    """
    FRED 시계열 최신값 1개를 float으로 반환.
    실패 시 fallback 반환.

    multiplier: 단위 변환용 (예: % → bps = ×100)
    """
    obs = fetch_series(series_id, limit=5)
    if not obs:
        if fallback is not None:
            logger.warning(
                f"[FRED] {series_id} 수집 실패 → fallback={fallback} 사용"
            )
        return fallback

    try:
        value = float(obs[0]["value"]) * multiplier
        return value
    except (ValueError, KeyError) as e:
        logger.warning(f"[FRED] {series_id} 값 파싱 실패: {e} → fallback={fallback}")
        return fallback
