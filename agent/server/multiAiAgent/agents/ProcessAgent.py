from typing import TypedDict, Dict, Any
from langgraph.graph import StateGraph
import random

class AgentState(TypedDict):
    input_data: Dict[str, Any]
    risk_score: float
    recommendation: str

def analyze_process(input_data: Dict[str, Any]) -> float:
    # TODO: 실제 이미지 분석 모델로 교체
    return random.uniform(0, 1)

def process_analyze(state: AgentState):
    state["risk_score"] = analyze_process(state["input_data"])
    return state

def process_decide(state: AgentState):
    state["recommendation"] = (
        "STOP_PROCESS" if state["risk_score"] > 0.7 else "CONTINUE"
    )
    return state

def build_process_agent():
    graph = StateGraph(AgentState)
    graph.add_node("analyze", process_analyze)
    graph.add_node("decide", process_decide)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "decide")
    graph.set_finish_point("decide")

    return graph.compile()

process_agent_app = build_process_agent()