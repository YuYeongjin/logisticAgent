import os
import tempfile
from typing import TypedDict, Optional, Dict, Any, Literal
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from langgraph.graph import StateGraph

import cv2
from ultralytics import YOLO
from faster_whisper import WhisperModel

# ==============================
# 모델 초기화
# ==============================

vision_model = YOLO("yolov8n.pt")

stt_model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)

# ==============================
# Global State
# ==============================

class GlobalState(TypedDict):

    input: Optional[str]

    voice_path: Optional[str]
    image_path: Optional[str]

    voice_text: Optional[str]
    image_analysis: Optional[Dict]

    observation: Dict

    process_result: Dict
    safety_result: Dict
    sop_result: Dict

    final_decision: str

# ==============================
# Session Store
# ==============================

SESSION_STORE: Dict[str, Dict] = {}

def get_state(session_id: str):

    if session_id not in SESSION_STORE:

        SESSION_STORE[session_id] = {
            "input": None,
            "voice_path": None,
            "image_path": None
        }

    return SESSION_STORE[session_id]

# ==============================
# INIT NODE
# ==============================

def init_node(state: GlobalState):

    print("INIT NODE")

    state.setdefault("voice_text", None)
    state.setdefault("image_analysis", None)
    state.setdefault("observation", {})

    state.setdefault("process_result", {})
    state.setdefault("safety_result", {})
    state.setdefault("sop_result", {})

    return state

# ==============================
# VOICE NODE
# ==============================

def voice_node(state: GlobalState):

    print("VOICE NODE")

    if not state.get("voice_path"):
        return state

    segments, _ = stt_model.transcribe(
        state["voice_path"],
        language="ko"
    )

    text = " ".join(seg.text for seg in segments)

    state["voice_text"] = text

    print("STT RESULT:", text)

    return state

# ==============================
# IMAGE NODE
# ==============================

def image_node(state: GlobalState):

    print("VISION NODE")

    if not state.get("image_path"):
        return state

    img = cv2.imread(state["image_path"])

    results = vision_model(img)

    detected_objects = []

    for r in results:

        for box in r.boxes:

            cls = int(box.cls)
            label = vision_model.names[cls]

            detected_objects.append(label)

    worker_present = "person" in detected_objects

    machine_present = any(x in detected_objects for x in [
        "knife", "scissors", "saw"
    ])

    if worker_present and machine_present:
        action = "cutting"
    else:
        action = "unknown"

    analysis = {

        "objects": detected_objects,
        "worker": worker_present,
        "machine": machine_present,
        "action": action

    }

    state["image_analysis"] = analysis

    print("IMAGE ANALYSIS:", analysis)

    return state

# ==============================
# MERGE INPUT
# ==============================

def merge_inputs(state: GlobalState):

    print("MERGE INPUT NODE")

    observation = {

        "text": state.get("input"),
        "voice": state.get("voice_text"),
        "vision": state.get("image_analysis")

    }

    state["observation"] = observation

    print("OBSERVATION:", observation)

    return state

# ==============================
# AGENTS
# ==============================

def process_agent(state: GlobalState):

    print("PROCESS AGENT")

    obs = state["observation"]

    anomaly = False

    if obs["vision"]:

        if obs["vision"]["action"] == "unknown":
            anomaly = True

    state["process_result"] = {

        "process": obs["vision"]["action"] if obs["vision"] else "unknown",
        "anomaly": anomaly

    }

    return state


def safety_agent(state: GlobalState):

    print("SAFETY AGENT")

    obs = state["observation"]

    risk = "LOW"

    if obs["vision"]:

        if obs["vision"]["worker"] and obs["vision"]["machine"]:
            risk = "MEDIUM"

    state["safety_result"] = {

        "risk_level": risk

    }

    return state


def sop_agent(state: GlobalState):

    print("SOP AGENT")

    obs = state["observation"]

    deviation = False

    if obs["vision"]:

        if obs["vision"]["action"] == "unknown":
            deviation = True

    state["sop_result"] = {

        "deviation": deviation

    }

    return state

# ==============================
# ORCHESTRATOR
# ==============================

def orchestrator(state: GlobalState):

    print("ORCHESTRATOR")

    safety = state["safety_result"]
    process = state["process_result"]
    sop = state["sop_result"]

    score = 0

    if safety["risk_level"] == "HIGH":
        score += 100

    if process["anomaly"]:
        score += 50

    if sop["deviation"]:
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

    print("FINAL DECISION:", decision)

    return state

# ==============================
# GRAPH
# ==============================

builder = StateGraph(GlobalState)

builder.add_node("init", init_node)

builder.add_node("voice", voice_node)
builder.add_node("image", image_node)

builder.add_node("merge", merge_inputs)

builder.add_node("process_agent", process_agent)
builder.add_node("safety_agent", safety_agent)
builder.add_node("sop_agent", sop_agent)

builder.add_node("orchestrator", orchestrator)

builder.set_entry_point("init")

builder.add_edge("init", "voice")
builder.add_edge("voice", "image")

builder.add_edge("image", "merge")

builder.add_edge("merge", "process_agent")
builder.add_edge("merge", "safety_agent")
builder.add_edge("merge", "sop_agent")

builder.add_edge("process_agent", "orchestrator")
builder.add_edge("safety_agent", "orchestrator")
builder.add_edge("sop_agent", "orchestrator")

graph = builder.compile()

# ==============================
# FastAPI
# ==============================

app = FastAPI()

class ChatResponse(BaseModel):
    response: str

@app.post("/sop", response_model=ChatResponse)

async def chat(

    input: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    session_id: str = Form(...)

):

    state = get_state(session_id)

    if input:
        state["input"] = input

    if voice_file:

        content = await voice_file.read()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:

            tmp.write(content)

            state["voice_path"] = tmp.name

    if image_file:

        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:

            tmp.write(await image_file.read())

            state["image_path"] = tmp.name

    result = graph.invoke(state)

    return ChatResponse(
        response=result["final_decision"]
    )

# ==============================
# RUN
# ==============================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)