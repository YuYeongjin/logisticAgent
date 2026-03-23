"""
TestAgent - Multi-Agent 오케스트레이터

Graph 흐름:
    init → voice → image → merge
                              ↓              (병렬 fan-out)
                    safety_agent        process_agent
                              ↓              ↓         (fan-in)
                            collect_results
                              ↓  (route_after_collect, 5방향)
          ①                 ②              ③                ④              ⑤
   sop_interactive      sop_approval   sop_creation    propose_sop      sop_agent
       _node               _node          _intent        _creation          ↓
   (State Machine)          ↓           (AGREE/REJECT)      ↓               ↓
          ↓           (route_after      END (AGREE→     orchestrator    orchestrator
          ↓             _approval)      다음요청①)          ↓               ↓
      orchestrator    END or orch.                         END             END
          ↓
         END

[SOP 대화형 수집 Stage 순서]
  WAITING_PROCESS_NAME → WAITING_PROCESS_DESC → WAITING_PURPOSE
  → WAITING_INPUT → WAITING_WORK → WAITING_CONDITION
  → WAITING_STEP ←────────────────────── WAITING_STEP_MORE
       └─ 완료 → COMPLETED → sop_approval_pending=True → ② 로 전환
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
from agents.config import llm_chat, llm_json
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
    conversation_history: List[Dict[str, str]]  # 누적 대화 이력

    # 처리 결과
    voice_text:           Optional[str]
    image_analysis:       Optional[Dict]
    observation:          Dict

    # 각 에이전트 결과
    safety_result:        Dict
    process_result:       Dict
    sop_validation_result: Dict
    sop_generation_result: Dict

    # SOP 승인 대화
    sop_approval_pending:  bool      # SOP 미리보기 후 사용자 승인 대기 중
    sop_creation_proposed: bool      # 신규 공정 감지 후 SOP 생성 동의 요청 중

    # SOP 대화형 수집 (Step-by-Step State Machine)
    sop_collection_stage: str        # 현재 수집 단계 ('IDLE' | 'WAITING_*' | 'COMPLETED')
    sop_draft:            Dict       # 현재까지 수집된 SOP 필드 데이터

    # 최종 출력
    final_decision:  str
    final_score:     int
    response_message: str  # LLM이 생성한 자연어 응답


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
            "sop_approval_pending":   False,
            "sop_creation_proposed":  False,
            "sop_collection_stage":   "IDLE",
            "sop_draft":              {},
            "final_decision":         "info",
            "final_score":            0,
            "response_message":       "",
        }
    return SESSION_STORE[session_id]


# ==============================
# Node: init
# 매 요청마다 에이전트 결과 초기화
# ==============================

def init_node(state: GlobalState) -> Dict:
    cleared: Dict = {
        "safety_result":         {},
        "process_result":        {},
        "sop_validation_result": {},
        "response_message":      "",   # 매 요청마다 초기화
    }
    # 승인 대기 중이면 SOP 생성 결과를 유지 (다음 요청에서도 저장 가능)
    if not state.get("sop_approval_pending"):
        cleared["sop_generation_result"] = {}
    # sop_draft / sop_collection_stage 는 수집 중일 때 여기서 건드리지 않음.
    # SESSION_STORE 에 보존되어 다음 요청에서 자동으로 이어짐.
    return cleared


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

    # 음성 입력을 우선으로 대화 이력에 추가, 없으면 텍스트
    voice_text = state.get("voice_text")
    text_input = state.get("input")

    if voice_text and text_input:
        # 둘 다 있으면 하나로 합쳐서 기록
        history.append({"role": "user", "content": f"{text_input} [음성: {voice_text}]"})
    elif voice_text:
        history.append({"role": "user", "content": f"[음성] {voice_text}"})
    elif text_input:
        history.append({"role": "user", "content": text_input})

    return {"observation": observation, "conversation_history": history}


# ==============================
# Node: safety_agent  (병렬 실행 대상)
# SOP Q&A 진행 중이면 건너뜀
# ==============================

def safety_node(state: GlobalState) -> Dict:
    print("safety_node")
    # 승인·동의·대화 수집 중이면 건너뜀
    if (state.get("sop_approval_pending")
            or state.get("sop_creation_proposed")
            or state.get("sop_collection_stage", "IDLE") != "IDLE"):
        return {}
    result = run_safety_agent(state["observation"])
    return {"safety_result": result}


# ==============================
# Node: process_agent  (병렬 실행 대상)
# 승인/동의/수집 중이면 건너뜀
# ==============================

def process_node(state: GlobalState) -> Dict:
    print("process_node")
    if (state.get("sop_approval_pending")
            or state.get("sop_creation_proposed")
            or state.get("sop_collection_stage", "IDLE") != "IDLE"):
        return {}
    result = run_process_agent(state["observation"])
    return {"process_result": result}


# ==============================
# Node: collect_results  (fan-in 패스스루)
# ==============================

def collect_results(state: GlobalState) -> Dict:
    return {}


# ==============================
# SOP 미리보기 텍스트 생성 (헬퍼)
# ==============================

def _build_sop_preview(sop: Dict) -> str:
    lines = [
        f"공정명: {sop.get('process_name', '')}",
        f"목적:   {sop.get('purpose',   '')}",
        f"투입:   {sop.get('input',     '')}",
        f"작업:   {sop.get('work',      '')}",
        f"조건:   {sop.get('condition', '')}",
        "단계:",
    ]
    for s in sop.get("steps", []):
        lines.append(
            f"  {s.get('step')}. [{s.get('task', '')}] "
            f"{s.get('action', '')}  "
            f"(도구: {s.get('tool', '')}, 안전: {s.get('safety', '')})"
        )
    return "\n".join(lines)


# ==============================
# Node: sop_approval_node
# 사용자의 저장/수정/거부 의도를 감지하고 처리
# ==============================

def sop_approval_node(state: GlobalState) -> Dict:
    print("sop_approval_node")
    user_input = state.get("input") or state.get("voice_text") or ""
    sop        = state.get("sop_generation_result", {})
    history    = state.get("conversation_history", [])

    # 입력 없으면 미리보기 재표시
    if not user_input:
        preview  = _build_sop_preview(sop)
        response = f"저장 대기 중인 SOP입니다:\n\n{preview}\n\n저장하시겠습니까? (저장 / 수정 / 취소)"
        return {
            "response_message":     response,
            "conversation_history": history + [{"role": "assistant", "content": response}],
            "final_decision":       "notice",
            "final_score":          0,
        }

    # LLM으로 사용자 의도 분류
    intent_prompt = f"""사용자 입력에서 SOP 관련 의도를 분류하라.

사용자 입력: "{user_input}"

- SAVE:   저장·승인 (예: "저장해줘", "좋아", "확인", "저장", "네", "ㅇㅇ")
- MODIFY: 수정·변경 (예: "수정해줘", "바꿔줘", "다시 만들어줘")
- REJECT: 취소·거부 (예: "취소", "필요없어", "아니", "하지마")
- CHAT:   질문·대화 (그 외)

반드시 JSON으로만 응답:
{{"intent": "SAVE" | "MODIFY" | "REJECT" | "CHAT", "feedback": "수정 요청 내용 (MODIFY일 때만)"}}
"""
    try:
        res      = llm_json.invoke(intent_prompt)
        data     = json.loads(res.content)
        intent   = data.get("intent", "CHAT")
        feedback = data.get("feedback", "")
    except Exception:
        intent   = "CHAT"
        feedback = ""

    print(f"  → SOP approval intent: {intent}")

    # ── SAVE ──
    if intent == "SAVE":
        save_result = approve_and_save_sop(sop)
        if save_result.get("status") == "saved":
            response = f"SOP '{sop.get('process_name', '')}' 이(가) 성공적으로 저장되었습니다."
        else:
            response = f"저장 중 오류: {save_result.get('reason', '알 수 없는 오류')}"
        return {
            "sop_approval_pending":  False,
            "sop_generation_result": {},
            "response_message":      response,
            "conversation_history":  history + [{"role": "assistant", "content": response}],
            "final_decision":        "info",
            "final_score":           0,
        }

    # ── MODIFY ──
    if intent == "MODIFY":
        obs = dict(state.get("observation", {}))
        obs["text"] = f"{obs.get('text') or ''} [수정 요청: {feedback or user_input}]".strip()
        new_sop = run_sop_create_agent(obs)
        if new_sop:
            preview  = _build_sop_preview(new_sop)
            response = f"수정된 SOP입니다:\n\n{preview}\n\n저장하시겠습니까? (저장 / 수정 / 취소)"
            return {
                "sop_generation_result": new_sop,
                "response_message":      response,
                "conversation_history":  history + [{"role": "assistant", "content": response}],
                "final_decision":        "notice",
                "final_score":           0,
            }
        response = "SOP 재생성에 실패했습니다. 다시 시도해주세요."
        return {
            "response_message":     response,
            "conversation_history": history + [{"role": "assistant", "content": response}],
            "final_decision":       "notice",
            "final_score":          0,
        }

    # ── REJECT ──
    if intent == "REJECT":
        response = "SOP 저장을 취소했습니다."
        return {
            "sop_approval_pending":  False,
            "sop_generation_result": {},
            "response_message":      response,
            "conversation_history":  history + [{"role": "assistant", "content": response}],
            "final_decision":        "info",
            "final_score":           0,
        }

    # ── CHAT: 위임 (response_message 없으면 orchestrator로 이동) ──
    return {}


# ==============================
# Router: sop_approval_node 이후 분기
# ==============================

def route_after_approval(state: GlobalState) -> str:
    if state.get("response_message"):
        return "END"
    return "orchestrator"


# ==============================
# Router: collect_results 이후 분기
# ==============================

def route_after_collect(state: GlobalState) -> str:
    print("route_after_collect")
    # ① SOP 대화형 수집 진행 중 → 최우선으로 수집 노드로
    if state.get("sop_collection_stage", "IDLE") != "IDLE":
        return "sop_interactive_node"

    # ② SOP 승인 대기 중 → 저장/수정/거부/대화 처리
    if state.get("sop_approval_pending"):
        return "sop_approval_node"

    # ③ SOP 생성 동의 요청 중 → 사용자 의도 분류
    if state.get("sop_creation_proposed"):
        return "sop_creation_intent_node"

    # ④ 신규 공정 감지 → 생성 여부 사용자에게 먼저 물어봄
    if state.get("process_result", {}).get("anomaly"):
        return "propose_sop_creation"

    # ⑤ 기존 공정 → SOP 이탈 검증
    return "sop_agent"


# ==============================
# Node: propose_sop_creation
# 신규 공정 감지 시 SOP 생성 여부를 사용자에게 물어봄
# ==============================

def propose_sop_creation_node(state: GlobalState) -> Dict:
    print("propose_sop_creation_node")
    process = state.get("process_result", {})
    process_name = process.get("process", "신규 작업")
    history = state.get("conversation_history", [])

    response = (
        f"새로운 공정 '{process_name}'이(가) 감지되었습니다. "
        "아직 등록된 SOP가 없습니다. 이 작업의 SOP를 생성하시겠습니까?"
    )
    updated_history = history + [{"role": "assistant", "content": response}]
    return {
        "sop_creation_proposed":  True,
        "response_message":       response,
        "conversation_history":   updated_history,
        "final_decision":         "notice",
        "final_score":            0,
    }


# ==============================
# Node: sop_creation_intent_node
# 사용자의 SOP 생성 동의/거부 의도 분류
# ==============================

def sop_creation_intent_node(state: GlobalState) -> Dict:
    print("sop_creation_intent_node")
    user_input = state.get("input") or state.get("voice_text") or ""
    history    = state.get("conversation_history", [])

    intent_prompt = f"""사용자가 SOP 생성에 동의하는지 분류하라.

사용자 입력: "{user_input}"

- AGREE:  동의 (예: "네", "응", "좋아", "만들어줘", "생성해줘", "ㅇㅇ", "해줘")
- REJECT: 거부 (예: "아니", "필요없어", "취소", "하지마", "괜찮아", "ㄴㄴ")

반드시 JSON으로만 응답:
{{"intent": "AGREE" | "REJECT"}}
"""
    try:
        res    = llm_json.invoke(intent_prompt)
        data   = json.loads(res.content)
        intent = data.get("intent", "REJECT")
    except Exception:
        intent = "REJECT"

    print(f"  → SOP creation intent: {intent}")

    if intent == "AGREE":
        # 대화형 수집 모드 시작: Stage Machine 초기화 + 첫 번째 질문 생성
        response = (
            "SOP 작성을 시작하겠습니다!\n\n"
            "먼저, 이 공정의 **이름**을 입력해 주세요.\n"
            "예: '치킨 튀기기', '금속 부품 용접', '포장재 조립'"
        )
        return {
            "sop_creation_proposed":  False,
            "sop_collection_stage":   "WAITING_PROCESS_NAME",
            "sop_draft":              {},
            "response_message":       response,
            "conversation_history":   history + [{"role": "assistant", "content": response}],
            "final_decision":         "notice",
            "final_score":            0,
        }

    # REJECT
    response = "SOP 생성을 취소했습니다. 다른 도움이 필요하시면 말씀해 주세요."
    return {
        "sop_creation_proposed": False,
        "response_message":      response,
        "conversation_history":  history + [{"role": "assistant", "content": response}],
        "final_decision":        "info",
        "final_score":           0,
    }


# ==============================
# Router: sop_creation_intent_node 이후 분기
# AGREE: 수집 시작 질문 응답 완료 → END (다음 요청에서 sop_interactive_node로 진입)
# REJECT: 취소 응답 완료 → END
# ==============================

def route_after_creation_intent(state: GlobalState) -> str:
    return "END"


# ==============================
# LLM 추출 헬퍼 (sop_interactive_node 전용)
# ==============================

def _extract_with_llm(user_input: str, field_hint: str, field_key: str) -> Optional[str]:
    """사용자 자연어 입력에서 단일 필드를 추출한다. 불명확하면 None 반환."""
    prompt = f"""사용자 입력에서 '{field_hint}'에 해당하는 내용을 추출하라.

사용자 입력: "{user_input}"

내용이 충분히 명확하면 추출하고, 불명확하거나 관련 없으면 null을 반환하라.
반드시 JSON으로만 응답: {{"{field_key}": "추출된 내용" | null}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        val  = data.get(field_key)
        if val and str(val).strip() and str(val).strip().lower() not in ("null", "none", "없음"):
            return str(val).strip()
        return None
    except Exception:
        return None


def _extract_step_with_llm(user_input: str, step_order: int) -> Optional[Dict]:
    """사용자 입력에서 단일 SOP 단계 정보를 추출한다.
    step_name 과 action 이 없으면 None 반환.
    """
    prompt = f"""사용자 입력에서 {step_order}번째 작업 단계 정보를 추출하라.

사용자 입력: "{user_input}"

반드시 JSON으로만 응답:
{{
  "step_name":       "단계 이름 (없으면 null)",
  "action":          "수행할 동작 설명 (없으면 null)",
  "expected_tool":   "사용 도구/장비 (없으면 빈 문자열)",
  "expected_object": "대상 물체/재료 (없으면 빈 문자열)",
  "safety_check":    "안전 주의사항 (없으면 빈 문자열)"
}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        if data.get("step_name") and data.get("action"):
            return {
                "step_name":       str(data["step_name"]).strip(),
                "action":          str(data["action"]).strip(),
                "expected_tool":   str(data.get("expected_tool") or "").strip(),
                "expected_object": str(data.get("expected_object") or "").strip(),
                "safety_check":    str(data.get("safety_check") or "").strip(),
            }
        return None
    except Exception:
        return None


def _classify_step_continuation(user_input: str, step_count: int) -> Dict:
    """WAITING_STEP_MORE 단계: 사용자 응답이 완료/추가(데이터 포함)/추가(데이터 없음) 중 무엇인지 분류.
    반환: {"status": "DONE"|"MORE_WITH_DATA"|"MORE_NO_DATA", "step_data": dict|None}
    """
    prompt = f"""사용자의 응답을 분석하라. 현재까지 {step_count}개의 단계가 수집되었다.

사용자 입력: "{user_input}"

다음 중 하나로 분류하라:
- DONE:           수집 완료 (예: "완료", "끝", "없어요", "이게 다야", "ㄴ", "다 됐어")
- MORE_WITH_DATA: 추가 단계를 포함한 입력 (예: "2단계는 기름을 달군다", "다음: 재료 투입 — 칼 사용")
- MORE_NO_DATA:   추가 단계 있지만 상세 미입력 (예: "네", "있어요", "더 있어")

MORE_WITH_DATA 인 경우 단계 데이터도 함께 추출하라 (step_name, action 필수).

반드시 JSON으로만 응답:
{{
  "status": "DONE" | "MORE_WITH_DATA" | "MORE_NO_DATA",
  "step_data": {{
    "step_name":       "단계 이름",
    "action":          "수행 동작",
    "expected_tool":   "도구 (없으면 빈 문자열)",
    "expected_object": "대상 (없으면 빈 문자열)",
    "safety_check":    "안전사항 (없으면 빈 문자열)"
  }}
}}
step_data 는 MORE_WITH_DATA 가 아닌 경우 null 로 설정.
"""
    try:
        res       = llm_json.invoke(prompt)
        data      = json.loads(res.content)
        status    = data.get("status", "MORE_NO_DATA")
        step_data = data.get("step_data")
        # step_data 유효성 검증
        if status == "MORE_WITH_DATA" and step_data:
            if not (step_data.get("step_name") and step_data.get("action")):
                status    = "MORE_NO_DATA"
                step_data = None
        return {"status": status, "step_data": step_data}
    except Exception:
        return {"status": "MORE_NO_DATA", "step_data": None}


def _draft_to_gen_result(draft: Dict) -> Dict:
    """sop_draft를 approve_and_save_sop() 입력 포맷으로 변환한다."""
    return {
        "process_detected":    True,
        "process_name":        draft.get("process_name", ""),
        "process_description": draft.get("process_description", ""),
        "purpose":             draft.get("purpose", ""),
        "input":               draft.get("input", ""),
        "work":                draft.get("work", ""),
        "condition":           draft.get("condition", ""),
        "steps":               draft.get("steps", []),
        "reason":              "",
    }


# ==============================
# Node: sop_interactive_node
# Step-by-Step State Machine으로 SOP 데이터를 대화형으로 수집한다.
#
# Stage 순서:
#   WAITING_PROCESS_NAME  → 공정명 수집
#   WAITING_PROCESS_DESC  → 공정 설명 수집
#   WAITING_PURPOSE       → SOP 목적 수집
#   WAITING_INPUT         → 투입물(재료/도구) 수집
#   WAITING_WORK          → 핵심 작업 내용 수집
#   WAITING_CONDITION     → 전제 조건/주의사항 수집
#   WAITING_STEP          → 단계 정보 수집 (루프)
#   WAITING_STEP_MORE     → 추가 단계 여부 확인 (루프)
#   COMPLETED             → 전체 완료 → sop_approval_pending 전환
# ==============================

def sop_interactive_node(state: GlobalState) -> Dict:
    stage      = state.get("sop_collection_stage", "IDLE")
    draft      = dict(state.get("sop_draft", {}))
    user_input = (state.get("input") or state.get("voice_text") or "").strip()
    history    = state.get("conversation_history", [])

    next_stage = stage   # 기본값: 현재 Stage 유지 (추출 실패 시 재질문)
    response   = ""

    # ── 1. 공정명 ──────────────────────────────────────────────────────────────
    if stage == "WAITING_PROCESS_NAME":
        value = _extract_with_llm(user_input, "공정(작업)의 이름", "process_name")
        if value:
            draft["process_name"] = value
            next_stage = "WAITING_PROCESS_DESC"
            response = (
                f"✓ 공정명: '{value}'\n\n"
                "이 공정에 대한 **간단한 설명**을 입력해 주세요.\n"
                "(어떤 작업인지 한두 문장으로 설명해 주세요.)"
            )
        else:
            response = (
                "공정 이름을 명확하게 입력해 주세요.\n"
                "예: '치킨 튀기기', '금속 부품 용접', '포장재 조립'"
            )

    # ── 2. 공정 설명 ───────────────────────────────────────────────────────────
    elif stage == "WAITING_PROCESS_DESC":
        value = _extract_with_llm(user_input, "공정에 대한 설명 또는 개요", "process_description")
        if value:
            draft["process_description"] = value
            next_stage = "WAITING_PURPOSE"
            response = (
                "✓ 공정 설명 저장.\n\n"
                "이 SOP의 **목적**을 입력해 주세요.\n"
                "(왜 이 작업을 수행하는가?)\n"
                "예: '제품 품질 균일화', '작업자 안전 확보', '생산 공정 표준화'"
            )
        else:
            response = "공정에 대한 설명을 한두 문장으로 입력해 주세요."

    # ── 3. SOP 목적 ────────────────────────────────────────────────────────────
    elif stage == "WAITING_PURPOSE":
        value = _extract_with_llm(user_input, "이 SOP를 수행하는 목적 또는 이유", "purpose")
        if value:
            draft["purpose"] = value
            next_stage = "WAITING_INPUT"
            response = (
                "✓ 목적 저장.\n\n"
                "작업에 필요한 **투입물(재료·도구·장비·정보)**을 입력해 주세요.\n"
                "예: '닭고기 1kg, 튀김유 2L, 온도계, 튀김기'"
            )
        else:
            response = "SOP의 목적을 한 문장으로 입력해 주세요. (왜 이 작업을 하는가?)"

    # ── 4. 투입물 ──────────────────────────────────────────────────────────────
    elif stage == "WAITING_INPUT":
        value = _extract_with_llm(user_input, "작업에 필요한 재료·도구·장비·정보 목록", "input")
        if value:
            draft["input"] = value
            next_stage = "WAITING_WORK"
            response = (
                "✓ 투입물 저장.\n\n"
                "**핵심 작업 내용**을 한 문장으로 요약해 주세요.\n"
                "(무엇을 하는 작업인가?)\n"
                "예: '닭고기를 적정 온도에서 튀겨 황금색을 낸다'"
            )
        else:
            response = "작업에 필요한 재료, 도구, 장비를 입력해 주세요."

    # ── 5. 핵심 작업 내용 ──────────────────────────────────────────────────────
    elif stage == "WAITING_WORK":
        value = _extract_with_llm(user_input, "핵심 작업 내용 요약 (무엇을 하는가)", "work")
        if value:
            draft["work"] = value
            next_stage = "WAITING_CONDITION"
            response = (
                "✓ 작업 내용 저장.\n\n"
                "작업 수행을 위한 **전제 조건 또는 주의사항**을 입력해 주세요.\n"
                "예: '튀김기 예열 완료 후 작업', '보호장갑 착용 필수'\n"
                "없으면 '없음'이라고 입력해 주세요."
            )
        else:
            response = "핵심 작업 내용을 한 문장으로 요약해 주세요."

    # ── 6. 전제 조건 ───────────────────────────────────────────────────────────
    elif stage == "WAITING_CONDITION":
        # '없음' 입력도 유효한 값으로 처리
        value = user_input if user_input else None
        if value:
            draft["condition"] = value if value != "없음" else ""
            draft.setdefault("steps", [])
            next_stage = "WAITING_STEP"
            step_num   = len(draft["steps"]) + 1
            response   = (
                "✓ 조건 저장.\n\n"
                f"이제 작업 **단계**를 입력해 주세요.\n"
                f"**{step_num}단계** 정보를 자유롭게 설명해 주세요.\n"
                "(단계명, 수행 동작, 도구, 대상 물체, 안전사항 포함)\n"
                "예: '재료 준비 — 닭고기를 한 입 크기로 자른다. 도구: 칼. 안전: 손 베임 주의'"
            )
        else:
            response = (
                "작업 전제 조건이나 주의사항을 입력해 주세요.\n"
                "없으면 '없음'이라고 입력해 주세요."
            )

    # ── 7. 단계 수집 (루프 진입점) ─────────────────────────────────────────────
    elif stage == "WAITING_STEP":
        step_order = len(draft.get("steps", [])) + 1
        step_data  = _extract_step_with_llm(user_input, step_order)
        if step_data:
            steps = draft.get("steps", [])
            steps.append({
                "step_order":     step_order,
                "step_name":      step_data["step_name"],
                "action":         step_data["action"],
                "expected_tool":  step_data["expected_tool"],
                "expected_object": step_data["expected_object"],
                "safety_check":   step_data["safety_check"],
            })
            draft["steps"] = steps
            next_stage = "WAITING_STEP_MORE"
            response   = (
                f"✓ {step_order}단계 저장 완료.\n\n"
                "다음 단계가 있나요?\n"
                f"• **있으면**: {step_order + 1}단계 내용을 바로 입력해 주세요.\n"
                "• **없으면**: '완료'라고 말씀해 주세요."
            )
        else:
            response = (
                f"{step_order}단계 정보를 더 구체적으로 입력해 주세요.\n"
                "단계명과 수행 동작이 필요합니다.\n"
                "예: '기름 가열 — 튀김기 온도를 180°C로 설정해 예열한다. "
                "도구: 튀김기, 온도계. 안전: 화상 주의'"
            )

    # ── 8. 추가 단계 여부 확인 (루프 분기) ─────────────────────────────────────
    elif stage == "WAITING_STEP_MORE":
        step_count = len(draft.get("steps", []))
        result     = _classify_step_continuation(user_input, step_count)
        status     = result["status"]
        step_data  = result.get("step_data")

        if status == "DONE":
            # COMPLETED 처리는 아래 공통 블록에서 수행
            next_stage = "COMPLETED"

        elif status == "MORE_WITH_DATA" and step_data:
            # 사용자가 "다음 단계가 있나요?" 에 단계 내용을 직접 포함해 답한 경우
            next_step_order = step_count + 1
            steps = draft.get("steps", [])
            steps.append({
                "step_order":     next_step_order,
                "step_name":      step_data.get("step_name", ""),
                "action":         step_data.get("action", ""),
                "expected_tool":  step_data.get("expected_tool", ""),
                "expected_object": step_data.get("expected_object", ""),
                "safety_check":   step_data.get("safety_check", ""),
            })
            draft["steps"] = steps
            next_stage = "WAITING_STEP_MORE"
            response   = (
                f"✓ {next_step_order}단계 저장 완료.\n\n"
                "다음 단계가 있나요?\n"
                f"• **있으면**: {next_step_order + 1}단계 내용을 바로 입력해 주세요.\n"
                "• **없으면**: '완료'라고 말씀해 주세요."
            )

        else:  # MORE_NO_DATA: 추가 단계 있지만 내용 미입력
            next_step_order = step_count + 1
            next_stage = "WAITING_STEP"
            response   = (
                f"{next_step_order}단계 정보를 입력해 주세요.\n"
                "(단계명, 수행 동작, 도구, 대상, 안전사항)\n"
                "예: '포장 — 완성된 제품을 포장 용기에 담는다. "
                "도구: 포장 용기. 안전: 온도 주의'"
            )

    # ── COMPLETED: 수집 완료 → sop_approval_pending 으로 전환 ────────────────
    if next_stage == "COMPLETED":
        gen_result = _draft_to_gen_result(draft)
        preview    = _build_sop_preview(gen_result)
        response   = (
            "✓ 모든 SOP 정보 수집이 완료되었습니다!\n\n"
            f"{preview}\n\n"
            "이대로 저장하시겠습니까? (저장 / 수정 / 취소)"
        )
        updated_history = history + [{"role": "assistant", "content": response}]
        return {
            "sop_collection_stage":  "IDLE",       # 수집 Stage 초기화
            "sop_draft":             {},            # draft 초기화
            "sop_generation_result": gen_result,   # 승인 노드에서 사용
            "sop_approval_pending":  True,          # 다음 요청 → sop_approval_node
            "response_message":      response,
            "conversation_history":  updated_history,
            "final_decision":        "notice",
            "final_score":           0,
        }

    # 일반 Stage 응답 반환
    updated_history = history + [{"role": "assistant", "content": response}]
    return {
        "sop_draft":            draft,
        "sop_collection_stage": next_stage,
        "response_message":     response,
        "conversation_history": updated_history,
        "final_decision":       "notice",
        "final_score":          0,
    }


# ==============================
# Node: sop_agent
# 기존 SOP 대비 이탈 검증
# ==============================

def sop_agent_node(state: GlobalState) -> Dict:
    print("sop_agent_node")
    result = run_sop_agent(state["observation"])
    return {"sop_validation_result": result}


# ==============================
# Node: sop_generator_agent
# 신규 SOP 생성 후 승인 대기 상태로 전환
# ==============================

def sop_generator_node(state: GlobalState) -> Dict:
    print("sop_generator_node")
    result = run_sop_create_agent(state["observation"])
    if result:
        return {
            "sop_generation_result": result,
            "sop_approval_pending":  True,   # 승인 대기 시작
        }
    return {"sop_generation_result": {}}


# ==============================
# Node: orchestrator
# 최종 위험 점수 산출 + LLM 자연어 응답
# SOP 생성 직후엔 미리보기 제공
# ==============================

def orchestrator(state: GlobalState) -> Dict:
    safety  = state.get("safety_result", {})
    process = state.get("process_result", {})
    sop     = state.get("sop_generation_result") or state.get("sop_validation_result", {})
    history = state.get("conversation_history", [])

    # approval_node 또는 다른 노드가 이미 응답을 만든 경우 건너뜀
    if state.get("response_message"):
        return {}

    # SOP가 방금 생성되어 승인 대기 상태인 경우 → 미리보기 제공
    if state.get("sop_approval_pending") and state.get("sop_generation_result"):
        preview  = _build_sop_preview(state["sop_generation_result"])
        response = (
            f"새 공정의 SOP를 생성했습니다:\n\n{preview}\n\n"
            "저장하시겠습니까? (저장 / 수정 / 취소)"
        )
        updated_history = history + [{"role": "assistant", "content": response}]
        return {
            "final_decision":       "notice",
            "final_score":          0,
            "response_message":     response,
            "conversation_history": updated_history,
        }

    # ── 위험 점수 산출 ──
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

    # ── LLM 자연어 응답 생성 (최근 6턴 대화 이력 반영) ──
    recent_history = history[-6:] if len(history) > 6 else history
    history_text   = "\n".join(
        f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}"
        for m in recent_history
    ) or "없음"

    analysis_summary = (
        f"- 안전 위험도: {safety.get('risk_level', '없음')} — {safety.get('reason', '')}\n"
        f"- 공정 이상:   {'감지됨' if process.get('anomaly') else '없음'} — {process.get('reason', '')}\n"
        f"- SOP:         {'이탈' if sop.get('deviation') else '준수'} — {sop.get('reason', '')}\n"
        f"- 종합 위험 점수: {score}점 ({decision})"
    )

    prompt = f"""당신은 스마트팩토리 AI 안전 관리 어시스턴트입니다.
이전 대화 맥락을 이어받아 현재 분석 결과를 자연스럽게 설명하십시오.

### 최근 대화 기록
{history_text}

### 현재 분석 결과
{analysis_summary}

### 응답 지침
- 이전 대화를 자연스럽게 이어서 응답하라
- 위험도에 맞는 톤으로 응답하라 (HIGH→즉각 경고, MEDIUM→주의, LOW→안내)
- 필요한 조치가 있으면 구체적으로 안내하라
- 150자 이내의 자연스러운 한국어 텍스트로만 응답하라 (JSON 금지)
"""
    try:
        res              = llm_chat.invoke(prompt)
        response_message = res.content.strip()
    except Exception:
        response_message = f"분석 완료: 위험도 {safety.get('risk_level', '알 수 없음')}, 종합 점수 {score}점."

    updated_history = history + [{"role": "assistant", "content": response_message}]
    return {
        "final_decision":       decision,
        "final_score":          score,
        "response_message":     response_message,
        "conversation_history": updated_history,
    }


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(GlobalState)

_builder.add_node("init",                 init_node)
_builder.add_node("voice",               voice_node)
_builder.add_node("image",               image_node)
_builder.add_node("merge",               merge_node)
_builder.add_node("safety_agent",        safety_node)
_builder.add_node("process_agent",       process_node)
_builder.add_node("collect_results",     collect_results)
_builder.add_node("sop_approval_node",   sop_approval_node)
_builder.add_node("propose_sop_creation", propose_sop_creation_node)
_builder.add_node("sop_creation_intent", sop_creation_intent_node)
_builder.add_node("sop_interactive_node", sop_interactive_node)  # Step-by-Step 수집
_builder.add_node("sop_agent",           sop_agent_node)
_builder.add_node("orchestrator",        orchestrator)

_builder.set_entry_point("init")
_builder.add_edge("init",  "voice")
_builder.add_edge("voice", "image")
_builder.add_edge("image", "merge")

# 병렬 fan-out
_builder.add_edge("merge", "safety_agent")
_builder.add_edge("merge", "process_agent")

# fan-in
_builder.add_edge("safety_agent",  "collect_results")
_builder.add_edge("process_agent", "collect_results")

# collect 후 5방향 분기
_builder.add_conditional_edges(
    "collect_results",
    route_after_collect,
    {
        "sop_interactive_node":    "sop_interactive_node",  # ① 수집 진행 중 (최우선)
        "sop_approval_node":       "sop_approval_node",     # ② 저장 승인 대기
        "sop_creation_intent_node": "sop_creation_intent",  # ③ 생성 동의 분류
        "propose_sop_creation":    "propose_sop_creation",  # ④ 신규 공정 제안
        "sop_agent":               "sop_agent",             # ⑤ 기존 SOP 검증
    },
)

# sop_approval 후 분기: 응답 완료 → END, CHAT → orchestrator
_builder.add_conditional_edges(
    "sop_approval_node",
    route_after_approval,
    {
        "END":          END,
        "orchestrator": "orchestrator",
    },
)

# 신규 공정 제안 → orchestrator (response_message 이미 설정됨 → orchestrator skip 후 END)
_builder.add_edge("propose_sop_creation", "orchestrator")

# SOP 생성 동의/거부 분류 → 항상 END
# (AGREE: 다음 요청에서 sop_interactive_node 진입, REJECT: 완료)
_builder.add_edge("sop_creation_intent", END)

# 대화형 수집 → orchestrator (response_message 이미 설정됨 → orchestrator skip 후 END)
_builder.add_edge("sop_interactive_node", "orchestrator")

# SOP 검증 → orchestrator
_builder.add_edge("sop_agent", "orchestrator")

_builder.add_edge("orchestrator", END)

graph = _builder.compile()


# ==============================
# FastAPI
# ==============================
# (이하 FastAPI 코드는 기존과 동일하게 유지하시면 됩니다)
# ...

app = FastAPI(title="Smart Factory Multi-Agent API")


class ChatResponse(BaseModel):
    response:   str   # LLM이 생성한 자연어 응답
    log_level:  str   # "danger" | "warn" | "info" | "notice"
    diff_score: int   # 위험 점수


@app.post("/sop", response_model=ChatResponse)
async def chat(
    input:      Optional[str]          = Form(None),
    voice_file: Optional[UploadFile]   = File(None),
    image_file: Optional[UploadFile]   = File(None),
    session_id: str                    = Form(...),
):
    state = get_state(session_id)

    # ── 임시 파일 저장 ──
    tmp_paths = []

    if voice_file:
        content = await voice_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(content)
            state["voice_path"] = tmp.name
            tmp_paths.append(tmp.name)

    if image_file:
        content = await image_file.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(content)
            state["image_path"] = tmp.name
            tmp_paths.append(tmp.name)

    if input:
        state["input"] = input

    # ── 그래프 실행 ──
    # SOP 저장/수정/거부는 sop_approval_node가 대화로 처리
    updated_state = graph.invoke(state)

    # ── 세션 저장 후 per-request 입력 필드 초기화 ──
    SESSION_STORE[session_id] = updated_state
    SESSION_STORE[session_id]["voice_path"]  = None
    SESSION_STORE[session_id]["image_path"]  = None
    SESSION_STORE[session_id]["input"]       = None
    SESSION_STORE[session_id]["voice_text"]  = None
    SESSION_STORE[session_id]["image_analysis"] = None

    # ── 임시 파일 삭제 ──
    for path in tmp_paths:
        try:
            os.unlink(path)
        except OSError:
            pass

    decision         = updated_state.get("final_decision", "info")
    score            = updated_state.get("final_score", 0)
    response_message = updated_state.get("response_message", "")

    level_map = {"danger": "danger", "warn": "warn", "info": "info", "notice": "notice"}
    level     = level_map.get(decision, "notice")

    return ChatResponse(
        response=response_message or decision,
        log_level=level,
        diff_score=score,
    )


# ==============================
# 진입점
# ==============================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)
