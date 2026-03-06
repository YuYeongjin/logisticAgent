import os
import json
import joblib
from enum import Enum
from typing import TypedDict, Optional, Dict, Any, List,Literal,Annotated
import operator
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from langgraph.graph import StateGraph

# ===============================
# STT / OCR
# ===============================
from faster_whisper import WhisperModel
from PIL import Image
import tempfile

import numpy as np
from skimage.metrics import structural_similarity as ssim

# ===============================
# 이미지 관련 
# ===============================
from minio import Minio
import io
import re
import numpy as np
import io
from PIL import Image
from skimage.metrics import structural_similarity as ssim

import psycopg2
from psycopg2.extras import RealDictCursor


# ===============================
# agent import
# ===============================
from agents.SopMultiAgent import sop_agent_app
from agents.SafeAgent import safety_agent_app
from agents.ProcessAgent import process_agent_app

# ===============================
# 이미지 관련
# ===============================
from minio import Minio
import io
import re
import numpy as np
import io
from PIL import Image
from skimage.metrics import structural_similarity as ssim

stt_model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

class GlobalState(TypedDict):

    input: Optional[str]

    voice_path: Optional[str]
    image_path: Optional[str]
    image_name: Optional[str]

    voice_status: Literal["PENDING", "DONE"]
    image_status: Literal["PENDING", "DONE"]

    voice_text: Optional[str]
    image_analysis: Optional[Dict]

    observation: Dict

    process_result: Dict
    safety_result: Dict
    sop_result: Dict

    final_decision: str


SESSION_STORE: Dict[str, Dict] = {}

minio_client = Minio(
    "localhost:9000",
    access_key="admin",
    secret_key="Abcd1234",
    secure=False
)
BUCKET_NAME = "factory-minio"

def build_global_state(state: Dict[str, Any]) -> GlobalState:
    return {
        "input": state.get("input"),    
        "image_path": state.get("image_path"),
        "image_name": state.get("image_name"),
        "image_analysis": state.get("image_analysis"),
        "image_status": state.get("image_status","DONE"),
        "voice_status": state.get("voice_status", "DONE"),
        "voice_path": state.get("voice_path"),
        "process_result": {},
        "safety_result": {},
        "sop_result": {},
        "final_decision": ""
    }

def get_state(session_id: str) -> Dict[str, Any]:
    """ 세션별 상태를 가져오거나 초기화"""
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {
            "text_history": [],
            "voice_history": [],
            "image_history": [],
            "voice_path": {},
            "voice_status": "PENDING",
            "image_status": "PENDING"
        }
    return SESSION_STORE[session_id]


def init_node(state: GlobalState) -> GlobalState:
    print("init node @@")
    state.setdefault("raw_inputs", {})
    state.setdefault("missing_fields", [])
    return state


def voice_node(state: GlobalState):

    print("VOICE NODE")

    if not state.get("voice_path"):
        state["voice_status"] = "DONE"
        return state

    segments, _ = stt_model.transcribe(
        state["voice_path"],
        language="ko"
    )

    text = " ".join(seg.text for seg in segments)

    state["voice_text"] = text
    state["voice_status"] = "DONE"

    print("VOICE TEXT:", text)

    return state

import cv2
from ultralytics import YOLO

model = YOLO("yolov8n.pt")


def image_node(state: GlobalState) -> GlobalState:

    print("VISION AGENT START")

    image_path = state.get("image_path")

    if image_path is None:
        state["image_status"] = "DONE"
        state["image_analysis"] = None
        return state

    img = cv2.imread(image_path)

    results = model(img)

    detected_objects = []

    for r in results:
        for box in r.boxes:

            cls = int(box.cls)
            label = model.names[cls]

            detected_objects.append(label)

    worker_present = "person" in detected_objects

    machine_present = any(x in detected_objects for x in [
        "knife", "scissors", "saw"
    ])

    ppe_status = {
        "helmet": "helmet" in detected_objects,
        "gloves": "gloves" in detected_objects
    }

    if worker_present and machine_present:
        action = "cutting"
    else:
        action = "unknown"

    analysis = {
        "objects": detected_objects,
        "worker": worker_present,
        "machine": machine_present,
        "action": action,
        "ppe": ppe_status
    }

    print("IMAGE ANALYSIS:", analysis)
    print(f"IMAGE ANALYSIS: {analysis}")
    state["image_analysis"] = analysis
    state["image_status"] = "DONE"

    return state

def get_minio_image(name):
    obj = minio_client.get_object(BUCKET_NAME, name)
    return np.array(Image.open(io.BytesIO(obj.read())).convert("L").resize((512, 512)))

def process_node(state: GlobalState):
    print("BUILD OBSERVATION")
    observation = {
        "text": state.get("input"),
        "voice": state.get("voice_text"),
        "vision": state.get("image_analysis")
    }

    return {"observation" : observation}

def run_process_agent(state: GlobalState):
    print("run_process_agent")
    result = process_agent_app.invoke({
        "observation": state["observation"]
    })
    return {"process_result": result}


def run_safety_agent(state: GlobalState):
    print("run_safety_agent")
    result = safety_agent_app.invoke({
        "observation": state["observation"]
    })
    return {"safety_result": result}


def run_sop_agent(state: GlobalState):
    print("run_sop_agent")
    result = sop_agent_app.invoke({
        "observation": state["observation"]
    })
    return {"sop_result": result}
# ===============================
# Graph
# ===============================
def orchestrator_decide(state: GlobalState):
    print("@@@@ orchestrator_decide @@@@")
    safety = state.get("safety_result", {})
    process = state.get("process_result", {})
    sop = state.get("sop_result", {})

    score = 0

    if safety.get("risk_level") == "HIGH":
        score += 100

    if process.get("anomaly"):
        score += 50

    if sop.get("deviation"):
        score += 30

    if score >= 100:
        decision = "STOP_IMMEDIATELY"
    elif score >= 50:
        decision = "PAUSE_PROCESS"
    elif score >= 30:
        decision = "CHECK_SOP"
    else:
        decision = "CONTINUE"

    state["final_decision"] = decision

    return state
def route_init(state: GlobalState):
    if state.get("voice_path") and state["voice_status"] == "PENDING":
        return "voice_node"
    if state.get("image_path") and state["image_status"] == "PENDING":
        return "image_node"
    return "process_node"

builder = StateGraph(GlobalState)
builder.add_node("init",init_node)
builder.add_node("voice_node", voice_node)
builder.add_node("image_node", image_node)
builder.add_node("process_node", process_node)

builder.add_node("process_agent", run_process_agent)
builder.add_node("safety_agent", run_safety_agent)
builder.add_node("sop_agent", run_sop_agent)
builder.add_node("decide", orchestrator_decide)

builder.set_entry_point("init")
builder.add_edge("process_node", "process_agent")
builder.add_edge("process_node", "safety_agent")
builder.add_edge("process_node", "sop_agent")
builder.add_edge("process_agent", "decide")
builder.add_edge("safety_agent", "decide")
builder.add_edge("sop_agent", "decide")

builder.add_conditional_edges(
    "init",
    route_init,
    {
        "voice_node": "voice_node",
        "image_node": "image_node",
        "process_node": "process_node"
    }
)
builder.add_edge("voice_node", "init")
builder.add_edge("image_node", "init")

graph = builder.compile()
# ===============================
# FastAPI
# ===============================

app = FastAPI(title="Veneta AI Agent (STT + OCR)")



class ChatResponse(BaseModel):
    response: str


@app.post("/sop", response_model=ChatResponse)
async def chat(
    input: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    image_name: Optional[str] = Form(None),
    session_id: str = Form(...)
):
    state = get_state(session_id)
    state.setdefault("text_history", [])
    state.setdefault("voice_history", [])
    state.setdefault("image_history", [])
    print(f"\n--- [FastAPI 수신 로그] ---")
    print(f"텍스트 입력(input): {input}")
    print(f"음성 파일 여부: {voice_file is not None}")
    print(f"이미지 파일 여부: {image_file is not None}")

    if input:
        state["text_history"].append(input)
        state["input"] = input

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
    
    global_state = build_global_state(state)

    result_state: GlobalState = graph.invoke(global_state)
    print(f"result_state : {result_state}")
    final_response = result_state.get("final_decision", "응답 없음")
    state.update(result_state)
    return ChatResponse(
        response=final_response,
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)