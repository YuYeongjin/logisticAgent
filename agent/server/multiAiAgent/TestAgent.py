import os
import tempfile
from typing import TypedDict, Optional, Dict, Any, Literal
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from langgraph.graph import StateGraph

import cv2
from ultralytics import YOLO
from faster_whisper import WhisperModel

from agents.ProcessAgent import run_process_agent
from agents.SopMultiAgent import run_sop_agent
from agents.SafeAgent import run_safety_agent
from agents.SopGeneratorAgent import run_sop_create_agent
from agents.SopQuestionAgent import generate_sop_questions
from langchain_ollama import ChatOllama


# ===============================
# LLM
# ===============================

llm_chat = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url="http://localhost:11434"
)

# ==============================
# 모델 초기화
# ==============================

# ============================
# 이미지 관련
# ============================
import json
import numpy as np
# object detection
detector = YOLO("yolov8m.pt")

# segmentation
segmentor = YOLO("yolov8m-seg.pt")

# pose detection
pose_model = YOLO("yolov8m-pose.pt")

# PPE detection
ppe_model = YOLO("yolov8m.pt") #YOLO("ppe-detection.pt")

def preprocess_image(path):

    img = cv2.imread(path)

    if img is None:
        raise Exception("image load fail")

    img = cv2.resize(img, (1280, 720))

    return img

def detect_objects(img):

    results = detector(img)

    objects = []

    for r in results:

        for box in r.boxes:

            conf = float(box.conf)

            if conf < 0.4:
                continue

            cls = int(box.cls)
            label = detector.names[cls]

            x1, y1, x2, y2 = box.xyxy[0].tolist()

            obj = {

                "label": label,
                "confidence": round(conf, 3),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
                "center": [
                    int((x1 + x2) / 2),
                    int((y1 + y2) / 2)
                ]
            }

            objects.append(obj)

    return objects
def detect_ppe(img):

    results = ppe_model(img)

    ppe_items = []

    for r in results:

        for box in r.boxes:

            conf = float(box.conf)

            if conf < 0.4:
                continue

            cls = int(box.cls)
            label = ppe_model.names[cls]

            x1,y1,x2,y2 = box.xyxy[0].tolist()

            ppe_items.append({

                "label": label,
                "confidence": round(conf,3),
                "bbox":[int(x1),int(y1),int(x2),int(y2)]

            })

    return ppe_items
def check_ppe_compliance(objects, poses, ppe_items):

    result = {

        "helmet": False,
        "gloves": False,
        "vest": False

    }

    if len(poses) == 0:
        return result

    pose = poses[0]["keypoints"]

    head = pose[0]
    left_hand = pose[9]
    right_hand = pose[10]

    for p in ppe_items:

        x1,y1,x2,y2 = p["bbox"]

        cx = (x1+x2)/2
        cy = (y1+y2)/2

        if p["label"] == "helmet":

            if abs(cx - head[0]) < 100 and abs(cy - head[1]) < 100:
                result["helmet"] = True

        if p["label"] == "gloves":

            if abs(cx - left_hand[0]) < 120 or abs(cx - right_hand[0]) < 120:
                result["gloves"] = True

        if p["label"] == "safety_vest":

            result["vest"] = True

    return result
# ============================
# Segmentation
# ============================

def segment_objects(img):

    results = segmentor(img)

    segments = []

    for r in results:

        if r.masks is None:
            continue

        for i, mask in enumerate(r.masks.xy):

            cls = int(r.boxes.cls[i])
            label = segmentor.names[cls]

            segments.append({

                "label": label,
                "polygon": mask.tolist()

            })

    return segments


# ============================
# Pose Detection
# ============================

def detect_pose(img):

    results = pose_model(img)

    poses = []

    for r in results:

        if r.keypoints is None:
            continue

        for k in r.keypoints.xy:

            points = k.tolist()

            poses.append({

                "keypoints": points

            })

    return poses


# ============================
# Object Relationship
# ============================

def analyze_relations(objects):

    relations = []

    for i in range(len(objects)):

        for j in range(i+1, len(objects)):

            o1 = objects[i]
            o2 = objects[j]

            x1,y1 = o1["center"]
            x2,y2 = o2["center"]

            dist = np.sqrt((x1-x2)**2 + (y1-y2)**2)

            if dist < 150:

                relations.append({

                    "object1": o1["label"],
                    "object2": o2["label"],
                    "distance": int(dist),
                    "relation": "near"

                })

    return relations


# ============================
# Scene Graph
# ============================

def build_scene_graph(objects, relations):

    graph = {

        "nodes": objects,
        "edges": relations

    }

    return graph


# ============================
# LLM Scene Understanding
# ============================

def scene_reasoning(objects, segments, poses, relations):

    prompt = f"""
    다음은 이미지 분석 데이터이다.

    objects:
    {json.dumps(objects, ensure_ascii=False)}

    segmentation:
    {json.dumps(segments, ensure_ascii=False)}

    human_pose:
    {json.dumps(poses, ensure_ascii=False)}

    relations:
    {json.dumps(relations, ensure_ascii=False)}

    이 데이터를 기반으로 장면을 분석하라.

    반드시 JSON 출력

    {{
        "scene": "",
        "human_activity": "",
        "tools": [],
        "environment": "",
        "risk": ""
    }}
    """

    res = llm_chat.invoke(prompt)

    try:
        return json.loads(res.content)

    except:
        return {"scene": "unknown"}

# ============================


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
    sop_validation_result: Dict
    sop_generation_result: Dict
    

    sop_questions: Optional[list]      # 질문 리스트
    current_question_index: int        # 현재 몇 번째 질문인지
    user_answers: Dict[str, str]       # 사용자의 답변들
    is_completed: bool                 # 대화 종료 여부

    final_decision: str
    final_score: str
# ==============================
# Session Store
# ==============================

SESSION_STORE: Dict[str, Dict] = {}

def get_state(session_id: str):

    if session_id not in SESSION_STORE:

        SESSION_STORE[session_id] = {
            "input": None,
            "voice_path": None,
            "image_path": None,

            "voice_text": None,
            "image_analysis": None,

            "observation": {},

            "process_result": {},
            "safety_result": {},
            "sop_validation_result": {},
            "sop_generation_result": {},

            "sop_questions": None,
            "user_answers": {},
            "current_question_index":0,
            "is_completed": False,

            "final_decision": None,
            "final_score": 0
        }

    return SESSION_STORE[session_id]

# ==============================
# INIT NODE
# ==============================

def init_node(state: GlobalState):

    state.setdefault("voice_text", None)
    state.setdefault("image_analysis", None)
    state.setdefault("observation", {})
    state.setdefault("process_result", {})
    state.setdefault("safety_result", {})
    state.setdefault("sop_validation_result", {})
    state.setdefault("sop_generation_result", {})
    # 질문 관련 초기화 (기존 데이터 유지 위해 setdefault)
    state.setdefault("sop_questions", None)
    state.setdefault("current_question_index", 0)
    state.setdefault("user_answers", {})
    state.setdefault("is_completed", False)
    return state

# ==============================
# VOICE NODE
# ==============================

def voice_node(state: GlobalState):

    # print("VOICE NODE")

    if not state.get("voice_path"):
        return state

    segments, _ = stt_model.transcribe(
        state["voice_path"],
        language="ko"
    )

    text = " ".join(seg.text for seg in segments)

    state["voice_text"] = text

    # print("STT RESULT:", text)

    return state

# ==============================
# IMAGE NODE
# ==============================

def image_node(state: GlobalState):

    # print("VISION PIPELINE START")
    if not state.get("image_path"):
        return state
    img = preprocess_image(state["image_path"])
    objects = detect_objects(img)
    segments = segment_objects(img)
    poses = detect_pose(img)
    ppe_items = detect_ppe(img)
    relations = analyze_relations(objects)
    graph = build_scene_graph(objects, relations)
    ppe_status = check_ppe_compliance(objects, poses, ppe_items)
    scene = scene_reasoning(
        objects,
        segments,
        poses,
        relations
    )
    state["image_analysis"] = {
        "objects": objects,
        "segments": segments,
        "poses": poses,
        "ppe_items": ppe_items,
        "ppe_status": ppe_status,
        "relations": relations,
        "scene_graph": graph,
        "scene": scene
    }
    return state

# ==============================
# MERGE INPUT
# ==============================

def merge_inputs(state: GlobalState):

    # print("MERGE INPUT NODE")

    observation = {

        "text": state.get("input"),
        "voice": state.get("voice_text"),
        "vision": state.get("image_analysis")

    }

    state["observation"] = observation

    # print("OBSERVATION:", observation)
    if state.get("input"):
        state["conversation_history"].append({
            "role": "user",
            "content": state["input"]
        })

    return state

# ==============================
# AGENTS
# ==============================

def process_agent(state: GlobalState):

    # print("PROCESS AGENT")
    if state.get("sop_questions"):
        return {}
    obs = state["observation"]
    result = run_process_agent(obs)
    # print(f"process result :{result}")

    return { "process_result": result}


def safety_agent(state: GlobalState):

    # print("SAFETY AGENT")
    if state.get("sop_questions"):
        return {}
    obs = state["observation"]
    result = run_safety_agent(obs)
    # print(f"safety result :{result}")

    return {"safety_result": result}


def sop_agent(state: GlobalState):
    # print("SOP AGENT")
    obs = state["observation"]
    result = run_sop_agent(obs)
    # print(f"sop_validation_result :{result}")

    return {"sop_validation_result": result}

def sop_generator_agent(state: GlobalState):
    if state.get("sop_questions"):
        return {}
    # print("SOP GENERATOR AGENT (New Process Detection)")
    obs = state["observation"]
    
    result = run_sop_create_agent(obs) 
    return {"sop_generation_result": result}
# ==============================
# ORCHESTRATOR
# ==============================
def sop_question_agent(state: GlobalState):

    if state.get("sop_questions") is None:
        state = generate_sop_questions(state)

    questions = state.get("sop_questions", [])

    # 모든 질문이 답변되었는지 확인
    unanswered = [q for q in questions if not q.get("answer")]

    if len(unanswered) > 0:

        state["final_decision"] = {
            "type": "sop_confirm_required",
            "questions": questions
        }

    else:

        state["is_completed"] = True
        state["final_decision"] = "SOP 생성이 완료되었습니다."

    return state


def orchestrator(state: GlobalState):

    safety = state.get("safety_result")
    process = state.get("process_result")

    sop = state.get("sop_generation_result") or state.get("sop_validation_result")

    questions = state.get("sop_questions")
    print(f"safety : {safety}")
    print(f"process : {process}")
    print(f"sop : {sop}")
    print(f"questions : {questions}")
    score = 0  

    if safety and safety.get("risk_level") == "HIGH":
        score += 100

    if process and process.get("anomaly"):
        score += 50

    if sop and sop.get("deviation"):
        score += 30

    if questions and not state.get("is_completed"):

        state["final_decision"] = {
            "type": "sop_confirm_required",
            "questions": questions
        }

    else:

        if score >= 100:
            decision = "danger"
        elif score >= 50:
            decision = "warn"
        elif score >= 30:
            decision = "warn"
        else:
            decision = "info"

        state["final_decision"] = decision

    state["final_score"] = score

    return state

def route_after_process(state: GlobalState):
    if state["process_result"].get("anomaly") == True:
        # DB에 없는 공정이면 생성 에이전트로 이동
        return "sop_generator_agent"
    else:
        # 있는 공정이면 기존 검증 에이전트로 이동
        return "sop_agent"
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
builder.add_node("sop_generator_agent", sop_generator_agent)
builder.add_node("sop_question_agent", sop_question_agent)
builder.add_node("orchestrator", orchestrator)

builder.set_entry_point("init")

builder.add_edge("init", "voice")
builder.add_edge("voice", "image")

builder.add_edge("image", "merge")

builder.add_edge("merge", "safety_agent")
builder.add_edge("safety_agent", "process_agent")

builder.add_conditional_edges(
    "process_agent",
    route_after_process,
    {
        "sop_generator_agent": "sop_generator_agent",
        "sop_agent": "sop_agent"
    }
)

builder.add_edge("sop_generator_agent", "sop_question_agent")
builder.add_edge("sop_question_agent", "orchestrator")
builder.add_edge("sop_agent", "orchestrator")
builder.set_finish_point("orchestrator")
graph = builder.compile()

# ==============================
# FastAPI
# ==============================

app = FastAPI()

class ChatResponse(BaseModel):
    response: str
    log_level: str
    diff_score : int
@app.post("/sop", response_model=ChatResponse)
async def chat(
    input: Optional[str] = Form(None),
    voice_file: Optional[UploadFile] = File(None),
    image_file: Optional[UploadFile] = File(None),
    session_id: str = Form(...)
):

    state = get_state(session_id)

    if voice_file:
        content = await voice_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(content)
            state["voice_path"] = tmp.name

    if image_file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(await image_file.read())
            state["image_path"] = tmp.name

    if input:
        state["input"] = input

    # result = graph.invoke(state)

    if state.get("sop_questions") and input:
        # 현재 답변이 필요한 질문 인덱스 찾기
        current_idx = state.get("current_question_index", 0)
        questions = state["sop_questions"]
        
        if current_idx < len(questions):
            questions[current_idx]["answer"] = input
            state["current_question_index"] = current_idx + 1
            
        if state["current_question_index"] >= len(questions):
            state["is_completed"] = True

    print(f"start state :: {state}")

    # ★ 중요: 호출 후 반환된 값을 다시 세션에 저장
    updated_state = graph.invoke(state)
    SESSION_STORE[session_id] = updated_state

    final_decision = updated_state.get("final_decision")

    decision = updated_state.get("final_decision", "info")
    score = updated_state.get("final_score", 0)

    if decision == 'danger': level = 'danger'
    elif decision == 'warn': level = 'warn'
    elif decision == 'info': level = 'info'
    else: level = 'notice'

    if isinstance(decision, dict):

        return ChatResponse(
            response=json.dumps(decision, ensure_ascii=False),
            log_level="notice",
            diff_score=0
        )

    return ChatResponse(
        response=str(decision),
        log_level=level,
        diff_score=score
    )

# ==============================
# RUN
# ==============================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8006)