"""
SopQuestionAgent - 신규 SOP 승인을 위한 대화형 질문 생성 에이전트

Graph:
    generate_questions → evaluate_completion
"""
import json
from typing import TypedDict, Dict, List, Optional

from langgraph.graph import StateGraph

from agents.config import llm_json


# ==============================
# State
# ==============================

class SopQuestionState(TypedDict):
    sop_generation_result:  Dict
    sop_questions:          Optional[List[Dict]]
    current_question_index: int
    user_answers:           Dict[str, str]
    is_completed:           bool
    pending_questions:      List[Dict]


# ==============================
# Node 1: 확인 질문 생성 (LLM)
# ==============================

def generate_questions(state: SopQuestionState) -> SopQuestionState:
    # 이미 질문이 생성된 경우(재진입) 건너뜀
    if state.get("sop_questions") is not None:
        return state

    sop = state["sop_generation_result"]

    prompt = f"""
당신은 스마트팩토리 SOP 검증 AI입니다.
새로 생성된 SOP가 실제 작업 환경에 적합한지 확인하기 위해
작업자에게 확인해야 할 질문을 3~5개 생성하십시오.

### 생성된 SOP
{json.dumps(sop, ensure_ascii=False, indent=2)}

### 질문 작성 기준
- 작업 절차의 정확성 확인
- 사용 도구/장비의 적합성 확인
- 안전 수칙 준수 여부 확인

반드시 아래 JSON 형식으로만 응답:
{{
  "questions": [
    {{"id": 1, "question": "질문 내용", "answer": ""}}
  ]
}}
"""
    try:
        res  = llm_json.invoke(prompt)
        data = json.loads(res.content)
        state["sop_questions"] = data.get("questions", [])
    except (json.JSONDecodeError, KeyError):
        state["sop_questions"] = []

    return state


# ==============================
# Node 2: 완료 여부 평가
# ==============================

def evaluate_completion(state: SopQuestionState) -> SopQuestionState:
    questions = state.get("sop_questions") or []
    unanswered = [q for q in questions if not q.get("answer")]

    state["pending_questions"] = unanswered
    state["is_completed"]      = len(unanswered) == 0

    return state


# ==============================
# Graph 빌드
# ==============================

_builder = StateGraph(SopQuestionState)
_builder.add_node("generate_questions",   generate_questions)
_builder.add_node("evaluate_completion",  evaluate_completion)

_builder.set_entry_point("generate_questions")
_builder.add_edge("generate_questions",  "evaluate_completion")
_builder.set_finish_point("evaluate_completion")

sop_question_graph = _builder.compile()


# ==============================
# 공개 인터페이스
# ==============================

def run_sop_question_agent(state: Dict) -> Dict:
    """
    현재 세션 state를 받아 질문 생성/평가 후 업데이트된 필드를 반환한다.

    Returns:
        {
            "sop_questions":          list,
            "current_question_index": int,
            "user_answers":           dict,
            "is_completed":           bool,
            "pending_questions":      list,
        }
    """
    result = sop_question_graph.invoke({
        "sop_generation_result":  state.get("sop_generation_result", {}),
        "sop_questions":          state.get("sop_questions"),
        "current_question_index": state.get("current_question_index", 0),
        "user_answers":           state.get("user_answers", {}),
        "is_completed":           state.get("is_completed", False),
        "pending_questions":      [],
    })
    return {
        "sop_questions":          result["sop_questions"],
        "current_question_index": result["current_question_index"],
        "user_answers":           result["user_answers"],
        "is_completed":           result["is_completed"],
        "pending_questions":      result["pending_questions"],
    }
