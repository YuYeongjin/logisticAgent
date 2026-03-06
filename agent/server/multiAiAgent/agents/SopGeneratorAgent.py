import json
from typing import TypedDict, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from langchain_ollama import ChatOllama

# 기존 설정 그대로 유지
llm_json = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url="http://localhost:11434"
)

DB_CONFIG = {
    "host": "localhost",
    "database": "factory_db",
    "user": "admin",
    "password": "Abcd1234",
    "port": "5432"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)

class SopState(TypedDict):
    observation: Dict
    db_process: Optional[Dict]
    deviation: bool
    result: Dict

def sop_db_retrieve(state: SopState):
    print(f"SopState :: {SopState}" )
    # ProcessAgent의 DB 조회 방식 그대로 적용
    obs = state["observation"]
    
    # 에러 방어: vision이 None이면 빈 딕셔너리로 취급
    vision_data = obs.get("vision") or {}
    voice_data = obs.get("voice") or "설명 없음"
    text_data = obs.get("text") or ""
    db_sop = state["db_process"]
    process_name = vision_data.get("action", "")
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tbl_sop WHERE name = %s LIMIT 1", (process_name,))
    state["db_process"] = cur.fetchone()
    cur.close()
    conn.close()
    return state
def sop_llm_analysis(state: SopState):

    obs = state["observation"]

    vision = obs.get("vision") or {}
    voice = obs.get("voice") or ""
    text = obs.get("text") or ""

    objects = vision.get("objects", [])
    ppe = vision.get("ppe_status", {})
    scene = vision.get("scene", {})

    activity = scene.get("human_activity", "")
    tools = scene.get("tools", [])
    env = scene.get("environment", "")

    observation_data = {
        "activity": activity,
        "tools": tools,
        "environment": env,
        "objects": objects,
        "ppe": ppe,
        "voice": voice,
        "text": text
    }

    # JSON schema (f-string 오류 방지)
    schema = {
        "process_detected": True,
        "process_name": "",
        "description": "",
        "steps": [
            {
                "step": 1,
                "task": "",
                "action": ""
            }
        ],
        "safety": {
            "helmet": True,
            "gloves": True,
            "vest": True,
            "issue": ""
        },
        "reason": ""
    }

    prompt = f"""
당신은 스마트팩토리 공정 분석 AI입니다.

작업자의 행동과 환경을 분석하여 공정(SOP)을 판단하십시오.

### 분석 규칙

1. 실제 작업 행동이 있을 때만 공정 생성
2. 단순 이동, 대기, 걷기는 공정이 아님
3. 제조 작업일 때만 SOP 생성
4. PPE 미착용은 safety.issue에 기록

### Vision / Sensor Observation

{json.dumps(observation_data, indent=2, ensure_ascii=False)}

### 반드시 아래 JSON 형식으로만 응답

{json.dumps(schema, indent=2, ensure_ascii=False)}
"""

    res = llm_json.invoke(prompt)

    try:
        data = json.loads(res.content)
    except Exception as e:
        print("LLM JSON parse error:", e)
        data = {"process_detected": False}

    state["result"] = {
        "deviation": False,
        "reason": data.get("reason", "")
    }

    return state

def run_sop_create_agent(observation: Dict):
    print(f"SopCreateState" )
    # Main Runner: 에러가 났던 함수 이름을 피하고 구조는 유지
    state: SopState = {
        "observation": observation,
        "db_process": None,
        "deviation": False,
        "result": {}
    }
    
    state = sop_db_retrieve(state)
    state = sop_llm_analysis(state)
    
    return state["result"]