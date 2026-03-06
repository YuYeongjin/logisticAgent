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
    
    # 에러 방어: vision이 None이면 빈 딕셔너리로 취급
    vision_data = obs.get("vision") or {}
    voice_data = obs.get("voice") or "설명 없음"
    text_data = obs.get("text") or ""
    db_sop = state["db_process"]

    prompt = f"""
    표준 공정 지침과 현재 상황을 비교하여 이탈 여부를 판단하라.
    현재 상황: {json.dumps(obs, ensure_ascii=False)}
    표준 지침: {json.dumps(db_sop, ensure_ascii=False) if db_sop else "데이터 없음"}
    
    반드시 JSON 출력: {{"deviation": true or false, "reason": "문장"}}
    """
    
    res = llm_json.invoke(prompt)
    data = json.loads(res.content)
    
    state["deviation"] = data.get("deviation", False)
    state["result"] = {
        "deviation": state["deviation"],
        "reason": data.get("reason", "")
    }
    return state

def run_sop_agent(observation: Dict):
    print(f"SopCheckState" )
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