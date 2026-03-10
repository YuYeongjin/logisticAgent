import json
from typing import TypedDict, Optional, Dict, Any
from enum import Enum

import psycopg2
from psycopg2.extras import RealDictCursor

from langchain_ollama import ChatOllama


# ===============================
# LLM
# ===============================

llm_json = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url="http://localhost:11434"
)

# ===============================
# Database
# ===============================

DB_CONFIG = {
    "host": "localhost",
    "database": "factory_db",
    "user": "admin",
    "password": "Abcd1234",
    "port": "5432"
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


# ===============================
# Process Model
# ===============================

class ProcessState(TypedDict):
    observation: Dict
    observation_id: Optional[int]
    detected_process: Optional[str]
    process_anomaly: bool
    db_process: Optional[Dict]
    result: Dict


# ===============================
# DB 조회
# ===============================

def retrieve_process(process_name: str):

    conn = get_db_connection()

    cur = conn.cursor()

    cur.execute("""
        SELECT *
        FROM tbl_sop
        WHERE name = %s
        LIMIT 1
    """, (process_name,))

    row = cur.fetchone()

    cur.close()
    conn.close()

    return row

def save_observation(state: ProcessState):

    obs = state["observation"]

    text = obs.get("text")
    voice = obs.get("voice")
    vision = obs.get("vision")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO tbl_ai_observation
        (text_input, voice_text, vision_json)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (
            text,
            voice,
            json.dumps(vision)
        )
    )

    observation_id = cur.fetchone()["id"]

    conn.commit()
    cur.close()
    conn.close()

    state["observation_id"] = observation_id

    return state

# ===============================
# 공정 판단
# ===============================

def detect_process(state: ProcessState):

    # print("PROCESS DETECT")

    obs = state["observation"]

    prompt = f"""
    다음 작업 상황을 보고 현재 수행 중인 제조 공정을 판단하라.

    observation:
    {json.dumps(obs, ensure_ascii=False)}

    가능한 공정 예시:
    - cutting
    - mixing
    - packaging
    - heating
    - unknown

    반드시 JSON으로 출력

    {{
        "process": "공정명"
    }}
    """

    res = llm_json.invoke(prompt)

    data = json.loads(res.content)

    state["detected_process"] = data["process"]

    return state


# ===============================
# 공정 DB 조회
# ===============================

def process_retrieve(state: ProcessState):

    # print("PROCESS RETRIEVE")

    process = state.get("detected_process")

    if not process or process == "unknown":

        state["db_process"] = None

        return state

    result = retrieve_process(process)

    state["db_process"] = result

    return state


# ===============================
# 공정 이상 판단
# ===============================

def process_anomaly_check(state: ProcessState):

    # print("PROCESS ANOMALY CHECK")

    obs = state["observation"]

    db_process = state.get("db_process")

    process = state.get("detected_process", "unknown")

    # DB에 공정이 없는 경우
    if not db_process:

        state["process_anomaly"] = True

        state["result"] = {

            "process": process,

            "anomaly": True,

            "reason": "DB에 정의되지 않은 공정"

        }

        return state

    prompt = f"""
    현재 작업 상황과 표준 공정을 비교하여
    공정 이상 여부를 판단하라.

    현재 작업:
    {json.dumps(obs, ensure_ascii=False)}

    표준 공정:
    {json.dumps(db_process, ensure_ascii=False)}

    반드시 JSON 출력

    {{
        "anomaly": true or false,
        "reason": "설명"
    }}
    """

    try:

        res = llm_json.invoke(prompt)

        data = json.loads(res.content)

        anomaly = data.get("anomaly", False)

        reason = data.get("reason", "")

    except Exception as e:

        print("LLM ERROR:", e)

        anomaly = True

        reason = "LLM 분석 실패"

    state["process_anomaly"] = anomaly

    state["result"] = {

        "process": process,

        "anomaly": anomaly,

        "reason": reason

    }

    return state



# ===============================
# Main Runner
# ===============================

def run_process_agent(observation):

    state: ProcessState = {

        "observation": observation

    }


    # 1 observation 저장
    state = save_observation(state)

    state = detect_process(state)

    state = process_retrieve(state)

    state = process_anomaly_check(state)

    return state["result"]