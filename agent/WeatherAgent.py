import re
import os
import joblib
from typing import TypedDict, Optional
from langgraph.graph import StateGraph
from langchain_google_genai import ChatGoogleGenerativeAI
import pandas as pd
import numpy as np


class GraphState(TypedDict):
    input: str
    target_wh: Optional[str]
    target_date: Optional[str]
    weather_info: Optional[str]  # 새로 추가: 외부에서 가져온 날씨 정보
    response: Optional[str]

models = {
    "A": joblib.load("model_Whse_A.pkl"),
    "C": joblib.load("model_Whse_C.pkl"),
    "J": joblib.load("model_Whse_J.pkl"),
    "S": joblib.load("model_Whse_S.pkl")
}
le_product = joblib.load("le_product.pkl")

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
def analyze_weather(state: GraphState) -> GraphState:
    print("--- 질문 분석 중 (날짜의 날씨) ---")
    prompt = f"""
    당신은 날씨 알리미입니다. 사용자의 질문을 분석하여 그 날의 온도와 날씨를 검색해서 알려줘
    - 설명이나 인사말 없이 오직 결과의 형태는 이 형태로만 해 [온도 : 00도, 날씨 : 맑음]
    질문: {state['input']}
    """
    res = llm.invoke(prompt)
    
    print(f" == prompt 결과 : {res} == ")
    return {"weather_info": res}

def analyze_warehouse(state: GraphState) -> GraphState:
    print("--- 질문 분석 중 (창고 분류) ---")
    prompt = f"""
    당신은 창고 분류기입니다. 사용자의 질문을 분석하여 반드시 다음 중 한 글자만 출력해.
    - 대상 창고: A, C, J, S
    - 해당하는 창고가 없으면 반드시 'UNKNOWN'이라고만 답해.
    - 설명이나 인사말 없이 오직 한 단어만 출력해.
    질문: {state['input']}
    """
    res = llm.invoke(prompt)
    # 전처리가 없을 수도 있으나, 필요할 수도 있음...
    # 전처리: 공백 제거, 대문자 변환, 그리고 첫 번째 알파벳만 추출
    raw_target = res.content.strip().upper()
    print("-- raw_target : " + raw_target + " --")
    
    # 정규표현식을 사용하여 응답 중 A, C, J, S, UNKNOWN 키워드만 추출
    match = re.search(r'\b(A|C|J|S|UNKNOWN)\b', raw_target)
    target = match.group(0) if match else "UNKNOWN"
    
    print(f" == prompt 결과 : {target} == ")
    return {"target_wh": target}

def run_wh_model(state: GraphState) -> GraphState:
    wh = state["target_wh"]
    prod_name = state.get("target_product", "UNKNOWN")
    
    print(f"--- {wh} 창고 에이전트 가동 ---")

    # 제품명이 UNKNOWN이거나 목록을 요청하는 경우
    if prod_name == "UNKNOWN" or "리스트" in state["input"] or "목록" in state["input"]:
        # 인코더에서 학습된 모든 제품명 중 상위 10개만 추출
        all_products = le_product.classes_
        sample_list = ", ".join(all_products[:10]) 
        
        response = (
            f"{wh} 창고 모델이 분석 가능한 제품은 총 {len(all_products)}개입니다.\n"
            f"주요 제품 예시: {sample_list} 등이 있습니다.\n"
            "원하시는 제품 코드를 입력하시면 수요를 예측해 드릴게요!"
        )
        return {"response": response}

    # 실제 제품 코드가 들어온 경우 (예측 로직)
    try:
        # 제품명을 숫자로 변환
        prod_n = le_product.transform([prod_name])[0]
        
        # 모델 입력 (Month: 1, Category: 0으로 가정)
        sample_X = pd.DataFrame([[1, 0, prod_n]], columns=['Month', 'Category_n', 'Product_n'])
        pred = models[wh].predict(sample_X)[0]
        
        response = f"[{wh} 창고] {prod_name} 제품의 예상 수요량은 {pred:.2f}개입니다."
    except Exception as e:
        response = f"해당 창고에서 제품 코드 '{prod_name}'를 찾을 수 없습니다. '제품 리스트 보여줘'라고 입력해 보세요."
    
    return {"response": response}

def run_general_llm(state: GraphState) -> GraphState:
    print("--- LLM 에이전트 ---")
    res = llm.invoke(state["input"])
    return {"response": res.content}

# --- 조건부 엣지 ---
def router_logic(state: GraphState) -> str:
    if state["target_wh"] in ["A", "C", "J", "S"]:
        return "use_model"
    return "use_llm"

builder = StateGraph(GraphState)

builder.add_node("router", analyze_warehouse)
builder.add_node("ml_agent", run_wh_model)
builder.add_node("llm_agent", run_general_llm)

builder.set_entry_point("router")
builder.add_conditional_edges("router", router_logic, {
    "use_model": "ml_agent",
    "use_llm": "llm_agent"
})

builder.set_finish_point("ml_agent")
builder.set_finish_point("llm_agent")

graph = builder.compile()
# 실행 (Main)
if __name__ == "__main__":
    print("=== 물류 AI 에이전트  ===")
    user_input = input("항목을 입력하세요: ")
    result = graph.invoke({"input": user_input})
    print("\n", result["response"])