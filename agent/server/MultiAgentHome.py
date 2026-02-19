import os
import json
import joblib
from enum import Enum
from typing import TypedDict, Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel

from langgraph.graph import StateGraph
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

# ===============================
# STT / OCR
# ===============================
from faster_whisper import WhisperModel
from PIL import Image
import tempfile

import numpy as np
from skimage.metrics import structural_similarity as ssim

# ===============================
# Action / State
# ===============================

class Action(str, Enum):
    GENERAL_CHAT = "GENERAL_CHAT"
    USE_MODEL = "USE_MODEL"
    MODEL_CHAT = "MODEL_CHAT"

class VisionStatus(str, Enum):
    NORMAL = "NORMAL"
    ABNORMAL = "ABNORMAL"

class PredictionResult(BaseModel):
    prediction: float
    inferred_params: Dict[str, Any]
    model_id: str


class GraphState(TypedDict, total=False):
    input: str

    voice_path: Optional[str]
    image_path: Optional[str]

    weather: Optional[dict]
    temperature: Optional[float]
    rain_flag: Optional[int]
    wind_speed: Optional[float]
    humidity: Optional[int]

    action: Action
    selected_model: Optional[str]
    extracted_values: Dict[str, Any]
  
    diff_score: float
    vision_status: VisionStatus
    predictions: List[PredictionResult]
    response: Optional[str]


# ===============================
# LLM
# ===============================

llm_json = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url="http://localhost:11434"
)

llm_chat = ChatOllama(
    model="llama3.1",
    temperature=0.7,
    base_url="http://localhost:11434"
)

# ===============================
# STT / OCR 초기화
# ===============================

stt_model = WhisperModel("small", device="cpu")

# ===============================
# Model Registry
# ===============================

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(parents=True, exist_ok=True)


def get_registered_models():
    registry = []
    for f in os.listdir(MODEL_DIR):
        if f.endswith(".meta.json"):
            with open(MODEL_DIR / f, encoding="utf-8") as file:
                meta = json.load(file)
                registry.append({
                    "id": meta.get("modelFile"),
                    "description": meta.get("analyze", {}).get("description", ""),
                    "features": meta.get("features", []),
                    "samples": meta.get("category_samples", [])
                })
    return registry


# ===============================
# Nodes
# ===============================

def stt_node(state: GraphState) -> GraphState:
    if not state.get("voice_path"):
        return {}
    print("voice @@@@")
    segments, _ = stt_model.transcribe(
        state["voice_path"],
        language="ko"
    )

    text = " ".join(seg.text for seg in segments)
    return {"input": text}

BASE_IMAGE_PATH = BASE_DIR / "server" / "image" / "KakaoTalk_Photo_2026-02-19-10-22-08 004.jpeg"


def vision_node(state: GraphState) -> GraphState:
    if not state.get("image_path"):
        return {}

    if not BASE_IMAGE_PATH.exists():
        print(f"[Vision][ERROR] Baseline image not found: {BASE_IMAGE_PATH}")
        return {
            "response": "기준 이미지가 설정되지 않았습니다."
        }
    current = Image.open(state["image_path"]).convert("L").resize((512, 512))
    baseline = Image.open(BASE_IMAGE_PATH).convert("L").resize((512, 512))

    current_np = np.array(current)
    baseline_np = np.array(baseline)

    score, _ = ssim(baseline_np, current_np, full=True)

    diff = 1 - score  # 차이 점수 (0 ~ 1)

    action = VisionStatus.ABNORMAL if diff > 0.15 else VisionStatus.NORMAL

    print(f"[Vision] diff score: {diff:.4f}")

    return {
        "diff_score": diff,
        "vision_status": action
    }
def explain_abnormal_node(state: GraphState) -> GraphState:
    print("explain_abnormal_node")

    prompt = f"""
    너는 veneta AI Agent 입니다.
    공장 설비 사진에서 기준 상태 대비 이상 변화가 감지되었습니다.

    변화 점수: {state['diff_score']:.3f}

    작업자가 이해할 수 있도록
    가능한 원인을 간단히 한글로 설명하세요.
    """

    res = llm_chat.invoke(prompt)
    print(f"[Vision] res: {res}")
    return {"response": res.content}


def analyze_prompt(state: GraphState) -> GraphState:
    registry = get_registered_models()
    model_context = "\n".join(
        f"- {m['id']} ({m['features']})"
        for m in registry
    )

    prompt = f"""
    질문을 분석해 행동을 결정하세요.

    규칙:
    - 예측/수치 → USE_MODEL
    - 목록/조회 → MODEL_CHAT
    - 일반 대화 → GENERAL_CHAT

    가용 모델:
    {model_context}

    JSON:
    {{
      "action": "USE_MODEL | MODEL_CHAT | GENERAL_CHAT",
      "target": "model.pkl",
      "values": {{}}
    }}

    질문: {state.get("input")}
    """

    res = llm_json.invoke(prompt)

    try:
        data = json.loads(res.content)
        action = Action(data["action"])
        return {
            "action": action,
            "selected_model": data.get("target"),
            "extracted_values": data.get("values", {})
        }
    except Exception:
        return {"action": Action.GENERAL_CHAT}


def analyze_weather(state: GraphState) -> GraphState:
    w = state.get("weather") or {}
    return {
        "temperature": float(w.get("T1H", 0)),
        "rain_flag": 1 if float(w.get("RN1", 0)) > 0 else 0,
        "wind_speed": float(w.get("WSD", 0)),
        "humidity": int(w.get("REH", 0))
    }


def run_dynamic_models(state: GraphState) -> GraphState:
    model_id = state.get("selected_model")
    if not model_id:
        return {}

    path = MODEL_DIR / model_id
    if not path.exists():
        return {}

    saved = joblib.load(path)
    model = saved["model"]
    features = saved["features"]
    encoders = saved["feature_encoders"]

    input_data = {}
    for f in features:
        v = state.get("extracted_values", {}).get(f)
        input_data[f] = v if v is not None else 0

    df = pd.DataFrame([input_data])
    for col, le in encoders.items():
        if col in df:
            v = str(df[col][0])
            df[col] = le.transform([v]) if v in le.classes_ else 0

    pred = float(model.predict(df)[0])

    return {
        "predictions": [
            PredictionResult(
                prediction=pred,
                inferred_params=input_data,
                model_id=model_id
            )
        ]
    }


def run_general_llm(state: GraphState) -> GraphState:

    prompt = f"""
    너는 veneta AI Agent 입니다.
    {state.get("input")}

    사용자에게 친절하게 응답하세요.
    """
    res = llm_chat.invoke(prompt)
    return {"response": res.content}


def run_model_llm(state: GraphState) -> GraphState:
    p = state["predictions"][0]
    prompt = f"""
    너는 veneta AI Agent 입니다.
    모델 {p.model_id} 결과: {p.prediction}
    조건: {p.inferred_params}
    질문: {state.get("input")}
    """
    res = llm_chat.invoke(prompt)
    return {"response": res.content}


# ===============================
# Graph
# ===============================

def route_input(state: GraphState) -> str:
    if state.get("action") == Action.USE_MODEL:
        return "model"
    if state.get("action") == Action.MODEL_CHAT:
        return "model_llm"
    return "llm"
def route_image(state: GraphState) -> str:
    if state.get("vision_status") == VisionStatus.ABNORMAL:
        return "explain"
    if state.get("vision_status") == VisionStatus.NORMAL:
        return "skip"
    return "skip"

builder = StateGraph(GraphState)

builder.add_node("stt", stt_node)
builder.add_node("vision", vision_node)
builder.add_node("analyze_prompt", analyze_prompt)
builder.add_node("explain_abnormal_node",explain_abnormal_node)
builder.add_node("weather", analyze_weather)
builder.add_node("model", run_dynamic_models)
builder.add_node("model_llm", run_model_llm)
builder.add_node("llm", run_general_llm)

builder.set_entry_point("stt")
builder.add_edge("stt", "vision")
builder.add_conditional_edges(
    "vision",
    route_image,
    {
        "explain": "explain_abnormal_node",
        "skip": "analyze_prompt"
    }
)

builder.add_conditional_edges(
    "analyze_prompt",
    route_input,
    {
        "model": "weather",
        "model_llm": "model_llm",
        "llm": "llm"
    }
)

builder.add_edge("weather", "model")
builder.set_finish_point("model")
builder.set_finish_point("llm")
builder.set_finish_point("model_llm")
builder.set_finish_point("explain_abnormal_node")

graph = builder.compile()

# ===============================
# FastAPI
# ===============================

app = FastAPI(title="Veneta AI Agent (STT + OCR)")


class ChatResponse(BaseModel):
    response: str


@app.post("/chat", response_model=ChatResponse)
async def chat(
    input: Optional[str] = Form(None),
    weather: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
):
    state: GraphState = {}
    print(f"\n--- [FastAPI 수신 로그] ---")
    print(f"텍스트 입력(input): {input}")
    print(f"날씨 데이터(weather): {weather}")
    print(f"음성 파일 여부: {voice_file is not None}")
    print(f"이미지 파일 여부: {image_file is not None}")
    if input:
        state["input"] = input

    if weather:
        state["weather"] = json.loads(weather)

    if voice_file:
        # 1. 파일 데이터 읽기
        content = await voice_file.read()
        print(f"[*] 수신된 음성 파일 크기: {len(content)} bytes")
        
        if len(content) == 0:
            print("[!] 에러: 수신된 파일이 비어 있습니다.")
            return ChatResponse(response="음성 데이터가 비어 있습니다.")

        # 2. 임시 파일 생성 및 강제 쓰기
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(content)
            tmp.flush()  # 버퍼 강제 비우기
            os.fsync(tmp.fileno()) # 디스크에 물리적 기록 보장
            state["voice_path"] = tmp.name
            print(f"[*] 임시 파일 생성 완료: {tmp.name}")

    if image_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as f:
            f.write(await image_file.read())
            state["image_path"] = f.name

    result = graph.invoke(state)
    return ChatResponse(response=result.get("response", "응답 없음"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)