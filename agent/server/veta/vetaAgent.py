# import json, re, joblib
# from typing import TypedDict, List, Dict, Optional
# from datetime import datetime
# from pathlib import Path
# import psycopg2
# from psycopg2.extras import RealDictCursor
# import pandas as pd
# from fastapi import FastAPI
# from pydantic import BaseModel

# from langgraph.graph import StateGraph
# from langchain_community.chat_models import ChatOllama

# # =========================
# # LLM
# # =========================
# llm_json = ChatOllama(
#     model="llama3.1",
#     temperature=0,
#     format="json",
#     base_url="http://newyork-llm.newyork-llm:11434"
# )

# llm_chat = ChatOllama(
#     model="llama3.1",
#     temperature=0.6,
#     base_url="http://newyork-llm.newyork-llm:11434"
# )
# DB_CONFIG = {
#     "dbname": "test_veta_wallet",
#     "user": "root",
#     "password": "Abcd1234",
#     "host": "192.168.40.119",
#     "port": 30432,
# }

# # =========================
# # Utils
# # =========================
# def safe_json(content) -> dict:
#     # 이미 dict면 그대로 반환
#     if isinstance(content, dict):
#         return content

#     # 문자열인 경우만 전처리
#     if isinstance(content, str):
#         try:
#             text = re.sub(r"```json|```", "", content).strip()
#             return json.loads(text)
#         except Exception:
#             return {}

#     return {}


# def sql_is_safe(sql: str) -> bool:
#     sql = sql.lower()
#     banned = ["insert", "update", "delete", "drop", "alter", ";"]
#     return sql.startswith("select") and not any(b in sql for b in banned)

# # =========================
# # Paths
# # =========================
# BASE_DIR = Path(__file__).resolve().parent
# MODEL_DIR = BASE_DIR / "models"
# META_DIR = BASE_DIR / "model_meta"

# # =========================
# # State
# # =========================
# class AgentState(TypedDict, total=False):
#     input: str
#     user: Optional[dict]
#     intent: str

#     sql_query: str
#     db_results: List[dict]

#     selected_models: List[str]
#     predictions: List[dict]

#     response: str

# # =========================
# # Agents
# # =========================
# def intent_agent(state: AgentState) -> AgentState:
#     print(f"intent_agent")
#     prompt = f"""
#     질문 의도를 분류하세요.

#     JSON:
#     {{ "intent": "DB_QUERY | PREDICTION | CHAT" }}

#     질문: {state["input"]}
#     """
#     res = llm_json.invoke(prompt)
#     data = safe_json(res.content)
#     return {"intent": data.get("intent", "CHAT")}

# def chat_agent(state: AgentState) -> AgentState:
#     print(f"chat_agent")
#     res = llm_chat.invoke(state["input"])
#     return {"response": res.content}

# def sql_planner_agent(state: AgentState) -> AgentState:
#     print(f"sql_planner_agent")
#     prompt = f"""
#     아래는 복지 포인트 시스템의 데이터베이스 테이블 정보입니다. 이 이름들을 정확히 사용하세요.
#     - tbl_user : 사용자 정보 (name, user_id, email, first_name, last_name, phone_number 등)
#     - tbl_core_balance : 포인트 잔액 정보 (amount, address, token_id 등)
#     - tbl_transaction : 결제 및 거래 내역 (source_name, amount 등)
#     - tbl_staking_transaction : 스테이킹/이차 정보

#     질문: {state["input"]}
#     사용자 : {state["user"]}
#     {{ "sql": "SELECT ..." }}
#     """
#     res = llm_json.invoke(prompt)
#     data = safe_json(res.content)
#     print(f"data :: {data}")
#     sql = data.get("sql", "")

#     if not sql_is_safe(sql):
#         return {"sql_query": None}

#     return {"sql_query": sql }

# def db_executor_agent(state: AgentState) -> AgentState:
#     print(f"db_executor_agent")
#     if not state.get("sql_query"):
#         return {"db_results": [{"error": "안전하지 않은 SQL"}]}
#     try:
#         with psycopg2.connect(**DB_CONFIG) as conn: 
#             with conn.cursor(cursor_factory=RealDictCursor) as cur:
#                 cur.execute(state["sql_query"])
#                 rows = cur.fetchall()
#                 print(f"rows :: {rows}")
#         return {"db_results": rows}

#     except Exception as e:
#         print(f"error ::: {e}")
#         return {"db_results": [{"error": str(e)}]}

# def ml_selector_agent(state: AgentState) -> AgentState:
#     print(f"ml_selector_agent")
#     registry = [json.loads(f.read_text()) for f in META_DIR.glob("*.json")]
#     if not registry:
#         return {"selected_models": []}

#     return {"selected_models": [registry[0]["model_id"]]}

# def ml_runner_agent(state: AgentState) -> AgentState:
#     print(f"ml_runner_agent")
#     preds = []
#     for mid in state.get("selected_models", []):
#         preds.append({"model_id": mid, "prediction": 123.4})
#     return {"predictions": preds}

# def reporter_agent(state: AgentState) -> AgentState:
#     print(f"reporter_agent")
#     context = ""
#     if state.get("db_results"):
#         context += "\nDB 결과:\n" + json.dumps(
#             state["db_results"],
#             ensure_ascii=False,
#             indent=2
#         )

#     if state.get("predictions"):
#         context += "\n예측 결과:\n" + json.dumps(
#             state["predictions"],
#             ensure_ascii=False,
#             indent=2
#         )

#     prompt = f"""
#     veneta AI agent입니다. 앱 사용자에게 민감한 정보는 제공하지말고, 간단한 도움을 제공하세요.
#     질문: {state["input"]}
#     결과: {context}
#     사용자에게 짧게 설명하세요.
#     """
#     res = llm_chat.invoke(prompt)
#     print(f"result : {res.content}" )
#     return {"response": res.content}

# # =========================
# # Graph
# # =========================
# def route(state: AgentState):
#     if state["intent"] == "DB_QUERY": return "db"
#     if state["intent"] == "PREDICTION": return "ml"
#     return "chat"

# builder = StateGraph(AgentState)

# builder.add_node("intent", intent_agent)
# builder.add_node("chat", chat_agent)
# builder.add_node("sql_planner", sql_planner_agent)
# builder.add_node("db_exec", db_executor_agent)
# builder.add_node("ml_selector", ml_selector_agent)
# builder.add_node("ml_runner", ml_runner_agent)
# builder.add_node("report", reporter_agent)

# builder.set_entry_point("intent")

# builder.add_conditional_edges("intent", route, {
#     "chat": "chat",
#     "db": "sql_planner",
#     "ml": "ml_selector"
# })

# builder.add_edge("sql_planner", "db_exec")
# builder.add_edge("db_exec", "report")
# builder.add_edge("ml_selector", "ml_runner")
# builder.add_edge("ml_runner", "report")

# builder.set_finish_point("report")
# graph = builder.compile()

# # =========================
# # FastAPI
# # =========================
# app = FastAPI()

# class ChatRequest(BaseModel):
#     input: str
#     user: Optional[dict] = None

# @app.post("/chat")
# def chat(req: ChatRequest):
#     user_data = req.user if req.user is not None else {}
#     result = graph.invoke({"input": req.input, "user": user_data})
#     return {"response": result.get("response", "응답 생성 실패")}

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8004)
