from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph
import random

class AgentState(TypedDict):
    input_data: Dict[str, Any]
    risk_score: float
    recommendation: str

def detect_safety(input_data: Dict[str, Any]) -> float:
    # TODO: 실제 안전 모델로 교체
    return random.uniform(0, 1)

def safety_analyze(state: AgentState):
    state["risk_score"] = detect_safety(state["input_data"])
    return state

def safety_decide(state: AgentState):
    state["recommendation"] = (
        "EMERGENCY_STOP" if state["risk_score"] > 0.8 else "OK"
    )
    return state

def build_safety_agent():
    graph = StateGraph(AgentState)
    graph.add_node("analyze", safety_analyze)
    graph.add_node("decide", safety_decide)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "decide")
    graph.set_finish_point("decide")

    return graph.compile()

safety_agent_app = build_safety_agent()