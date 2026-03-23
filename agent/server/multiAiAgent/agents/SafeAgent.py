"""
SafeAgent - 작업 현장 안전 평가 에이전트

Graph:
    parse_vision → assess_safety
"""
import json
from typing import TypedDict, Dict, List

from langgraph.graph import StateGraph

from agents.config import llm_json


# ==============================
# State
# ==============================

class SafetyState(TypedDict):
    observation:    Dict
    vision_context: Dict
    risk_level:     str   # "LOW" | "MEDIUM" | "HIGH"
    risk_reason:    str
    anomaly:        bool


# ==============================
# Node 1: 비전 데이터 파싱
# ==============================

def parse_vision(state: SafetyState) -> SafetyState:
    obs    = state["observation"]
    vision = obs.get("vision") or {}
    scene  = vision.get("scene") or {}

    objects  = [o["label"] for o in vision.get("objects", [])]
    poses    = vision.get("poses", [])
    relations = vision.get("relations", [])

    state["vision_context"] = {
        "objects":         objects,
        "ppe_status":      vision.get("ppe_status", {}),
        "human_activity":  scene.get("human_activity", ""),
        "scene_risk":      scene.get("risk", ""),
        "tools":           scene.get("tools", []),
        "environment":     scene.get("environment", ""),
        "relations":       relations,
        "worker_count":    objects.count("person"),
    }
    return state


# ==============================
# Node 2: LLM 안전 평가
# ==============================

def assess_safety(state: SafetyState) -> SafetyState:
    obs = state["observation"]
    ctx = state["vision_context"]

    prompt = f"""
당신은 스마트팩토리 안전 관리 AI입니다.
아래 작업 현장 데이터를 분석하여 안전 위험 수준을 평가하십시오.

### 작업 정보
텍스트 입력: {obs.get("text") or "없음"}
음성 입력:   {obs.get("voice") or "없음"}

### 비전 분석 결과
감지된 객체:    {ctx.get("objects", [])}
작업자 수:      {ctx.get("worker_count", 0)}명
PPE 착용 상태:  {json.dumps(ctx.get("ppe_status", {}), ensure_ascii=False)}
작업자 활동:    {ctx.get("human_activity", "")}
사용 도구:      {ctx.get("tools", [])}
환경:           {ctx.get("environment", "")}
장면 위험도:    {ctx.get("scene_risk", "")}
객체 근접 관계: {json.dumps(ctx.get("relations", []), ensure_ascii=False)}

### 위험 수준 기준
- HIGH:   즉각적 위험 (PPE 미착용 + 위험 도구 근접, 작업자 부상 위험 있음)
- MEDIUM: 잠재적 위험 (일부 PPE 미착용, 위험 요소 근접)
- LOW:    안전한 상태 (모든 안전 수칙 준수)

반드시 아래 JSON 형식으로만 응답:
{{
  "risk_level": "HIGH" | "MEDIUM" | "LOW",
  "reason":     "한국어로 위험 근거 설명",
  "anomaly":    true | false
}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        state["risk_level"] = data.get("risk_level", "LOW")
        state["risk_reason"] = data.get("reason", "")
        state["anomaly"]    = data.get("anomaly", False)
    except (json.JSONDecodeError, KeyError):
        state["risk_level"] = "LOW"
        state["risk_reason"] = "안전 분석 실패 - 기본값 적용"
        state["anomaly"]    = False

    return state


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(SafetyState)
_builder.add_node("parse_vision",  parse_vision)
_builder.add_node("assess_safety", assess_safety)

_builder.set_entry_point("parse_vision")
_builder.add_edge("parse_vision", "assess_safety")
_builder.set_finish_point("assess_safety")

safety_graph = _builder.compile()


# ==============================
# 공개 인터페이스
# ==============================

def run_safety_agent(observation: Dict) -> Dict:
    """
    Returns:
        {"risk_level": str, "reason": str, "anomaly": bool}
    """
    result = safety_graph.invoke({
        "observation":    observation,
        "vision_context": {},
        "risk_level":     "LOW",
        "risk_reason":    "",
        "anomaly":        False,
    })
    return {
        "risk_level": result["risk_level"],
        "reason":     result["risk_reason"],
        "anomaly":    result["anomaly"],
    }
