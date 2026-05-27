from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from pathlib import Path
from datetime import datetime

app = FastAPI(
    title="맹목적 강세장 경고 대시보드 API",
    description="김효진 박사 강연 기반 4대 매크로 경고등 시스템",
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
            detail="데이터가 아직 없습니다. 파이프라인을 먼저 실행하세요."
        )
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/scores")
def get_scores():
    return load_latest()


@app.get("/api/composite")
def get_composite():
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
    data = load_latest()
    warnings = data.get("warnings", {})
    if warning_id not in warnings:
        raise HTTPException(
            status_code=404,
            detail=f"유효한 ID: {list(warnings.keys())}"
        )
    return warnings[warning_id]


@app.get("/api/history")
def get_history(days: int = 90):
    if not HISTORY_PATH.exists():
        return {"history": []}
    lines = HISTORY_PATH.read_text(encoding="utf-8").strip().split("\n")
    history = [json.loads(l) for l in lines if l.strip()]
    return {"history": history[-days:]}


@app.get("/api/signal")
def get_signal():
    data = load_latest()
    return data.get("algo_signal", {})


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
