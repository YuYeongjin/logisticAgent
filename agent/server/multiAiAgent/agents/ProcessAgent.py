"""
ProcessAgent - 제조 공정 감지 및 이상 탐지 에이전트

Graph:
    save_observation → detect_process → retrieve_db_process → check_anomaly
"""
import json
from typing import TypedDict, Dict, Optional

from langgraph.graph import StateGraph, END

from agents.config import llm_json, get_db_connection


# ==============================
# State
# ==============================

class ProcessState(TypedDict):
    observation:      Dict
    observation_id:   Optional[int]
    detected_process: str
    db_process:       Optional[Dict]
    process_anomaly:  bool
    anomaly_reason:   str
    result:           Dict


# ==============================
# Node 1: 관찰 데이터 저장
# ==============================

def save_observation(state: ProcessState) -> Dict:
    obs  = state["observation"]
    conn = get_db_connection()
    cur  = conn.cursor()
    observation_id = None
    
    try:
        cur.execute(
            """
            INSERT INTO tbl_ai_observation (text_input, voice_text, vision_json)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (
                obs.get("text"),
                obs.get("voice"),
                json.dumps(obs.get("vision")),
            ),
        )
        observation_id = cur.fetchone()[0] # 커서 타입에 따라 안전하게 인덱스 접근
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        cur.close()
        conn.close()
        
    # 변경된 상태만 반환합니다.
    return {"observation_id": observation_id}


# ==============================
# Node 2: 공정 감지 (LLM)
# ==============================

def detect_process(state: ProcessState) -> Dict:
    obs    = state["observation"]
    vision = obs.get("vision") or {}
    scene  = (vision.get("scene") or {})

    prompt = f"""
작업 현장 데이터를 보고 현재 수행 중인 제조 공정 이름을 판단하라.

텍스트 입력:   {obs.get("text") or "없음"}
음성 입력:     {obs.get("voice") or "없음"}
작업자 활동:   {scene.get("human_activity", "없음")}
사용 도구:     {json.dumps(scene.get("tools", []), ensure_ascii=False)}
감지된 객체:   {[o["label"] for o in vision.get("objects", [])]}

가능한 공정 예시: cutting, mixing, packaging, heating, assembly, welding, inspection, unknown

반드시 아래 JSON 형식으로만 응답:
{{"process": "공정명"}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        detected_process = data.get("process", "unknown")
    except (json.JSONDecodeError, KeyError):
        detected_process = "unknown"

    return {"detected_process": detected_process}


# ==============================
# Node 3: DB에서 표준 공정 조회
# ==============================

def retrieve_db_process(state: ProcessState) -> Dict:
    process = state.get("detected_process", "unknown")

    if process == "unknown":
        return {"db_process": None}

    conn = get_db_connection()
    cur  = conn.cursor() # DB 설정에 따라 DictCursor 사용 시 dict() 래핑 필요
    db_process = None
    
    try:
        cur.execute(
            """
            SELECT s.id, s.name,
                   s.purpose, s.input, s.work, s.condition,
                   p.name AS process_name
            FROM tbl_sop s
            JOIN tbl_process p ON s.process_id = p.id
            WHERE p.name = %s
            LIMIT 1
            """,
            (process,),
        )
        row = cur.fetchone()
        
        # CursorFactory가 DictCursor라면 바로 row, 일반 Cursor라면 키 매핑 필요
        db_process = dict(row) if row else None
    finally:
        cur.close()
        conn.close()

    return {"db_process": db_process}


# ==============================
# Node 4: 이상 판단 (LLM)
# ==============================

def check_anomaly(state: ProcessState) -> Dict:
    obs        = state["observation"]
    db_process = state.get("db_process")
    process    = state.get("detected_process", "unknown")

    # DB에 공정이 없으면 신규 공정으로 간주
    if not db_process:
        reason = "DB에 정의되지 않은 신규 공정"
        return {
            "process_anomaly": True,
            "anomaly_reason":  reason,
            "result": {
                "process": process,
                "anomaly": True,
                "reason":  reason,
            }
        }

    prompt = f"""
현재 작업 상황과 표준 공정을 비교하여 이상 여부를 판단하라.

현재 작업:
{json.dumps(obs, ensure_ascii=False, indent=2)}

표준 공정:
{json.dumps(db_process, ensure_ascii=False, indent=2)}

반드시 아래 JSON 형식으로만 응답:
{{"anomaly": true | false, "reason": "한국어 설명"}}
"""
    try:
        res    = llm_json.invoke(prompt)
        data   = json.loads(res.content)
        anomaly = data.get("anomaly", False)
        reason  = data.get("reason", "")
    except Exception as e:
        anomaly = False
        reason  = f"분석 중 오류: {e}"

    return {
        "process_anomaly": anomaly,
        "anomaly_reason":  reason,
        "result": {
            "process": process,
            "anomaly": anomaly,
            "reason":  reason,
        }
    }


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(ProcessState)
_builder.add_node("save_observation",   save_observation)
_builder.add_node("detect_process",     detect_process)
_builder.add_node("retrieve_db_process", retrieve_db_process)
_builder.add_node("check_anomaly",      check_anomaly)

_builder.set_entry_point("save_observation")
_builder.add_edge("save_observation",    "detect_process")
_builder.add_edge("detect_process",      "retrieve_db_process")
_builder.add_edge("retrieve_db_process", "check_anomaly")

# set_finish_point 대신 최신 방식인 END 노드로 연결합니다.
_builder.add_edge("check_anomaly", END)

process_graph = _builder.compile()


# ==============================
# 공개 인터페이스
# ==============================

def run_process_agent(observation: Dict) -> Dict:
    """
    Returns:
        {"process": str, "anomaly": bool, "reason": str}
    """
    result = process_graph.invoke({
        "observation":      observation,
        "observation_id":   None,
        "detected_process": "unknown",
        "db_process":       None,
        "process_anomaly":  False,
        "anomaly_reason":   "",
        "result":           {},
    })
    return result.get("result", {})