# ============================================================
# fred_client.py  –  FRED API 공통 클라이언트
# 수정: global 키워드 명시, 타임아웃 강화
# ============================================================

import os
import time
import logging

import requests

logger = logging.getLogger(__name__)

FRED_API_KEY  = os.getenv("FRED_API_KEY", "")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

_MIN_INTERVAL = 0.6   # 초 (분당 최대 100회 기준, 안전 여유 포함)
_last_call_ts = 0.0


def _throttle():
    """호출 간격이 _MIN_INTERVAL 미만이면 슬립."""
    global _last_call_ts                          # ← 명시적 선언
    elapsed = time.time() - _last_call_ts
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_ts = time.time()


def fetch_series(
    series_id:   str,
    limit:       int = 5,
    sort_order:  str = "desc",
    max_retries: int = 3,
) -> list[dict]:
    """
    FRED 시계열 최근 N개 관측값 반환.
    실패 시 빈 리스트 반환 (파이프라인 중단 없음).
    """
    if not FRED_API_KEY:
        logger.error("[FRED] FRED_API_KEY 환경변수가 설정되지 않았습니다")
        return []

    params = {
        "series_id":         series_id,
        "api_key":           FRED_API_KEY,
        "file_type":         "json",
        "limit":             limit,
        "sort_order":        sort_order,
        "observation_start": "2020-01-01",
    }

    for attempt in range(1, max_retries + 1):
        _throttle()
        try:
            resp = requests.get(
                FRED_BASE_URL,
                params=params,
                timeout=20,
            )

            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning(
                    f"[FRED] {series_id} Rate Limit(429) — "
                    f"{wait}초 대기 후 재시도 ({attempt}/{max_retries})"
                )
                time.sleep(wait)
                continue

            if resp.status_code == 400:
                logger.error(
                    f"[FRED] {series_id} 잘못된 요청(400): "
                    f"{resp.text[:200]}"
                )
                return []

            resp.raise_for_status()
            data = resp.json()
            obs  = data.get("observations", [])

            # 결측값("." ) 제거
            valid = [
                o for o in obs
                if o.get("value") not in (".", "", None)
            ]

            if not valid:
                logger.warning(f"[FRED] {series_id} 유효 관측값 없음")
                return []

            logger.info(
                f"[FRED] {series_id} 수집 완료 — "
                f"최신: {valid[0]['date']} = {valid[0]['value']}"
            )
            return valid

        except requests.exceptions.Timeout:
            logger.warning(
                f"[FRED] {series_id} 타임아웃 ({attempt}/{max_retries})"
            )
            time.sleep(2 ** attempt)

        except requests.exceptions.ConnectionError:
            logger.warning(
                f"[FRED] {series_id} 연결 오류 ({attempt}/{max_retries})"
            )
            time.sleep(2 ** attempt)

        except requests.exceptions.RequestException as e:
            logger.warning(
                f"[FRED] {series_id} 요청 실패: {e} ({attempt}/{max_retries})"
            )
            time.sleep(2 ** attempt)

        except Exception as e:
            logger.error(
                f"[FRED] {series_id} 예상치 못한 오류: {e} ({attempt}/{max_retries})"
            )
            time.sleep(2 ** attempt)

    logger.error(f"[FRED] {series_id} {max_retries}회 재시도 모두 실패")
    return []


def get_latest_value(
    series_id:  str,
    fallback:   float | None = None,
    multiplier: float = 1.0,
) -> float | None:
    """
    FRED 시계열 최신값 1개를 float으로 반환.
    실패 시 fallback 반환.
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
        return round(value, 4)
    except (ValueError, KeyError, TypeError) as e:
        logger.warning(
            f"[FRED] {series_id} 값 파싱 실패: {e} → fallback={fallback}"
        )
        return fallback
