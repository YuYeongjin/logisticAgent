"""
SopGeneratorAgent - 신규 공정 SOP 생성 에이전트

Graph:
    check_existing_sop → generate_sop

승인 후 저장은 approve_and_save_sop()를 별도 호출.
"""
import json
from typing import TypedDict, Dict, Optional, List

from langgraph.graph import StateGraph
from sentence_transformers import SentenceTransformer

from agents.config import llm_json, get_db_connection


embedding_model = SentenceTransformer("all-MiniLM-L6-v2")


# ==============================
# State
# ==============================

class SopGenState(TypedDict):
    observation:     Dict
    existing_sop:    Optional[Dict]
    generated_sop:   Optional[Dict]
    process_detected: bool


# ==============================
# Node 1: 기존 SOP 존재 여부 확인
# ==============================

def check_existing_sop(state: SopGenState) -> SopGenState:
    obs    = state["observation"]
    vision = obs.get("vision") or {}
    scene  = (vision.get("scene") or {})
    activity = scene.get("human_activity", "")

    if not activity:
        state["existing_sop"] = None
        return state

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.id, s.name, p.description
            FROM tbl_sop s
            JOIN tbl_process p ON s.process_id = p.id
            WHERE p.name = %s
            LIMIT 1
            """,
            (activity,),
        )
        row = cur.fetchone()
        state["existing_sop"] = dict(row) if row else None
    finally:
        cur.close()
        conn.close()

    return state


# ==============================
# Node 2: SOP 생성 (LLM)
# ==============================

def generate_sop(state: SopGenState) -> SopGenState:
    obs    = state["observation"]
    vision = obs.get("vision") or {}
    scene  = (vision.get("scene") or {})

    observation_data = {
        "activity":    scene.get("human_activity", ""),
        "tools":       scene.get("tools", []),
        "environment": scene.get("environment", ""),
        "objects":     [o["label"] for o in vision.get("objects", [])],
        "ppe":         vision.get("ppe_status", {}),
        "voice":       obs.get("voice") or "",
        "text":        obs.get("text") or "",
    }

    schema = {
        "process_detected": True,
        "process_name":     "",
        "description":      "",
        "steps": [
            {
                "step":   1,
                "task":   "",
                "action": "",
                "tool":   "",
                "object": "",
                "safety": "",
            }
        ],
        "reason": "",
    }

    prompt = f"""
당신은 스마트팩토리 SOP 생성 AI입니다.
작업자의 행동 데이터를 분석하여 표준 작업 절차(SOP)를 생성하십시오.

### 작업 현장 데이터
{json.dumps(observation_data, indent=2, ensure_ascii=False)}

### 응답 형식 (반드시 아래 JSON 구조만 출력)
{json.dumps(schema, indent=2, ensure_ascii=False)}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        state["generated_sop"]   = data
        state["process_detected"] = data.get("process_detected", False)
    except (json.JSONDecodeError, KeyError):
        state["generated_sop"]   = {"process_detected": False}
        state["process_detected"] = False

    return state


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(SopGenState)
_builder.add_node("check_existing_sop", check_existing_sop)
_builder.add_node("generate_sop",       generate_sop)

_builder.set_entry_point("check_existing_sop")
_builder.add_edge("check_existing_sop", "generate_sop")
_builder.set_finish_point("generate_sop")

sop_gen_graph = _builder.compile()


# ==============================
# 공개 인터페이스
# ==============================

def run_sop_create_agent(observation: Dict) -> Optional[Dict]:
    """
    Returns:
        generated_sop dict 또는 None (공정 미감지 시)
    """
    result = sop_gen_graph.invoke({
        "observation":     observation,
        "existing_sop":   None,
        "generated_sop":  None,
        "process_detected": False,
    })
    sop = result.get("generated_sop")
    if not sop or not sop.get("process_detected"):
        return None
    return sop


def approve_and_save_sop(generated_sop: Dict) -> Dict:
    """
    사용자 승인 후 SOP를 DB에 저장하고 벡터 임베딩을 생성한다.

    Returns:
        {"status": "saved", "sop_id": int} 또는 {"status": "error", "reason": str}
    """
    if not generated_sop or not generated_sop.get("process_detected"):
        return {"status": "skipped", "reason": "저장할 SOP 데이터 없음"}

    process_name = generated_sop.get("process_name", "")
    description  = generated_sop.get("description", "")
    steps: List[Dict] = generated_sop.get("steps", [])

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        # 공정 upsert
        cur.execute(
            """
            INSERT INTO tbl_process (name)
            VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (process_name,),
        )
        process_id = cur.fetchone()["id"]

        # SOP 저장
        cur.execute(
            """
            INSERT INTO tbl_sop (process_id, name, description, is_completed)
            VALUES (%s, %s, %s, TRUE)
            RETURNING id
            """,
            (process_id, process_name, description),
        )
        sop_id = cur.fetchone()["id"]

        # 단계별 저장 + 임베딩
        for step in steps:
            cur.execute(
                """
                INSERT INTO tbl_sop_step
                    (sop_id, step_order, step_name, action,
                     expected_tool, expected_object, safety_check)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    sop_id,
                    step["step"],
                    step["task"],
                    step["action"],
                    step["tool"],
                    step["object"],
                    step["safety"],
                ),
            )
            step_id = cur.fetchone()["id"]

            content   = (
                f"Step {step['step']} Task: {step['task']} "
                f"Action: {step['action']} Tool: {step['tool']} "
                f"Object: {step['object']} Safety: {step['safety']}"
            )
            embedding = embedding_model.encode(content).tolist()

            cur.execute(
                """
                INSERT INTO tbl_sop_vector (sop_id, step_id, content, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                (sop_id, step_id, content, embedding),
            )

        conn.commit()
        return {"status": "saved", "sop_id": sop_id}

    except Exception as e:
        conn.rollback()
        return {"status": "error", "reason": str(e)}
    finally:
        cur.close()
        conn.close()
