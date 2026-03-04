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
# 이미지 관련
# ===============================
from minio import Minio
import io
import re
import numpy as np
import io
from PIL import Image
from skimage.metrics import structural_similarity as ssim


# ===============================
# Database
# ===============================
import psycopg2
from psycopg2.extras import RealDictCursor

# =========================
# 앱 / 전역 세션 스토어
# =========================

# 세션별 상태 저장소
SESSION_STORE: Dict[str, Dict] = {}


def get_state(session_id: str) -> Dict[str, Any]:
    """ 세션별 상태를 가져오거나 초기화"""
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {
            "text_history": [],
            "voice_history": [],
            "image_history": [],
            "sop_value": WorkState(), # 초기 빈 공정 객체 생성
            "raw_inputs": {},
            "voice_status": "DONE",
            "image_status": "DONE"
        }
    return SESSION_STORE[session_id]

# ===============================
# Action / State
# ===============================

class Action(str, Enum):
    GENERAL_CHAT = "GENERAL_CHAT"
    USE_MODEL = "USE_MODEL"
    MODEL_CHAT = "MODEL_CHAT"
    RETRIEVE = "RETRIEVE"

class WorkState(BaseModel):
    """
    공정(작업) 구조화 모델
    """
    name: Optional[str] = None        # 공종 이름
    purpose: Optional[str] = None     # 작업 목적
    input: Optional[str] = None       # 원재료 / 입력물
    work: Optional[str] = None        # 주 작업 내용
    condition: Optional[str | Dict[str, Any]] = None  # 작업 조건 (온도, 시간 등)

class GraphState(TypedDict, total=False):
    input: str

    text_history: List[str]
    voice_history: List[str]    
    image_history: List[Dict]

    voice_path: Optional[str]
    image_path: Optional[str]
    image_name: Optional[str]

    action: Action
    selected_model: Optional[str]
    extracted_values: Dict[str, Any]

    sop_value: Optional[WorkState]
    sop_valid: bool
    # 중간 결과
    raw_inputs: Dict[str, Any]

    voice_status: Literal["PENDING", "DONE"]
    image_status: Literal["PENDING", "DONE"]

    missing_fields: List[str]
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
# 데이터베이스 접속정보 
# ===============================
DB_CONFIG = {
    "host": "localhost",
    "database": "factory_db",
    "user": "admin",
    "password": "Abcd1234",
    "port": "5432"
}
def save_work_process_to_db(sop: WorkState):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO tbl_sop
        (name, purpose, input, work, condition)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        sop.name,
        sop.purpose,
        sop.input,
        sop.work,
        sop.condition
    ))

    conn.commit()
    cur.close()
    conn.close()
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

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



# ===============================
# Nodes
# ===============================
def init_node(state: GraphState) -> GraphState:
    print("init node @@")
    state.setdefault("raw_inputs", {})
    state.setdefault("missing_fields", [])
    return state

def voice_node(state: GraphState) -> GraphState:
    print("voice_node @@")
    if not state.get("voice_path"):
        state["voice_status"] = "DONE"
        return state

    print("voice @@@@")
    segments, _ = stt_model.transcribe(
        state["voice_path"],
        language="ko"
    )

    text = " ".join(seg.text for seg in segments)
    state["voice_history"].append(text)
    state["raw_inputs"]["voice_text"] = text
    state["input"] = text
    state["voice_status"] = "DONE"

    return state

def image_node(state: GraphState) -> GraphState:
    print("image_node @@")
    current_key = state.get("image_path") 
    print(f"[*] current_key : {current_key}")
    if not current_key:
        state["image_status"] = "DONE"
        return state
    print("image @@@@")
    # 2. 파일명에서 카메라 ID 추출 (cam_1, cam_2 등)
    match = re.match(r"(cam_\d+)", state.get("image_name"))
    if not match:
        state["response"] = "잘못된 파일 형식입니다."
        state["image_status"] = "DONE"
        return state
    print("t1")
    target_cam = match.group(1)
    
    state["raw_inputs"]["image_cam"] = target_cam
    state["image_status"] = "DONE"
    state["image_history"].append({
        "name": state.get("image_name"),
        "cam": target_cam
    })
    return state

def get_minio_image(name):
    obj = minio_client.get_object(BUCKET_NAME, name)
    return np.array(Image.open(io.BytesIO(obj.read())).convert("L").resize((512, 512)))

def analyze_prompt(state: GraphState) -> GraphState:
    print("analyze_prompt")
    user_input = state.get("input", "")
    
    prompt = f"""
    사용자의 입력이 다음 중 어디에 해당하는지 분류하라.
    1. CREATE: 새로운 공정/레시피를 만듦
    2. RETRIEVE: 기존에 저장된 레시피/공정을 조회하거나 보여달라고 함
    3. GENERAL: 그 외 일반적인 대화
    
    사용자 입력: "{user_input}"
    - 출력은 반드시 CREATE, RETRIEVE, GENERAL 중 하나여야 한다.
    - 다른 단어, 문장, 설명 없이 답해라
    - 출력 예시:
    RETRIEVE or CREATE or GENERAL
    """
    res = llm_chat.invoke(prompt)
    print(f"res :: {res.content}")
    raw = res.content.upper()
    intent = res.content.strip().upper()
    print(f"intent :: {raw}")
    if intent == "CREATE": state["action"] = Action.USE_MODEL
    elif intent == "RETRIEVE": state["action"] = Action.RETRIEVE
    else: state["action"] = Action.GENERAL_CHAT

    return state



def make_sop_node(state: GraphState) -> GraphState:
    """
    사용자 입력(텍스트 + 음성 + 이미지 분석 결과)을 바탕으로
    공정(WorkState)을 구조화하는 노드
    """
    print("make_sop_node")

    prev_work = state.get("sop_value") or WorkState()
    
    history_block = f"""
    [누적 히스토리]
    텍스트: {", ".join(state.get("text_history", []))}
    음성: {", ".join(state.get("voice_history", []))}
    """
    print(f"history_block : {history_block}")
    prompt = f"""
    너는 veneta AI 제조 공정 설계 어시스턴트다.

    아래는 사용자와 지금까지의 누적 대화 및 입력 기록이다.
    이 기록을 기준으로 공정 정보를 점진적으로 완성하라.
    기존 데이터: {prev_work.model_dump_json()}
    {history_block}

    [공정 State 필드 설명]
    - name: 공종 또는 작업 이름
    - purpose: 해당 작업의 목적
    - input: 사용되는 원재료 또는 입력물
    - work: 실제 수행하는 주 작업
    - condition: 작업 시 중요한 조건(온도, 시간, 기준 등)

    규칙:
    - 추측하지 말고, 명확한 정보만 채워라
    - 정보가 없으면 null 로 남겨라
    - 반드시 JSON 형식으로만 출력하라

    JSON 형식:
    {{
      "name": "...",
      "purpose": "...",
      "input": "...",
      "work": "...",
      "condition": "..."
    }}

    [사용자 텍스트 입력]
    {state.get("input")}

    [음성/이미지 기반 보조 정보]
    {json.dumps(state.get("raw_inputs", {}), ensure_ascii=False)}
    """

    res = llm_json.invoke(prompt)

    try:
        data = json.loads(res.content)
        print(f"data :: {data}")
        new_work = WorkState(**data)

        prev_work: WorkState = state.get("sop_value") or WorkState()

        merged = prev_work.model_copy(update={
            k: v for k, v in new_work.model_dump().items()
            if v is not None
        })

        state["sop_value"] = merged
        return state

    except Exception as e:
        print(f"[analyze_prompt error] {e}")
        # 실패 시에도 그래프는 계속 진행 가능하게
        state["action"] = Action.GENERAL_CHAT
        state["sop_value"] = state.get("sop_value") or WorkState()
        return state

def check_sop(state: GraphState) -> GraphState:
    print("check_sop")
    sop: WorkState | None = state.get("sop_value")

    if sop is None:
        state["missing_fields"] = []
        state["sop_valid"] = False
        return state

    required_fields = ["name", "purpose", "input", "work", "condition"]

    missing = [
        field for field in required_fields
        if getattr(sop, field) is None
    ]

    state["missing_fields"] = missing

    if not missing:
        state["sop_valid"] = True
    else:
        state["sop_valid"] = False

    return state



def run_dynamic_models(state: GraphState) -> GraphState:
    """
    검증된 공정 정보를 기반으로
    - 공정 데이터 저장
    - 동적 모델 / 시뮬레이션 / Rule 실행
    """
    print("run_dynamic_models")

    sop_value: WorkState = state["sop_value"]
    print(f"sop_value : {sop_value}")
    # 방어 로직 (이론상 여기까지 오면 True)
    if not state.get("sop_valid") or not sop_value:
        return state 

    # 1. 공정 DB 저장 (예시)
    try:
        save_work_process_to_db(sop_value)
    except Exception as e:
        print(f"[DB save error] {e}")
        # DB 실패해도 사용자 응답은 계속
    
    # 2. 공정 기반 모델 실행
    model_prompt = f"""
    저장된 공정 정보:
    {sop_value.model_dump()}
    해당 공정을 통해 어떤 것을 진행할 것인지 간단히 응답할 것.
    """

    res = llm_chat.invoke(model_prompt)
    # run_dynamic_models 마지막
    state["text_history"] = []
    state["voice_history"] = []
    state["image_history"] = []
    state["sop_value"] = None
    return {
        "response": res.content,
        "sop_value": WorkState()
    }

def check_missing_llm(state: GraphState) -> GraphState:
    print("check_missing")

    missing = state.get("missing_fields", [])

    prompt = f"""
    너는 veneta ai agent로 제조 공정을 대화로 완성한다.

    현재 공정은 일부만 작성되었고,
    아래 항목들이 아직 비어 있다:

    {", ".join(missing)}

    규칙:
    - 설명하지 말고 질문만 해라
    - 항목별 정의를 말하지 마라
    - 사용자에게 정보를 요청하는 문장만 생성해라
    - 한글로 자연스럽게 질문해라

    예시:
    "사용되는 원재료는 무엇인가요?"
    "작업은 어떻게 진행되나요?"
    "작업을 위한 특별한 조건이 있나요?"

    이제 질문을 생성해라.
    """

    res = llm_chat.invoke(prompt)
    return {"response": res.content}

def retrieve_node(state: GraphState) -> GraphState:
    print("retrieve_node (Auto-Query) @@")
    user_input = state.get("input", "")

    query_prompt = f"""
    너는 PostgreSQL 전문가다. 사용자의 질문을 바탕으로 'tbl_sop' 테이블을 조회하는 SELECT 문을 생성하라.

    [DB 정보]
    - 테이블: tbl_sop
    - 컬럼: name, purpose, input, work, condition

    [필수 규칙]
    1. PostgreSQL 문법을 준수하라. 문자열 값은 반드시 홑따옴표(')를 사용하라 (예: LIKE '%값%'). 큰따옴표(")는 절대 사용하지 마라.
    2. 사용자가 '레시피 조회해줘'와 같이 전체 조회를 요청하면 WHERE 절 없이 전체를 조회하라.
    3. 특정 키워드(예: 닭고기)가 언급된 경우에만 해당 컬럼에 대해 LIKE 조회를 수행하라.
    4. 출력은 오직 SQL 문장만 하고, 설명은 생략하라.

    [사용자 질문]
    "{user_input}"
    """
    
    sql_res = llm_chat.invoke(query_prompt)
    generated_sql = sql_res.content.strip().replace("```sql", "").replace("```", "")
    
    print(f"[*] 생성된 쿼리: {generated_sql}")

    # 2. 데이터베이스 실행
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 보안 주의: 실제 서비스에서는 파라미터 바인딩이나 SQL 인젝션 방지 로직이 추가되어야 합니다.
        cur.execute(generated_sql)
        rows = cur.fetchall()
        
        if rows:
            recipe_list = "\n".join([
                f"📍 {r['name']}\n   - 작업: {r['work']}\n   - 재료: {r['input']}\n   - 조건: {r['condition']}" 
                for r in rows
            ])
            response = f"'{user_input}'에 대한 검색 결과입니다:\n\n{recipe_list}"
        else:
            response = f"'{user_input}'와 관련된 레시피를 찾을 수 없습니다."
            
        cur.close()
        conn.close()
    except Exception as e:
        response = f"조회 중 오류가 발생했습니다. (쿼리 오류 가능성)\n입력: {user_input}"
        print(f"[DB Error] {e}")
        
    return {"response": response}


def general_llm(state: GraphState) -> GraphState:
    print("@@@@@@@@general_llm@@@@@@@@@")
    history_block = f"""
    [누적 히스토리]
    텍스트: {", ".join(state.get("text_history", []))}
    음성: {", ".join(state.get("voice_history", []))}
    """

    prompt = f"""
    너는 veneta ai agent로 제조 공정을 만들어주는 agent야.
    의도와 달라진 일반적인 대화로,

    과거 대화 내역 
    {history_block}

    현재 질문
    {state.get("input")}

    대답은 짧고 친절하고 간단하게 해.
    """

    res = llm_chat.invoke(prompt)
    return {"response": res.content}

# ===============================
# Graph
# ===============================
def route_init(state: GraphState):
    if state.get("voice_path") and state["voice_status"] == "PENDING":
        return "voice_node"
    if state.get("image_path") and state["image_status"] == "PENDING":
        return "image_node"
    return "process_node"

def route_input(state: GraphState) -> str:
    if state.get("sop_valid"):
        return "save_sop"
    return "fail_sop"
def route_prompt(state: GraphState) -> str:
    if state.get("action") == Action.USE_MODEL:
        return "make_sop"
    if state.get("action") == Action.RETRIEVE:
        return "retrive"
    if state.get("action") == Action.GENERAL_CHAT:
        return "general"
    return ""
builder = StateGraph(GraphState)

builder.add_node("init",init_node)
builder.add_node("voice_node", voice_node)
builder.add_node("image_node", image_node)
builder.add_node("analyze_prompt", analyze_prompt)
builder.add_node("make_sop_node", make_sop_node)
builder.add_node("check_sop", check_sop)
builder.add_node("save_sop", run_dynamic_models)
builder.add_node("fail_sop",check_missing_llm)
builder.add_node("general_llm", general_llm)
builder.add_node("retrieve_node",retrieve_node)

builder.set_entry_point("init")
builder.add_conditional_edges(
    "init",
    route_init,
    {
        "voice_node": "voice_node",
        "image_node": "image_node",
        "process_node": "analyze_prompt"
    }
)
builder.add_edge("voice_node", "init")
builder.add_edge("image_node", "init")

builder.add_conditional_edges(
    "analyze_prompt",
    route_prompt,
    {
        "make_sop": "make_sop_node",
        "retrive": "retrieve_node",
        "general": "general_llm",
    }
)
builder.add_edge("make_sop_node", "check_sop")
builder.add_conditional_edges(
    "check_sop",
    route_input,
    {
        "save_sop": "save_sop",
        "fail_sop": "fail_sop"
    }
)
builder.set_finish_point("save_sop")
builder.set_finish_point("fail_sop")
builder.set_finish_point("general_llm")
builder.set_finish_point("retrieve_node")

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

    result = graph.invoke(state)
    final_response = result.get("response", "응답 없음")
    state.update(result)
    return ChatResponse(
        response=final_response,
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)