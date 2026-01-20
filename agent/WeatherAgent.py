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
    target_prod: Optional[str]
    target_date: Optional[str]
    target_temp: Optional[str] # 맑음, 비 , 등
    weather_info: Optional[str]  # 온도
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
    당신은 날씨 알리미입니다. 사용자의 질문을 분석하여 무작위 날짜에 서울의 온도와 날씨를 검색해서 알려줘
    - 설명이나 인사말 없이 오직 결과의 형태는 [온도 : 00도, 날씨 : 맑음] 형태로만 해
    질문: {state['input']}
    """
    res = llm.invoke(prompt)
    print(f" == prompt 결과 : {res.content} == ")
    
    temp = int(re.search(r'온도\s*:\s*(-?\d+)', res.content).group(1))
    return {"weather_info": res.content, "target_temp": str(temp)}

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
    prod_match = re.search(r'PRODUCT_\d+', state['input'].upper())
    target_prod = prod_match.group(0) if prod_match else "AUTO_SELECT"
    
    print(f" == 추출 결과 - 창고: {target}, 제품: {target_prod} == ")
    return {"target_wh": target, "target_product": target_prod}
def run_wh_model(state: GraphState) -> GraphState:
    wh = state["target_wh"]
    prod_name = state.get("target_product", "AUTO_SELECT")
    weather_text = state.get("weather_info", "평이한 날씨")
    
    print(f"--- [에이전트] {wh} 창고 예측 수행 중 ---")

    try:
        # 1. 상품 선택 로직: AUTO_SELECT일 경우 첫 번째 상품 선택
        if prod_name == "AUTO_SELECT":
            prod_name = le_product.classes_[0] # 첫 번째 상품 자동 선택
            print(f"--- [자동 선택] {prod_name}으로 예측을 진행합니다 ---")

        # 2. ML 모델 기준점 계산
        prod_n = le_product.transform([prod_name])[0]
        # 현재 날짜 기준 월(Month) 추출 (예: 1월)
        current_month = 1 
        sample_X = pd.DataFrame([[current_month, 0, prod_n]], columns=['Month', 'Category_n', 'Product_n'])
        base_pred = models[wh].predict(sample_X)[0]

        # 3. LLM에게 날씨 기반 보정치 요청
        reasoning_prompt = f"""
        날씨 정보: {weather_text}
        위 날씨가 물류 수요에 미칠 영향(보정 계수)을 숫자만 답하세요. (예: 1.1)
        """
        adj_res = llm.invoke(reasoning_prompt)
        # 숫자만 추출하기 위한 처리
        adjustment = float(re.search(r"[-+]?\d*\.\d+|\d+", adj_res.content).group())

        final_pred = base_pred * adjustment
        
        report = f"{final_pred:.2f}개 (기본:{base_pred:.2f} * 보정:{adjustment})"
        return {"response": report, "target_product": prod_name}

    except Exception as e:
        return {"response": f"예측 처리 오류: {e}", "target_product": "UNKNOWN"}

def run_general_llm(state: GraphState) -> GraphState:
    print("--- LLM 에이전트 ---")
    res = llm.invoke(state["input"])
    return {"response": res.content}

def run_finish_llm(state: GraphState) -> GraphState:
    print("--- 분석 결과 요약 중 ---")
    
    # 이전 노드에서 저장된 데이터 활용
    weather = state.get('weather_info', '정보 없음')
    prediction_report = state.get('response', '예측 불가')
    product = state.get('target_product', '해당 상품')
    
    prompt = f"""
    당신은 물류 요약 에이전트입니다. 다음 데이터를 바탕으로 한 문장으로 핵심만 리포트하세요.
    
    데이터:
    - 날씨: {weather}
    - 예측: {prediction_report}
    - 상품: {product}
    
    형식: "[상품명]은 [날씨] 조건에서 [예측수요]의 수요가 예상되어 [상태/권고] 상태입니다."
    설명 없이 위 형식에 맞춰서 딱 한 줄만 출력해.
    """
    
    res = llm.invoke(prompt)
    return {"response": res.content.strip()}

# --- 조건부 엣지 ---
def router_logic(state: GraphState) -> str:
    if state["target_wh"] in ["A", "C", "J", "S"]:
        return "use_model"
    return "use_llm"

builder = StateGraph(GraphState)

builder.add_node("start", analyze_weather)
builder.add_node("router", analyze_warehouse)
builder.add_node("ml_agent", run_wh_model)
builder.add_node("llm_agent", run_general_llm)
builder.add_node("run_finish_llm",run_finish_llm)
builder.add_edge("ml_agent", "run_finish_llm")
builder.add_edge("start","router")
builder.set_entry_point("start")
builder.add_conditional_edges("router", router_logic, {
    "use_model": "ml_agent",
    "use_llm": "llm_agent"
})

builder.set_finish_point("run_finish_llm")
builder.set_finish_point("llm_agent")

graph = builder.compile()
# 실행 (Main)
if __name__ == "__main__":
    print("=== 물류 AI 에이전트  ===")
    user_input = input("항목을 입력하세요: ")
    result = graph.invoke({"input": user_input})
    print("\n", result["response"])