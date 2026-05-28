from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
from datetime import datetime

app = FastAPI(
    title="글로벌 증시 위기 경고 대시보드 API",
    description="4대 매크로 경고등 자동 분석 시스템",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

DATA_PATH    = Path("data/latest_scores.json")
HISTORY_PATH = Path("data/history.jsonl")


def load_latest() -> dict:
    if not DATA_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "데이터 파일이 없습니다. "
                "먼저 파이프라인을 실행하세요: "
                "python -m backend.data_pipeline.run_pipeline"
            )
        )
    try:
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"데이터 파일 파싱 오류: {e}"
        )


def load_history(days: int = 90) -> list:
    if not HISTORY_PATH.exists():
        return []

    lines = HISTORY_PATH.read_text(encoding="utf-8").strip().split("\n")
    history = []

    for line in lines:
        try:
            if line.strip():
                history.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return history[-days:]


# ── 엔드포인트 ──

@app.get("/api/scores")
def get_scores():
    """전체 스코어 JSON 반환"""
    return load_latest()


@app.get("/api/composite")
def get_composite():
    """종합 스코어 요약"""
    data = load_latest()
    return {
        "score":        data["composite"]["final_score"],
        "grade":        data["composite"]["overall_grade"],
        "label":        data["composite"]["overall_label"],
        "action":       data["composite"]["action_recommended"],
        "signal":       data["algo_signal"]["signal"],
        "generated_at": data["meta"]["generated_at"],
    }


@app.get("/api/warning/{warning_id}")
def get_warning(warning_id: str):
    """개별 경고등 데이터 반환
    - warning_id: w1_liquidity, w2_rates, w3_credit, w4_ipo
    """
    data     = load_latest()
    warnings = data.get("warnings", {})

    if warning_id not in warnings:
        raise HTTPException(
            status_code=404,
            detail=f"유효한 ID: {list(warnings.keys())}"
        )
    return warnings[warning_id]


@app.get("/api/history")
def get_history(days: int = 90):
    """히스토리 데이터 반환 (최대 days일)"""
    return {"history": load_history(days)}


@app.get("/api/signal")
def get_signal():
    """알고 트레이딩 시그널 반환"""
    return load_latest().get("algo_signal", {})


@app.get("/health")
def health():
    """헬스 체크"""
    data_exists = DATA_PATH.exists()
    return {
        "status":      "ok",
        "timestamp":   datetime.now().isoformat(),
        "data_exists": data_exists,
        "data_path":   str(DATA_PATH),
    }
