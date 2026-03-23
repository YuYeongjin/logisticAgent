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
            SELECT s.id, s.name, s.purpose, s.input, s.work, s.condition
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
        "process_name": "",
        "purpose":   "",   # SOP 목적 (왜 이 작업을 하는가)
        "input":     "",   # 작업 투입물 (재료, 장비, 정보 등)
        "work":      "",   # 핵심 작업 내용 (무엇을 하는가)
        "condition": "",   # 수행 조건 및 전제 조건
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

각 필드의 의미:
- purpose:   이 SOP의 목적 (왜 이 작업을 수행하는가)
- input:     작업에 필요한 투입물 (재료, 장비, 도구, 정보)
- work:      핵심 작업 내용 요약 (무엇을 하는가)
- condition: 작업 수행 조건 및 전제 사항

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
    사용자 승인 후 SOP를 DB에 저장한다.

    저장은 두 단계로 분리된다:
      1) tbl_process + tbl_sop + tbl_sop_step  (실패 시 전체 롤백)
      2) tbl_sop_vector 임베딩                  (실패해도 1단계 결과는 유지)

    Returns:
        {"status": "saved", "sop_id": int} 또는 {"status": "error", "reason": str}
    """
    if not generated_sop or not generated_sop.get("process_detected"):
        return {"status": "skipped", "reason": "저장할 SOP 데이터 없음"}

    process_name = generated_sop.get("process_name", "")
    process_desc = generated_sop.get("process_description", "")
    purpose      = generated_sop.get("purpose",   "")
    input_       = generated_sop.get("input",     "")
    work         = generated_sop.get("work",      "")
    condition    = generated_sop.get("condition", "")
    steps: List[Dict] = generated_sop.get("steps", [])

    # ── 1단계: SOP 메타데이터 + 단계 저장 ──
    conn = get_db_connection()
    cur  = conn.cursor()
    step_ids: List[tuple] = []   # (step_id, content) 를 2단계에서 활용

    try:
        cur.execute(
            """
            INSERT INTO tbl_process (name, description)
            VALUES (%s, %s)
            ON CONFLICT (name) DO UPDATE SET description = EXCLUDED.description
            RETURNING id
            """,
            (process_name, process_desc),
        )
        process_id = cur.fetchone()["id"]

        cur.execute(
            """
            INSERT INTO tbl_sop
                (process_id, name, purpose, input, work, condition, is_completed)
            VALUES (%s, %s, %s, %s, %s, %s, TRUE)
            RETURNING id
            """,
            (process_id, process_name, purpose, input_, work, condition),
        )
        sop_id = cur.fetchone()["id"]

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
                    step.get("step"),
                    step.get("task", ""),
                    step.get("action", ""),
                    step.get("tool", ""),
                    step.get("object", ""),
                    step.get("safety", ""),
                ),
            )
            step_id = cur.fetchone()["id"]
            content = (
                f"Step {step.get('step')} Task: {step.get('task', '')} "
                f"Action: {step.get('action', '')} Tool: {step.get('tool', '')} "
                f"Object: {step.get('object', '')} Safety: {step.get('safety', '')}"
            )
            step_ids.append((step_id, content))

        conn.commit()

    except Exception as e:
        conn.rollback()
        return {"status": "error", "reason": str(e)}
    finally:
        cur.close()
        conn.close()

    # ── 2단계: 벡터 임베딩 저장 (실패해도 SOP 저장 결과는 유지) ──
    _save_vectors(sop_id, step_ids)

    return {"status": "saved", "sop_id": sop_id}


def _save_vectors(sop_id: int, step_ids: List[tuple]) -> None:
    """
    각 단계의 텍스트를 벡터화하여 tbl_sop_vector에 저장한다.
    차원 불일치 등 오류 발생 시 경고만 출력하고 SOP 저장에는 영향을 주지 않는다.

    tbl_sop_vector.embedding 컬럼의 차원이 모델 출력(384)과 다를 경우:
        ALTER TABLE tbl_sop_vector ALTER COLUMN embedding TYPE vector(384);
    """
    if not step_ids:
        return

    # 임베딩 차원 사전 확인
    sample_dim = len(embedding_model.encode("test").tolist())

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        for step_id, content in step_ids:
            embedding = embedding_model.encode(content).tolist()
            cur.execute(
                """
                INSERT INTO tbl_sop_vector (sop_id, step_id, content, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (sop_id, step_id, content, embedding),
            )
        conn.commit()

    except Exception as e:
        conn.rollback()
        print(
            f"[WARN] 벡터 임베딩 저장 실패 (SOP는 정상 저장됨): {e}\n"
            f"       DB 컬럼 차원이 {sample_dim}과 다를 수 있습니다.\n"
            f"       DB에서 실행: ALTER TABLE tbl_sop_vector "
            f"ALTER COLUMN embedding TYPE vector({sample_dim});"
        )
    finally:
        cur.close()
        conn.close()
