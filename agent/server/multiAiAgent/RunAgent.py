import os
import json
import joblib
from enum import Enum
from typing import TypedDict, Optional, Dict, Any, List,Literal
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


class GlobalState(TypedDict):
    input: Optional[str]
    image: Optional[str]
    audio: Optional[str]
    process_result: Dict
    safety_result: Dict
    sop_result: Dict
    final_decision: str


SESSION_STORE: Dict[str, Dict] = {}
def build_global_state(state: Dict[str, Any]) -> GlobalState:
    return {
        "input": state.get("input"),    
        "image": state.get("image_path"),
        "audio": state.get("voice_path"),
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
            "raw_inputs": {},
            "voice_status": "DONE",
            "image_status": "DONE"
        }
    return SESSION_STORE[session_id]

def run_process_agent(state: GlobalState):
    print("run_process_agent")
    result = process_agent_app.invoke({
        "input_data": {
            "input": state["input"],
            "image": state["image"],
            "audio": state["audio"],
        }
    })
    state["process_result"] = result
    return state


def run_safety_agent(state: GlobalState):
    print("run_safety_agent")
    result = safety_agent_app.invoke({
         "input_data": {
            "input": state["input"],
            "image": state["image"],
            "audio": state["audio"],
            "process_result": state["process_result"]
        }
    })
    state["safety_result"] = result
    return state

def run_sop_agent(state: GlobalState):
    print("run_sop_agent")
    result = sop_agent_app.invoke({
        "input_data": {
            "input": state["input"],
            "image": state["image"],
            "audio": state["audio"],
            "process_result": state["process_result"],
            "safety_result": state["safety_result"],
        }
    })
    state["sop_result"] = result
    return state
# ===============================
# Graph
# ===============================
def orchestrator_decide(state: GlobalState):
    if state["safety_result"]["recommendation"] == "EMERGENCY_STOP":
        state["final_decision"] = "STOP_IMMEDIATELY"
    elif state["process_result"]["recommendation"] == "STOP_PROCESS":
        state["final_decision"] = "PAUSE_PROCESS"
    else:
        state["final_decision"] = "CONTINUE"
    return state

builder = StateGraph(GlobalState)

builder.add_node("process_agent", run_process_agent)
builder.add_node("safety_agent", run_safety_agent)
builder.add_node("sop_agent", run_sop_agent)
builder.add_node("decide", orchestrator_decide)

builder.set_entry_point("process_agent")
builder.add_edge("process_agent", "safety_agent")
builder.add_edge("safety_agent", "sop_agent")
builder.add_edge("sop_agent", "decide")


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
    # state: GraphState = {}
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