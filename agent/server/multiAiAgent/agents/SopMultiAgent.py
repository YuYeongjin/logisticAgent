"""
SopMultiAgent - 기존 SOP 대비 이탈 여부 검증 에이전트

Graph:
    extract_process → retrieve_sop → analyze_deviation
"""
import json
from typing import TypedDict, Dict, List, Optional

from langgraph.graph import StateGraph

from agents.config import llm_json, get_db_connection


# ==============================
# State
# ==============================

class SopCheckState(TypedDict):
    observation:      Dict
    process_name:     str
    db_sop:           Optional[Dict]
    sop_steps:        List[Dict]
    deviation:        bool
    deviation_reason: str


# ==============================
# Node 1: 공정명 추출 (LLM)
# ==============================

def extract_process(state: SopCheckState) -> SopCheckState:
    obs    = state["observation"]
    vision = obs.get("vision") or {}
    scene  = (vision.get("scene") or {})

    prompt = f"""
아래 작업 현장 정보에서 현재 수행 중인 공정 이름을 추출하라.

텍스트 입력: {obs.get("text") or "없음"}
음성 입력:   {obs.get("voice") or "없음"}
작업자 활동: {scene.get("human_activity", "없음")}
사용 도구:   {json.dumps(scene.get("tools", []), ensure_ascii=False)}

반드시 아래 JSON 형식으로만 응답:
{{"process_name": "공정명"}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        state["process_name"] = data.get("process_name", "")
    except (json.JSONDecodeError, KeyError):
        state["process_name"] = ""

    return state


# ==============================
# Node 2: DB에서 SOP 및 단계 조회
# ==============================

def retrieve_sop(state: SopCheckState) -> SopCheckState:
    process_name = state.get("process_name", "")

    if not process_name:
        state["db_sop"]    = None
        state["sop_steps"] = []
        return state

    conn = get_db_connection()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            SELECT s.id, s.name,
                   s.purpose, s.input, s.work, s.condition
            FROM tbl_sop s
            JOIN tbl_process p ON s.process_id = p.id
            WHERE p.name = %s
            LIMIT 1
            """,
            (process_name,),
        )
        sop = cur.fetchone()
        state["db_sop"] = dict(sop) if sop else None

        if sop:
            cur.execute(
                """
                SELECT step_order, step_name, action,
                       expected_tool, expected_object, safety_check
                FROM tbl_sop_step
                WHERE sop_id = %s
                ORDER BY step_order
                """,
                (sop["id"],),
            )
            state["sop_steps"] = [dict(row) for row in cur.fetchall()]
        else:
            state["sop_steps"] = []
    finally:
        cur.close()
        conn.close()

    return state


# ==============================
# Node 3: SOP 이탈 분석 (LLM)
# ==============================

def analyze_deviation(state: SopCheckState) -> SopCheckState:
    obs       = state["observation"]
    db_sop    = state.get("db_sop")
    sop_steps = state.get("sop_steps", [])

    if not db_sop:
        state["deviation"]        = False
        state["deviation_reason"] = "등록된 SOP 없음 - 신규 공정으로 처리"
        return state

    prompt = f"""
당신은 스마트팩토리 SOP 검증 AI입니다.
현재 작업 상황과 표준 공정 지침을 비교하여 이탈 여부를 판단하라.

### 현재 작업 상황
{json.dumps(obs, ensure_ascii=False, indent=2)}

### 표준 SOP
이름:   {db_sop.get("name")}
목적:   {db_sop.get("purpose", "")}
투입:   {db_sop.get("input", "")}
작업:   {db_sop.get("work", "")}
조건:   {db_sop.get("condition", "")}
단계:
{json.dumps(sop_steps, ensure_ascii=False, indent=2)}

### 이탈 판단 기준
- deviation true:  작업 순서 누락, 도구 불일치, 안전 수칙 위반
- deviation false: 표준 절차를 준수하고 있음

반드시 아래 JSON 형식으로만 응답:
{{
  "deviation": true | false,
  "reason":    "한국어로 이탈 근거 또는 준수 근거 설명"
}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        state["deviation"]        = data.get("deviation", False)
        state["deviation_reason"] = data.get("reason", "")
    except (json.JSONDecodeError, KeyError):
        state["deviation"]        = False
        state["deviation_reason"] = "SOP 분석 실패 - 기본값 적용"

    return state


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(SopCheckState)
_builder.add_node("extract_process",   extract_process)
_builder.add_node("retrieve_sop",      retrieve_sop)
_builder.add_node("analyze_deviation", analyze_deviation)

_builder.set_entry_point("extract_process")
_builder.add_edge("extract_process",   "retrieve_sop")
_builder.add_edge("retrieve_sop",      "analyze_deviation")
_builder.set_finish_point("analyze_deviation")

sop_check_graph = _builder.compile()


# ==============================
# 공개 인터페이스
# ==============================

def run_sop_agent(observation: Dict) -> Dict:
    """
    Returns:
        {"deviation": bool, "reason": str}
    """
    result = sop_check_graph.invoke({
        "observation":      observation,
        "process_name":     "",
        "db_sop":           None,
        "sop_steps":        [],
        "deviation":        False,
        "deviation_reason": "",
    })
    return {
        "deviation": result["deviation"],
        "reason":    result["deviation_reason"],
    }
