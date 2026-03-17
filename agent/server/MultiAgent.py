# import json
# import re
# import os
# import joblib
# from typing import TypedDict, Optional
# from langgraph.graph import StateGraph
# from langchain_google_genai import ChatGoogleGenerativeAI
# import pandas as pd
# import numpy as np
# from datetime import datetime
# from pathlib import Path
# from langchain_community.chat_models import ChatOllama

# # 1. JSON 전용 모델 (오케스트레이터용)
# llm_json = ChatOllama(
#     model="llama3.1",
#     temperature=0,
#     format="json",
#     base_url="http://localhost:11434"
# )

# # 2. 자유 텍스트 모델 (요약 및 일반 대화용)
# llm_chat = ChatOllama(
#     model="llama3.1",
#     temperature=0.7, # 창의적인 답변을 위해 약간 높임
#     base_url="http://localhost:11434"
# )
# BASE_DIR = Path(__file__).resolve().parent.parent
# MODEL_DIR = BASE_DIR / "models"

# print(f"[*] Pathlib 기준 경로: {MODEL_DIR}")

# MODEL_DIR.mkdir(parents=True, exist_ok=True)

# class GraphState(TypedDict):
#     input: str
#     selected_models: Optional[list[str]] 
#     extracted_values: Optional[dict]

#     weather: Optional[dict]
#     temperature: Optional[float]
#     rain_flag: Optional[int]
#     wind_speed: Optional[float]
#     humidity: Optional[int]
    
#     request: Optional[str]
#     response: Optional[str]
#     analyze_prompt: Optional[str]

# # [수정] 가용 모델의 메타데이터를 스캔하는 함수 추가
# def get_registered_models():
#     registry = []
#     if not os.path.exists(MODEL_DIR):
#         return registry
#     for file in os.listdir(MODEL_DIR):
#         if file.endswith(".meta.json"):
#             try:
#                 with open(os.path.join(MODEL_DIR, file), "r", encoding="utf-8") as f:
#                     meta = json.load(f)
                    
#                     analysis = meta.get("analyze", {})
#                     category = analysis.get("category", "일반")
#                     description = analysis.get("description", "정보 없음")
#                     category_samples = meta.get("category_samples", [])
#                     features = meta.get("features",[])
                    
#                     registry.append({
#                         "id": meta.get("modelFile"), 
#                         "description": description,
#                         "category": category,
#                         "samples": category_samples,
#                         "features":features,
#                         "type": meta.get("title", "general") 
#                     })
#             except Exception as e:
#                 print(f"[*] registry 실패 : {e}")
#                 continue
#     return registry

# def analyze_prompt(state: GraphState) -> GraphState:
#     registry = get_registered_models()
#     valid_ids = [m['id'] for m in registry]
    
#     # 모델 설명을 더 단순화해서 주입
#     model_context = "\n".join([f"- ID: {m['id']} / 설명: {m['description']} / features: {m['features']}" for m in registry])
#     # print(f"[*] model_context: {model_context}")
#     prompt = f"""
#     ### SYSTEM:
#     1. [조회성 질문]: "목록", "리스트", "뭐 있어?" 같은 질문은 action을 'MODEL_CHAT'으로 지정하세요.
#     2. [예측성 질문]: "수요 예측", "거래량 예상" 등 수치 예측이 필요할 때만 'USE_MODEL'을 선택하세요.
#     3. [일반 대화]: 인사나 일반 질문은 action을 'GENERAL_CHAT'으로 지정하세요.

#     질문에 따른 target 모델을 선정하세요.

#     ### [가용 모델 목록]:
#     {model_context}
    
#     ### [반드시 JSON으로만 응답]:
#     {{
#       "action": "USE_MODEL", "GENERAL_CHAT", "MODEL_CHAT",
#       "target": "정확한 모델ID.pkl",
#       "values": {{"추출된 필드": "값"}}
#     }}
    
#     질문: {state['input']}
#     """

#     res = llm_json.invoke(prompt)
#     try:
#         # Llama 3.1의 JSON 모드 결과물을 안전하게 파싱
#         data = json.loads(res.content)
#         print(f"[*] 분석 결과: {data}")

#         # action이 USE_MODEL이고 target이 실제 파일 리스트에 있을 때만 수행
#         if data.get("action") == "USE_MODEL" or data.get("action")== "MODEL_CHAT" and data.get("target") in valid_ids:
#             return {
#                 "analyze_prompt": data.get("action"),
#                 "selected_models": [data.get("target")],
#                 "extracted_values": data.get("values", {})
#             }
#     except Exception as e:
#         print(f"[*] 파싱 실패 혹은 일반 질문: {e}")

#     return {"analyze_prompt": "GENERAL_CHAT"}

# # [유지] 날씨 정보 처리
# def analyze_weather(state: GraphState) -> GraphState:
#     print("analyze_weather")
#     weather = state.get("weather", {})
#     return {
#         "temperature": float(weather.get("T1H", 0)),
#         "rain_flag": 1 if (float(weather.get("RN1", 0)) > 0 or int(weather.get("PTY", 0)) > 0) else 0,
#         "wind_speed": float(weather.get("WSD", 0)),
#         "humidity": int(weather.get("REH", 0))
#     }
# def analyze_prompt_query(state: GraphState) -> GraphState:
#     print("@@@ 질문 상세 분석 및 피처 보완 단계 @@@")
    
#     # 1. 오케스트레이터가 선택한 모델 정보 가져오기
#     target_model_id = state.get("selected_models", [None])[0]
#     if not target_model_id:
#         return state

#     # 2. 레지스트리에서 해당 모델의 상세 메타데이터 찾기
#     registry = get_registered_models()
#     model_meta = next((m for m in registry if m['id'] == target_model_id), None)
    
#     if not model_meta:
#         return state

#     # 3. LLM에게 시나리오 구성을 요청 (부족한 피처 채우기)
#     prompt = f"""
#     데이터 분석을 해줘. 사용자의 질문을 바탕으로 머신러닝 모델 실행을 위한 최적의 '입력 데이터 세트'를 완성하세요.

#     [대상 모델]: {model_meta['id']}
#     [모델 설명]: {model_meta['description']}
#     [필수 피처 목록]: {model_meta['features']}
#     [피처 샘플 데이터]: {model_meta['samples']}

#     [현재 추출된 값]: {state.get('extracted_values', {})}
#     [사용자 질문]: {state.get('input')}

#     ### 임무:
#     1. '사용자 질문'과 '현재 추출된 값'을 확인하세요.
#     2. '필수 피처 목록' 중 누락된 값이 있다면, '피처 샘플 데이터'를 참고하여 가장 일반적이고 분석 가치가 높은 값으로 '추측'해서 채우세요.
#     3. 반드시 아래 JSON 형식으로만 응답하세요.
    
#     {{
#       "refined_values": {{
#           "피처명1": "값1",
#           "피처명2": "값2"
#       }},
#       "reasoning": "어떤 근거로 부족한 데이터를 채웠는지 설명"
#     }}
#     """

#     res = llm_json.invoke(prompt)
#     try:
#         refined_data = json.loads(res.content)
#         print(f"[*] 상세 분석 완료: {refined_data.get('reasoning')}")
        
#         # 보완된 데이터로 extracted_values 업데이트
#         return {
#             "extracted_values": refined_data.get("refined_values", {}),
#             "request": refined_data.get("reasoning", "")
#         }
#     except Exception as e:
#         print(f"[!] 상세 분석 파싱 실패: {e}")
#         return state

# # --- [수정] 범용 모델 실행 에이전트: 선택된 모델들을 동적으로 로드하여 실행 ---
# def run_dynamic_models(state: GraphState) -> GraphState:
#     print("=== 범용 모델 실행 에이전트 시작 ===")
#     selected_files = state.get("selected_models", [])
#     extracted_values = state.get("extracted_values", {})
#     results = []

#     for model_id in selected_files:
#         model_path = os.path.join(MODEL_DIR, model_id)
#         if not os.path.exists(model_path): continue

#         try:
#             saved_data = joblib.load(model_path)
#             model = saved_data["model"]
#             encoders = saved_data["feature_encoders"]
#             features = saved_data["features"]
            
#             # 1. 자동 피처 빌딩
#             input_data = {}
#             for feat in features:
#                 val = extracted_values.get(feat, "NULL")
                
#                 # 값이 NULL인 경우 시스템 기본값 적용 로직
#                 if val == "NULL":
#                     if 'month' in feat.lower(): val = datetime.now().month
#                     elif 'day' in feat.lower(): val = datetime.now().day
#                     elif 'status' in feat.lower(): val = 'success'
#                     else: val = 0 # 완전 기본값
                
#                 input_data[feat] = val

#             # 2. 데이터 프레임 생성 및 인코딩 (타입 체크 포함)
#             df_input = pd.DataFrame([input_data])
            
#             for col, le in encoders.items():
#                 if col in df_input.columns:
#                     target_val = str(df_input[col][0])
#                     # 인코더에 있는 값인지 확인 후 변환
#                     if target_val in [str(c) for c in le.classes_]:
#                         df_input[col] = le.transform([target_val])
#                     else:
#                         # 본 적 없는 값이면 0 또는 학습 데이터의 최빈값으로 대체
#                         df_input[col] = 0
            
#             # 3. 모델이 학습된 컬럼 순서와 동일하게 정렬
#             df_input = df_input[features]
            
#             # 4. 예측 실행
#             prediction = model.predict(df_input)[0]
            
#             results.append({
#                 "prediction": float(prediction),
#                 "inferred_params": input_data
#             })
           
#         except Exception as e:
#             print(f"[{model_id}] 실행 에러: {e}")

#     return {"response": json.dumps(results, ensure_ascii=False)}

# # [유지] 일반 LLM 대화
# def run_general_llm(state: GraphState) -> GraphState:
#     prompt = f"당신은 veneta AI 에이전트입니다. 질문에 답하세요: {state['input']}"
#     res = llm_chat.invoke(prompt)
#     return {"response": res.content}

# # [수정] 최종 요약: 모델 예측치와 날씨 정보를 결합하여 리포트
# def run_finish_llm(state: GraphState) -> GraphState:
#     print("최종 LLM ")
#     print(f"{state.get('response')}")
#     weather_info = f"temperature : {state.get('temperature')}도, rain_flag: {state.get('rain_flag')}, wind_speed : {state.get('wind_speed')} , humidity : {state.get('humidity')}"
#     print(f"{weather_info}")
#     data_summary = state.get('response')

#     prompt = f"""
#     당신은 데이터 리포트 전문가입니다. 
#     분석 결과({data_summary})가 날씨({weather_info})와 상관관계가 있는지 판단하세요. 관계가 있다면 연계하여 분석하고, 없다면 날씨는 연계없이 분석하세요.
#     결과를 질문 내용: {state['input']} 참고하여 자연스러운 한 문장으로만 정리해서 답해
#     """
#     res = llm_chat.invoke(prompt)
#     print(res)
#     return {"response": res.content.strip()}

# def run_model_llm(state: GraphState) -> GraphState:
#     print("@@@ ML 기반 지능형 조회(MODEL_CHAT) 실행 @@@")
    
#     # 1. 이전 노드(model_agent)에서 만든 예측 결과와 추론 파라미터 가져오기
#     # 만약 예측을 거치지 않고 왔다면 빈 값 처리
#     ml_result = state.get('response', '[]')
#     inferred_data = state.get('extracted_values', {})
    
#     # 2. 모델 메타데이터(제품 목록 등) 가져오기
#     target_model_id = state.get("selected_models", [None])[0]
#     registry = get_registered_models()
#     model_meta = next((m for m in registry if m['id'] == target_model_id), None)
    
#     samples_text = json.dumps(model_meta['samples'], ensure_ascii=False) if model_meta else "정보 없음"

#     # 3. 프롬프트 설계: "단순 조회가 아니라 ML 결과를 해석해라"
#     prompt = f"""
#     당신은 물류 데이터 분석 전문가입니다. 
#     머신러닝 모델의 예측 수치와 실제 데이터 샘플을 결합하여 사용자의 질문에 전문적으로 답하세요.

#     [머신러닝 분석 결과]
#     - 예측 데이터: {ml_result}
#     - 적용된 조건: {inferred_data}

#     [데이터베이스 기반 샘플 목록]
#     {samples_text}

#     ### 미션:
#     1. 사용자가 '목록'을 물었다면, 단순히 리스트만 주지 말고 "현재 {inferred_data} 조건 하에서 분석된 결과는 이렇습니다"라고 맥락을 짚어주세요.
#     2. 분석 결과({ml_result})에 나타난 예측 수치(prediction)가 왜 의미 있는지, 샘플 목록과 연계해서 설명하세요.
#     3. 날씨 정보({state.get('temperature')}도 등)가 분석 수치에 영향을 줬을지도 짧게 언급하세요.

#     질문: {state['input']}
#     """

#     res = llm_chat.invoke(prompt)
#     return {"response": res.content.strip()}

# # --- 그래프 구성 ---
# def route_input(state: GraphState) -> str:
#     status = state.get("analyze_prompt")
#     if status == "GENERAL_CHAT":
#         return "use_llm"
#     elif status == "MODEL_CHAT":
#         return "use_model_llm"
#     elif status == "USE_MODEL":
#         return "use_model"
#     return "use_llm" # 기본값
    
    
# builder = StateGraph(GraphState)

# builder.add_node("analyze_prompt", analyze_prompt)
# builder.add_node("weather_agent", analyze_weather)
# builder.add_node("model_agent", run_dynamic_models) # [수정] 통합된 동적 모델 노드
# builder.add_node("analyze_prompt_query", analyze_prompt_query)
# builder.add_node("use_model_llm" , run_model_llm)

# builder.add_node("llm_agent", run_general_llm)
# builder.add_node("run_finish_llm", run_finish_llm)


# builder.add_edge("weather_agent", "analyze_prompt_query")
# builder.add_edge("analyze_prompt_query", "model_agent")
# builder.add_edge("model_agent", "run_finish_llm")
# builder.set_entry_point("analyze_prompt")

# builder.add_conditional_edges("analyze_prompt", route_input, {
#     "use_model": "weather_agent",
#     "use_llm": "llm_agent",
#     "use_model_llm" : "use_model_llm"
# })

# builder.set_finish_point("run_finish_llm")
# builder.set_finish_point("llm_agent")
# builder.set_finish_point("use_model_llm")

# graph = builder.compile()

# from fastapi import FastAPI
# from pydantic import BaseModel


# app = FastAPI(title="Logistics AI Agent")

# # === Request / Response 모델 ===
# class ChatRequest(BaseModel):
#     input: str
#     weather: Optional[dict] = None

# class ChatResponse(BaseModel):
#     response: str


# @app.post("/chat", response_model=ChatResponse)
# def chat(req: ChatRequest):
#     """
#     Spring에서 호출하는 엔드포인트
#     """

#     result = graph.invoke({
#         "input": req.input,
#         "weather": req.weather
#     })
#     return ChatResponse(response=result["response"])


# # === 로컬 테스트용 (선택) ===
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8003)
