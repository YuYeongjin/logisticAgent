import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_experimental.sql import SQLDatabaseChain


class GraphState(TypedDict):
    input: str
    target_wh: Optional[str] # 분석된 타겟 창고
    response: Optional[str]


models = {
    "A": joblib.load("model_Whse_A.pkl"),
    "C": joblib.load("model_Whse_C.pkl"),
    "J": joblib.load("model_Whse_J.pkl"),
    "S": joblib.load("model_Whse_S.pkl")
}
le_product = joblib.load("le_product.pkl")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)


def retrieve_from_db(state: GraphState) -> GraphState:
    print("--- 질문 분석 중 (창고 분류) ---")
    prompt = f"질문: {state['input']}\n이 질문은 A, C, J, S 창고 중 어디에 대한 것인지 알파벳 한 글자로만 답해. 해당 없으면 'unknown'이라고 해."
    res = llm.invoke(prompt)
    target = res.content.strip().upper()
    return {"target_wh": target}

def run_llm(state: GraphState) -> GraphState:
    print("--- AI로 답변 생성 중... ---")
    response = llm.invoke(state["input"])
    return {"response": response.content}
def run_model_a(state: GraphState) -> GraphState:
    print("--- a model... ---")
    response = llm.invoke(state["input"])
    return {"response": response.content}
def run_model_c(state: GraphState) -> GraphState:
    print("--- c model... ---")
    response = llm.invoke(state["input"])
    return {"response": response.content}

def run_model_j(state: GraphState) -> GraphState:
    print("--- j model... ---")
    response = llm.invoke(state["input"])
    return {"response": response.content}

def run_model_s(state: GraphState) -> GraphState:
    print("--- s model... ---")
    response = llm.invoke(state["input"])
    return {"response": response.content}

def return_retrieved(state: GraphState) -> GraphState:
    print("--- DB 결과 반환 중... ---")
    return {"response": state["retrieved"]}

def should_use_retrieved(state: GraphState) -> str:
    if state["retrieved"] and "null" not in state["retrieved"].lower():
        return "use_retrieved"
    if state["retrieved"] and "a" not in state["retrieved"].lower():
        return "run_model_a"
    if state["retrieved"] and "c" not in state["retrieved"].lower():
        return "run_model_c"
    if state["retrieved"] and "j" not in state["retrieved"].lower():
        return "run_model_j"
    if state["retrieved"] and "s" not in state["retrieved"].lower():
        return "run_model_s"
    return "use_llm"

builder = StateGraph(GraphState)
builder.add_node("retrieve", retrieve_from_db)
builder.add_node("use_llm", run_llm)
builder.add_node("use_retrieved", return_retrieved)

builder.add_node("run_model_a", run_model_a)
builder.add_node("run_model_c", run_model_c)
builder.add_node("run_model_j", run_model_j)
builder.add_node("run_model_s", run_model_s)
builder.add_edge("run_model_a","use_llm")
builder.add_edge("run_model_c","use_llm")
builder.add_edge("run_model_j","use_llm")
builder.add_edge("run_model_s","use_llm")

builder.set_entry_point("retrieve")
builder.add_conditional_edges("retrieve", should_use_retrieved, {
    "use_llm": "use_llm",
    "use_retrieved": "use_retrieved",
    "run_model_a":"run_model_a",
    "run_model_c":"run_model_c",
    "run_model_j":"run_model_j",
    "run_model_s":"run_model_s"
})
builder.set_finish_point("use_llm")
builder.set_finish_point("use_retrieved")

graph = builder.compile()

# 6. 실행 (Main)
if __name__ == "__main__":
    print("=== 물류 AI 에이전트  ===")
    user_input = input("항목을 입력하세요: ")
    result = graph.invoke({"input": user_input})
    print("\n[최종 답변]:", result["response"])