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

from minio import Minio
import io
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
    image_name: Optional[str]
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
    log_level: Optional[str]

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
minio_client = Minio(
    "localhost:9000",
    access_key="admin",
    secret_key="Abcd1234",
    secure=False
)
BUCKET_NAME = "factory-minio"


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


# def vision_node(state: GraphState) -> GraphState:
#     if not state.get("image_path"):
#         return {}

#     if not BASE_IMAGE_PATH.exists():
#         print(f"[Vision][ERROR] Baseline image not found: {BASE_IMAGE_PATH}")
#         return {
#             "response": "기준 이미지가 설정되지 않았습니다."
#         }
#     current = Image.open(state["image_path"]).convert("L").resize((512, 512))
#     baseline = Image.open(BASE_IMAGE_PATH).convert("L").resize((512, 512))

#     current_np = np.array(current)
#     baseline_np = np.array(baseline)

#     score, _ = ssim(baseline_np, current_np, full=True)

#     diff = 1 - score  # 차이 점수 (0 ~ 1)

#     action = VisionStatus.ABNORMAL if diff > 0.15 else VisionStatus.NORMAL

#     print(f"[Vision] diff score: {diff:.4f}")

#     return {
#         "diff_score": diff,
#         "vision_status": action
#     }
import re
import numpy as np
import io
from PIL import Image
from skimage.metrics import structural_similarity as ssim

def vision_node(state: GraphState) -> GraphState:
    # 1. 입력된 최신 이미지 정보 가져오기
    current_key = state.get("image_path") # 예: cam_1_1771569517877.jpg
    print(f"[*] current_key : {current_key}")
    if not current_key:
        return {}
    print("image @@@@")
    # 2. 파일명에서 카메라 ID 추출 (cam_1, cam_2 등)
    match = re.match(r"(cam_\d+)", state.get("image_name"))
    if not match:
        print("???????")
        return {"response": "잘못된 파일 형식입니다."}
    print("t1")
    target_cam = match.group(1)
    
    # 3. MinIO에서 해당 카메라의 과거 파일 목록 필터링 및 정렬
    objects = list(minio_client.list_objects(BUCKET_NAME))
    all_files = [obj.object_name for obj in objects if obj.object_name.startswith(target_cam)]
    all_files.sort(reverse=True) # 최신순 정렬

    if len(all_files) < 3:
        return {"response": f"[{target_cam}] 분석을 위한 기초 데이터(최소 3장)가 부족합니다."}
    print("t2")
    try:
        # [데이터 로드]
        # A: 현재 이미지 (방금 들어온 것)
        curr_img = get_minio_image(all_files[0])
        # B: 직전 이미지 (단기 변화 체크)
        prev_img = get_minio_image(all_files[1])
        # C: 기준 이미지 (오늘의 첫 이미지 - 장기 변위 체크)
        anchor_img = get_minio_image(all_files[-1])

        # [다각도 수치 분석]
        # 1. 단기 변화율 (Short-term): 갑작스러운 물체 등장이나 카메라 흔들림 감지
        score_short, _ = ssim(prev_img, curr_img, full=True)
        diff_short = 1 - score_short

        # 2. 장기 변화율 (Long-term): 시간이 지나며 발생하는 미세한 구조적 변형 감지
        score_long, _ = ssim(anchor_img, curr_img, full=True)
        diff_long = 1 - score_long

        # 3. 최근 3장 일관성 (Consistency): 변화가 없어야 하는 상태인지 확인
        # 최근 이미지들이 서로 얼마나 비슷한지 평균을 냄
        consistency_scores = []
        for i in range(min(len(all_files)-1, 3)):
            img_a = get_minio_image(all_files[i])
            img_b = get_minio_image(all_files[i+1])
            consistency_scores.append(1 - ssim(img_a, img_b))
        avg_consistency = np.mean(consistency_scores)

        # [종합 판정 로직]
        status = VisionStatus.NORMAL
        log_level = "info"
        # 수치는 현장 상황에 맞게 튜닝 필요 (0.1~0.15 권장)
        if diff_short > 0.12 or diff_long > 0.15:
            status = VisionStatus.ABNORMAL
            log_level = "warn"
        if diff_short > 0.2 or diff_long > 0.5:
            log_level = "danger"
        print("t3")
        report = (
            f"--- {target_cam} 분석 보고서 ---\n"
            f"1. 단기 변화량: {diff_short:.4f} (직전 대비)\n"
            f"2. 장기 누적치: {diff_long:.4f} (최초 대비)\n"
            f"3. 최근 일관성: {avg_consistency:.4f}\n"
            f"결과: {'이상 감지' if status == VisionStatus.ABNORMAL else '정상 유지'}"
        )
        print(report)
        print(log_level)
        return {
            "diff_score": diff_short,
            "vision_status": status,
            "response": report,
            "log_level":log_level,
        }

    except Exception as e:
        return {"response": f"[{target_cam}] 분석 중 오류 발생: {str(e)}"}

def get_minio_image(name):
    obj = minio_client.get_object(BUCKET_NAME, name)
    return np.array(Image.open(io.BytesIO(obj.read())).convert("L").resize((512, 512)))

def explain_abnormal_node(state: GraphState) -> GraphState:
    print("explain_abnormal_node")

    prompt = f"""
    너는 veneta AI Agent 입니다.
    공장 설비 사진에서 기준 상태 대비 이상 변화가 감지되었습니다.

    변화 점수: {state['diff_score']:.3f}

    작업자가 이해할 수 있도록
    이유를 한줄로 짧게 한글로 설명하세요.
    """

    res = llm_chat.invoke(prompt)
    print(f"[Vision] res: {res}")
    return {
        "response": res.content,
        "log_level": state.get("log_level", "warn"),
        "diff_score": state.get("diff_score", 0.0)
    }


def analyze_prompt(state: GraphState) -> GraphState:
    print("analyze_prompt")
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
    print("run_general_llm")
    prompt = f"""
    너는 veneta AI Agent 입니다.
    {state.get("input")}

    사용자에게 친절하게 응답하세요.
    """
    res = llm_chat.invoke(prompt)
    return {"response": res.content}


def run_model_llm(state: GraphState) -> GraphState:
    print("run_model_llm")
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

class ImageResponse(BaseModel):
    response: str
    log_level: str
    diff_score: float

@app.post("/chat", response_model=ChatResponse)
async def chat(
    input: Optional[str] = Form(None),
    weather: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    image_name: Optional[str] = Form(None)
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
            state["image_name"] = image_name

    result = graph.invoke(state)
    final_response = result.get("response", "응답 없음")

    return ChatResponse(
        response=final_response,
    )


@app.post("/imageCheck", response_model=ImageResponse)
async def imageCheck(
    input: Optional[str] = Form(None),
    weather: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    image_name: Optional[str] = Form(None)
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
            state["image_name"] = image_name

    result = graph.invoke(state)
    final_response = result.get("response", "응답 없음")
    log_level = result.get("log_level", "info") # 기본값 info
    diff_score = result.get("diff_score",0.0)
    return ImageResponse(
        response=final_response,
        log_level=log_level,
        diff_score=float(diff_score)
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)