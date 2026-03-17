# import re
# import os
# import joblib
# from typing import TypedDict, Optional
# from langgraph.graph import StateGraph
# from langchain_google_genai import ChatGoogleGenerativeAI
# import pandas as pd
# import numpy as np
# from datetime import datetime


# class GraphState(TypedDict):
#     input: str

#     target_wh: Optional[list[str]]
#     target_product: Optional[list[str]]
#     target_category: Optional[list[str]]

#     weather: Optional[dict]  
#     temperature: Optional[float]
#     rain_flag: Optional[int]
#     wind_speed: Optional[float]
#     humidity: Optional[int]

#     response: Optional[str]
#     analyze_prompt: Optional[str]

# # 머신러닝 모델
# models = {
#     "A": joblib.load("model_Whse_A.pkl"),
#     "C": joblib.load("model_Whse_C.pkl"),
#     "J": joblib.load("model_Whse_J.pkl"),
#     "S": joblib.load("model_Whse_S.pkl")
# }
# # 인덱스 모델 
# le_product = joblib.load("le_product.pkl")
# le_category = joblib.load("le_category.pkl")
# product_category_map = joblib.load("product_category_map.pkl")
# # LLM은 제미나이
# llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite", temperature=0)
# #gemini-3.0-flash , gemini-2.5-flash , gemini-2.5-flash-lite

# def analyze_prompt(state: GraphState) -> GraphState:
#     print("=Prompt 분석중=")
#     prompt = f"""
#     당신은 veneta multi 물류 AI agent입니다. 질문을 분석하여 다음 형식으로만 답하세요.
#     - 일반 질문인 경우: [질문: 일반]
#     - 물류/창고 질문인 경우: [질문: 물류, 창고: A, 제품: Product_0979] (창고는 A,C,J,S 중 선택, 전체)
#     질문: {state['input']}
#     """
    
#     res = llm.invoke(prompt)
#     print(f" = prompt 분석 결과 :  {res.content} = ")
#     content = res.content

#     prom_match = re.search(r'질문\s*:\s*([^,\]\s]+)', content)
#     prom = prom_match.group(1) if prom_match else "일반"

#     if prom == '물류': 
#         wh = re.search(r'창고\s*:\s*([^,\]\s]+)', content)
#         prod = re.search(r'제품\s*:\s*([^,\]\s]+)', content)

#         wh_val = wh.group(1) if wh else "UNKNOWN"
#         prod_val = prod.group(1) if prod else "AUTO_SELECT"

#         wh_list = (
#             list(models.keys()) if wh_val == "전체"
#             else [wh_val]
#         )

#         prod_list = (
#             [] if prod_val in ["전체", "AUTO_SELECT"]
#             else [prod_val]
#         )

#         return {
#             "analyze_prompt": "물류",
#             "target_wh": wh_list,
#             "target_product": prod_list
#         }
#     return {"analyze_prompt": prom}

# def analyze_weather(state: GraphState) -> GraphState:
#     weather = state.get("weather", {})

#     temp = float(weather.get("T1H", 0))
#     rain = float(weather.get("RN1", 0))
#     pty = int(weather.get("PTY", 0))
#     wind = float(weather.get("WSD", 0))
#     reh = int(weather.get("REH", 0))

#     return {
#         "temperature": temp,
#         "rain_flag": 1 if (rain > 0 or pty > 0) else 0,
#         "wind_speed": wind,
#         "humidity": reh
#     }


# def run_wh_model(state: GraphState) -> GraphState:
#     print("=== Warehouse Predict Agent ===")
#     wh_list = state.get("target_wh", [])
#     prod_list = state.get("target_product", [])

#     results = []

#     for wh in wh_list:
#         if wh not in models:
#             continue

#         # 상품이 비어 있으면 → 전체 상품 평가
#         products = prod_list if prod_list else le_product.classes_

#         for prod_name in products:
#             if prod_name not in le_product.classes_:
#                 continue

#             try:
#                 prod_n = le_product.transform([prod_name])[0]
#                 cat_name = product_category_map.get(prod_name, "기타")
#                 category_n = le_category.transform([cat_name])[0]

#                 sample_X = pd.DataFrame([[
#                     datetime.now().month,
#                     category_n,
#                     prod_n
#                 ]], columns=["Month", "Category_n", "Product_n"])

#                 pred = float(models[wh].predict(sample_X)[0])

#                 results.append({
#                     "warehouse": wh,
#                     "product": prod_name,
#                     "category": cat_name,
#                     "pred": pred
#                 })

#             except Exception:
#                 continue

#     sorted_results = sorted(results, key=lambda x: x["pred"], reverse=True)
#     print(f"results :  {sorted_results[:5]}")
#     return {"response": sorted_results[:5]}

# def run_general_llm(state: GraphState) -> GraphState:
#     print("--- LLM 에이전트 ---")
#     prompt = f"""
#     당신은 veneta reserve AI agent입니다. 
#     한글로 친절하게 존댓말로 짧게 답변을 하세요.
#     질문: {state['input']}
#     """
#     res = llm.invoke(prompt)
#     return {"response": res.content}

# def run_finish_llm(state: GraphState) -> GraphState:
#     print("--- 분석 결과 요약 중 ---")
    
#     temp = state.get("temperature",{})
#     rain = state.get("rain_flag",{})
#     wind = state.get("wind_speed",{})
#     hum = state.get("humidity",{})
#     base_val = state.get('response', '0') 
#     product = state.get('target_product', '해당 상품')
#     category = state.get('target_category','정보 없음')
#     weather = (
#         f"기온 {temp}도, "
#         f"강수 {'있음' if rain == 1 else '없음'}, "
#         f"풍속 {wind}m/s, "
#         f"습도 {hum}%"
#     )

#     prompt = f"""
#     당신은 물류 요약 에이전트입니다. 다음 데이터를 바탕으로 한 문장으로 핵심만 리포트하세요.
    
#     데이터:
#     1. 상품명: {product}
#     2. 카테고리 : {category}
#     3. 날씨 정보: {weather}
#     4. ML 모델 기준 예측치: {base_val}개
    
#     제공된 '날씨 정보', '제품, 카테고리 정보'를 바탕으로 '기준 예측치'를 스스로 보정하세요.
#     여러 항목이라면, 예측치의 내림차순으로 정리해서 출력하세요.
#     """
    
#     try:
#         res = llm.invoke(prompt)
#         return {"response": res.content.strip()}
#     except Exception as e:
#         return {
#             "response": (
#                 f"{state.get('target_product')}은 "
#                 f"현재 기온 {state.get('temperature')}도, "
#                 f"{'강수 있음' if state.get('rain_flag') else '강수 없음'} 조건에서 "
#                 f"예상 수요 {state.get('response')} 수준입니다."
#             )
#         }

# def route_input(state: GraphState) -> str:
#     if state["analyze_prompt"] == "물류":
#         return "use_weather"
#     return "use_llm"

# builder = StateGraph(GraphState)

# builder.add_node("analyze_prompt", analyze_prompt)
# builder.add_node("weather_agent", analyze_weather)
# builder.add_node("warehouse_agent", run_wh_model)
# builder.add_node("llm_agent", run_general_llm)
# builder.add_node("run_finish_llm",run_finish_llm)

# builder.add_edge("weather_agent", "warehouse_agent")
# builder.add_edge("warehouse_agent", "run_finish_llm")
# builder.set_entry_point("analyze_prompt")
# builder.add_conditional_edges("analyze_prompt", route_input, {
#     "use_weather": "weather_agent",
#     "use_llm": "llm_agent"
# })
# builder.set_finish_point("run_finish_llm")
# builder.set_finish_point("llm_agent")

# graph = builder.compile()

# # 실행 (Main)
# # if __name__ == "__main__":
# #     print("=== 물류 AI 에이전트  ===")
# #     user_input = input("항목을 입력하세요: ")
# #     result = graph.invoke({"input": user_input})
# #     print("\n", result["response"])


# from fastapi import FastAPI
# from pydantic import BaseModel


# app = FastAPI(title="Logistics AI Agent")

# # === Request / Response 모델 ===
# class ChatRequest(BaseModel):
#     input: str
#     weather: dict 

# class ChatResponse(BaseModel):
#     response: str


# @app.post("/chat", response_model=ChatResponse)
# def chat(req: ChatRequest):
#     """
#     Spring에서 호출하는 엔드포인트
#     """

#     # result = graph.invoke({"input": req.input})
#     result = graph.invoke({
#         "input": req.input,
#         "weather": req.weather
#     })
#     return ChatResponse(response=result["response"])


# # === 로컬 테스트용 (선택) ===
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
