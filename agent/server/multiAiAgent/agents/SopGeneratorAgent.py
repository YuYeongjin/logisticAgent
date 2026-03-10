import json
from typing import TypedDict, Dict, Optional, List

import psycopg2
from psycopg2.extras import RealDictCursor

from langchain_ollama import ChatOllama
from sentence_transformers import SentenceTransformer


# -----------------------------
# LLM
# -----------------------------

llm_json = ChatOllama(
    model="llama3.1",
    temperature=0,
    format="json",
    base_url="http://localhost:11434"
)

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


# -----------------------------
# DB CONFIG
# -----------------------------

DB_CONFIG = {
    "host": "localhost",
    "database": "factory_db",
    "user": "admin",
    "password": "Abcd1234",
    "port": "5432"
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


# -----------------------------
# STATE
# -----------------------------

class SopState(TypedDict):
    observation: Dict
    db_process: Optional[Dict]
    generated_sop: Optional[Dict]
    deviation: bool
    result: Dict


# -----------------------------
# 2️⃣ 기존 SOP 조회
# -----------------------------

def sop_db_retrieve(state: SopState):

    obs = state["observation"]

    vision_data = obs.get("vision") or {}

    process_name = vision_data.get("action", "")

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT s.*, p.name as process_name
        FROM tbl_sop s
        JOIN tbl_process p
        ON s.process_id = p.id
        WHERE p.name = %s
        LIMIT 1
        """,
        (process_name,)
    )

    state["db_process"] = cur.fetchone()

    cur.close()
    conn.close()

    return state


# -----------------------------
# 3️⃣ SOP 생성 LLM
# -----------------------------

def sop_llm_generate(state: SopState):

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

    schema = {
        "process_detected": True,
        "deviation":True,
        "process_name": "",
        "description": "",
        "steps": [
            {
                "step": 1,
                "task": "",
                "action": "",
                "tool": "",
                "object": "",
                "safety": ""
            }
        ],
        "reason": "",
    }

    prompt = f"""
당신은 스마트팩토리 SOP 생성 AI입니다.

작업자의 행동을 분석하여 SOP를 생성하십시오.

### Observation

{json.dumps(observation_data, indent=2, ensure_ascii=False)}

### 반드시 아래 JSON 형식으로만 응답

{json.dumps(schema, indent=2, ensure_ascii=False)}
"""

    res = llm_json.invoke(prompt)

    try:
        data = json.loads(res.content)
    except:
        data = {"process_detected": False}

    state["generated_sop"] = data
    state["deviation"] = True
    return state


# -----------------------------
# 4️⃣ SOP 저장
# -----------------------------

def save_sop_to_db(state: SopState):

    sop = state["generated_sop"]

    process_name = sop["process_name"]
    description = sop["description"]

    steps = sop["steps"]

    conn = get_db_connection()
    cur = conn.cursor()

    # process 저장
    cur.execute(
        """
        INSERT INTO tbl_process (name)
        VALUES (%s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (process_name,)
    )

    process_id = cur.fetchone()["id"]

    # sop 저장
    cur.execute(
        """
        INSERT INTO tbl_sop
        (process_id, name, description, is_completed)
        VALUES (%s, %s, %s, TRUE)
        RETURNING id
        """,
        (
            process_id,
            process_name,
            description
        )
    )

    sop_id = cur.fetchone()["id"]

    # step 저장
    for step in steps:

        cur.execute(
            """
            INSERT INTO tbl_sop_step
            (sop_id, step_order, step_name, action, expected_tool, expected_object, safety_check)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                sop_id,
                step["step"],
                step["task"],
                step["action"],
                step["tool"],
                step["object"],
                step["safety"]
            )
        )

        step_id = cur.fetchone()["id"]

        content = f"""
        Step {step["step"]}
        Task: {step["task"]}
        Action: {step["action"]}
        Tool: {step["tool"]}
        Object: {step["object"]}
        Safety: {step["safety"]}
        """

        embedding = embedding_model.encode(content).tolist()

        cur.execute(
            """
            INSERT INTO tbl_sop_vector
            (sop_id, step_id, content, embedding)
            VALUES (%s,%s,%s,%s)
            """,
            (
                sop_id,
                step_id,
                content,
                embedding
            )
        )

    conn.commit()

    cur.close()
    conn.close()

    return state


# -----------------------------
# Runner
# -----------------------------

def run_sop_create_agent(observation: Dict):

    state: SopState = {
        "observation": observation,
        "observation_id": None,
        "db_process": None,
        "generated_sop": None,
        "deviation": False,
        "result": {}
    }

    # 2 기존 sop 조회
    state = sop_db_retrieve(state)

    # 3 sop 생성
    state = sop_llm_generate(state)

    return state["generated_sop"]


# -----------------------------
# 사용자가 승인할 때
# -----------------------------

def approve_and_save_sop(state: SopState):

    state = save_sop_to_db(state)

    return {"status": "saved"}