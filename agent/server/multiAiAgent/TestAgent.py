"""
TestAgent - Multi-Agent 오케스트레이터

Graph 흐름:
    init → voice → image → merge
                              ↓         (병렬 fan-out)
                    safety_agent   process_agent
                              ↓         ↓      (fan-in → collect)
                            collect_results
                              ↓  (conditional)
                  ┌───────────┼───────────────┐
             sop_agent  sop_generator_agent  sop_question_agent
                  ↓              ↓                   ↓
                         orchestrator (END)
"""

import json
import os
import tempfile
from typing import TypedDict, Optional, Dict, List

from fastapi import FastAPI, File, Form, UploadFile
from langgraph.graph import StateGraph, END
from pydantic import BaseModel

from agents.ProcessAgent import run_process_agent
from agents.SafeAgent import run_safety_agent
from agents.SopGeneratorAgent import approve_and_save_sop, run_sop_create_agent
from agents.SopMultiAgent import run_sop_agent
from agents.SopQuestionAgent import run_sop_question_agent
from vision import (
    analyze_relations,
    build_scene_graph,
    check_ppe_compliance,
    detect_objects,
    detect_ppe,
    detect_pose,
    preprocess_image,
    scene_reasoning,
    segment_objects,
    stt_model,
)


# ==============================
# Global State
# ==============================

class GlobalState(TypedDict):
    # 입력
    input:                Optional[str]
    voice_path:           Optional[str]
    image_path:           Optional[str]
    conversation_history: List[Dict[str, str]]

    # 처리 결과
    voice_text:           Optional[str]
    image_analysis:       Optional[Dict]
    observation:          Dict

    # 각 에이전트 결과
    safety_result:        Dict
    process_result:       Dict
    sop_validation_result: Dict
    sop_generation_result: Dict

    # SOP Q&A
    sop_questions:          Optional[List[Dict]]
    current_question_index: int
    user_answers:           Dict[str, str]
    is_completed:           bool

    # 최종 출력
    final_decision: str
    final_score:    int


# ==============================
# Session Store
# ==============================

SESSION_STORE: Dict[str, Dict] = {}


def get_state(session_id: str) -> Dict:
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = {
            "input":                None,
            "voice_path":           None,
            "image_path":           None,
            "conversation_history": [],
            "voice_text":           None,
            "image_analysis":       None,
            "observation":          {},
            "safety_result":        {},
            "process_result":       {},
            "sop_validation_result": {},
            "sop_generation_result": {},
            "sop_questions":          None,
            "current_question_index": 0,
            "user_answers":           {},
            "is_completed":           False,
            "final_decision":         "info",
            "final_score":            0,
        }
    return SESSION_STORE[session_id]


# ==============================
# Node: init
# 매 요청마다 에이전트 결과 초기화
# ==============================

def init_node(state: GlobalState) -> Dict:
    # 기존 state 복사 없이 변경할 값만 리턴
    return {
        "safety_result":        {},
        "process_result":       {},
        "sop_validation_result": {},
        "sop_generation_result": {},
    }


# ==============================
# Node: voice
# 음성 → 텍스트 변환
# ==============================

def voice_node(state: GlobalState) -> Dict:
    print(f"voice_node")
    if not state.get("voice_path"):
        return {"voice_text": None}

    segments, _ = stt_model.transcribe(state["voice_path"], language="ko")
    voice_text  = " ".join(seg.text for seg in segments)
    return {"voice_text": voice_text}


# ==============================
# Node: image
# 이미지 → 다중 비전 분석
# ==============================

def image_node(state: GlobalState) -> Dict:
    print(f"image_node")
    if not state.get("image_path"):
        return {"image_analysis": None}

    img         = preprocess_image(state["image_path"])
    objects     = detect_objects(img)
    segments    = segment_objects(img)
    poses       = detect_pose(img)
    ppe_items   = detect_ppe(img)
    relations   = analyze_relations(objects)
    scene_graph = build_scene_graph(objects, relations)
    ppe_status  = check_ppe_compliance(objects, poses, ppe_items)
    scene       = scene_reasoning(objects, segments, poses, relations)

    return {
        "image_analysis": {
            "objects":     objects,
            "segments":    segments,
            "poses":       poses,
            "ppe_items":   ppe_items,
            "ppe_status":  ppe_status,
            "relations":   relations,
            "scene_graph": scene_graph,
            "scene":       scene,
        },
    }


# ==============================
# Node: merge
# 멀티모달 입력을 observation으로 통합
# ==============================

def merge_node(state: GlobalState) -> Dict:
    print(f"merge_node")
    observation = {
        "text":   state.get("input"),
        "voice":  state.get("voice_text"),
        "vision": state.get("image_analysis"),
    }

    history = list(state.get("conversation_history", []))
    if state.get("input"):
        history.append({"role": "user", "content": state["input"]})

    return {"observation": observation, "conversation_history": history}


# ==============================
# Node: safety_agent  (병렬 실행 대상)
# SOP Q&A 진행 중이면 건너뜀
# ==============================

def safety_node(state: GlobalState) -> Dict:
    print(f"safety_node")
    if state.get("sop_questions"):
        return {} # 상태 변경 없음
    result = run_safety_agent(state["observation"])
    return {"safety_result": result}


# ==============================
# Node: process_agent  (병렬 실행 대상)
# SOP Q&A 진행 중이면 건너뜀
# ==============================

def process_node(state: GlobalState) -> Dict:
    print(f"process_node")
    if state.get("sop_questions"):
        return {} # 상태 변경 없음
    result = run_process_agent(state["observation"])
    return {"process_result": result}


# ==============================
# Node: collect_results
# 패스스루 노드
# ==============================

def collect_results(state: GlobalState) -> Dict:
    return {} # 라우팅을 위한 더미 노드이므로 상태 변경 안 함


# ==============================
# Router: collect_results 이후 분기
# ==============================

def route_after_collect(state: GlobalState) -> str:
    print(f"route_after_collect")
    if state.get("sop_questions") and not state.get("is_completed"):
        return "sop_question_agent"

    if state.get("process_result", {}).get("anomaly"):
        return "sop_generator_agent"

    return "sop_agent"


# ==============================
# Node: sop_agent
# 기존 SOP 대비 이탈 검증
# ==============================

def sop_agent_node(state: GlobalState) -> Dict:
    print(f"sop_agent_node")
    result = run_sop_agent(state["observation"])
    return {"sop_validation_result": result}


# ==============================
# Node: sop_generator_agent
# 신규 SOP 생성
# ==============================

def sop_generator_node(state: GlobalState) -> Dict:
    print(f"sop_generator_node")
    result = run_sop_create_agent(state["observation"])
    return {"sop_generation_result": result or {}}


# ==============================
# Node: sop_question_agent
# SOP 승인 질문 생성 및 완료 평가
# ==============================

def sop_question_node(state: GlobalState) -> Dict:
    print(f"sop_question_node")
    # 주의: run_sop_question_agent 도 {**state, ...}를 반환하면 안 됩니다.
    # 해당 에이전트가 "업데이트할 부분(딕셔너리)"만 반환하도록 작성되어 있어야 합니다.
    updated = run_sop_question_agent(state)
    return updated


# ==============================
# Node: orchestrator
# 최종 위험 점수 산출 및 의사결정
# ==============================

def orchestrator(state: GlobalState) -> Dict:
    safety  = state.get("safety_result", {})
    process = state.get("process_result", {})
    sop     = state.get("sop_generation_result") or state.get("sop_validation_result", {})

    if state.get("sop_questions") and not state.get("is_completed"):
        return {
            "final_decision": json.dumps(
                {
                    "type":      "sop_confirm_required",
                    "questions": state["sop_questions"],
                },
                ensure_ascii=False,
            ),
            "final_score": 0,
        }

    score = 0
    if safety.get("risk_level") == "HIGH":
        score += 100
    elif safety.get("risk_level") == "MEDIUM":
        score += 40

    if process.get("anomaly"):
        score += 50

    if sop.get("deviation"):
        score += 30

    if score >= 100:
        decision = "danger"
    elif score >= 50:
        decision = "warn"
    elif score >= 30:
        decision = "warn"
    else:
        decision = "info"

    return {"final_decision": decision, "final_score": score}


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(GlobalState)

_builder.add_node("init",               init_node)
_builder.add_node("voice",              voice_node)
_builder.add_node("image",              image_node)
_builder.add_node("merge",              merge_node)
_builder.add_node("safety_agent",       safety_node)
_builder.add_node("process_agent",      process_node)
_builder.add_node("collect_results",    collect_results)
_builder.add_node("sop_agent",          sop_agent_node)
_builder.add_node("sop_generator_agent", sop_generator_node)
_builder.add_node("sop_question_agent", sop_question_node)
_builder.add_node("orchestrator",       orchestrator)

_builder.set_entry_point("init")
_builder.add_edge("init",  "voice")
_builder.add_edge("voice", "image")
_builder.add_edge("image", "merge")

_builder.add_edge("merge", "safety_agent")
_builder.add_edge("merge", "process_agent")

_builder.add_edge("safety_agent",  "collect_results")
_builder.add_edge("process_agent", "collect_results")

_builder.add_conditional_edges(
    "collect_results",
    route_after_collect,
    {
        "sop_agent":          "sop_agent",
        "sop_generator_agent": "sop_generator_agent",
        "sop_question_agent": "sop_question_agent",
    },
)

_builder.add_edge("sop_agent", "orchestrator")
_builder.add_edge("sop_generator_agent", "sop_question_agent")
_builder.add_edge("sop_question_agent",  "orchestrator")

# 최신 문법인 END 노드를 연결합니다.
_builder.add_edge("orchestrator", END)

graph = _builder.compile()


# ==============================
# FastAPI
# ==============================
# (이하 FastAPI 코드는 기존과 동일하게 유지하시면 됩니다)
# ...

app = FastAPI(title="Smart Factory Multi-Agent API")


class ChatResponse(BaseModel):
    response:   str
    log_level:  str
    diff_score: int


@app.post("/sop", response_model=ChatResponse)
async def chat(
    input:      Optional[str]          = Form(None),
    voice_file: Optional[UploadFile]   = File(None),
    image_file: Optional[UploadFile]   = File(None),
    session_id: str                    = Form(...),
):
    state = get_state(session_id)

    # 파일 처리
    if voice_file:
        content = await voice_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(content)
            state["voice_path"] = tmp.name

    if image_file:
        content = await image_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(content)
            state["image_path"] = tmp.name

    if input:
        state["input"] = input

    # SOP Q&A 진행 중: 현재 질문에 답변 기록
    if state.get("sop_questions") and input:
        questions   = state["sop_questions"]
        current_idx = state.get("current_question_index", 0)

        if current_idx < len(questions):
            questions[current_idx]["answer"]  = input
            state["current_question_index"]   = current_idx + 1

        if state["current_question_index"] >= len(questions):
            state["is_completed"] = True

            # 모든 답변 완료 → SOP 저장
            if state.get("sop_generation_result"):
                approve_and_save_sop(state["sop_generation_result"])

    # 그래프 실행
    updated_state = graph.invoke(state)
    SESSION_STORE[session_id] = updated_state

    decision = updated_state.get("final_decision", "info")
    score    = updated_state.get("final_score", 0)

    # SOP 확인 요청인 경우
    if isinstance(decision, str) and decision.startswith("{"):
        return ChatResponse(
            response=decision,
            log_level="notice",
            diff_score=0,
        )

    level_map = {"danger": "danger", "warn": "warn", "info": "info"}
    level     = level_map.get(decision, "notice")

    return ChatResponse(
        response=str(decision),
        log_level=level,
        diff_score=score,
    )


# ==============================
# 진입점
# ==============================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
