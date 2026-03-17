# from fastapi import FastAPI, UploadFile, File, Form
# import pandas as pd
# import io
# import os
# import hashlib
# import re
# import joblib
# import json  # <--- 반드시 필요
# from datetime import datetime  # <--- 반드시 필요
# from sklearn.ensemble import RandomForestClassifier
# from langchain_google_genai import ChatGoogleGenerativeAI
# from sklearn.preprocessing import LabelEncoder
# from langchain_community.chat_models import ChatOllama
# app = FastAPI(title="Dynamic ML Training Agent")

# llm = ChatOllama(
#     model="llama3.1", 
#     temperature=0,    
#     format="json",    
#     base_url="http://localhost:11434" #
# )
# current_file = os.path.abspath(__file__)

# current_dir = os.path.dirname(current_file)
# BASE_DIR = os.path.dirname(current_dir)

# MODEL_DIR = os.path.join(BASE_DIR, "models")
# os.makedirs(MODEL_DIR, exist_ok=True)

# @app.post("/train")
# async def train_model(
#     file: UploadFile = File(...),
#     columns: str = Form(...),
#     analyze: str = Form(...),
#     samples: str = Form(...)
# ):
#     try:
#         analyze_dict = json.loads(analyze)
#         content = await file.read()
#         if file.filename.endswith(".csv"):
#             df = pd.read_csv(io.BytesIO(content))
#         elif file.filename.endswith((".xlsx", ".xls")):
#             df = pd.read_excel(io.BytesIO(content))
#         else:
#             return {"status": "error", "message": "지원하지 않는 파일 형식입니다."}

#         selected_cols = [c.strip() for c in columns.split(",") if c.strip()]
#         X_raw = df[selected_cols]
#         y = df[df.columns[-1]]

#         samples_list = json.loads(samples)
#         # 인코딩 로직
#         encoders = {}
#         X = pd.DataFrame()
#         for col in X_raw.columns:
#             if X_raw[col].dtype == "object":
#                 le = LabelEncoder()
#                 X[col] = le.fit_transform(X_raw[col].astype(str))
#                 encoders[col] = le
#             else:
#                 X[col] = X_raw[col]

#         target_encoder = None
#         if y.dtype == "object":
#             target_encoder = LabelEncoder()
#             y = target_encoder.fit_transform(y.astype(str))

#         # 모델 학습
#         model = RandomForestClassifier(n_estimators=100, random_state=42)
#         model.fit(X, y)

#         # 저장 경로 설정
#         base_name = os.path.splitext(file.filename)[0]
#         col_hash = hashlib.md5(",".join(selected_cols).encode()).hexdigest()[:8]
#         model_name = f"{base_name}_{col_hash}.pkl"
#         meta_name = f"{base_name}_{col_hash}.meta.json"
        
#         model_path = os.path.join(MODEL_DIR, model_name)
#         meta_path = os.path.join(MODEL_DIR, meta_name)

#         # 1. 모델 저장
#         joblib.dump({
#             "model": model,
#             "feature_encoders": encoders,
#             "target_encoder": target_encoder,
#             "features": selected_cols
#         }, model_path)
        
#         # 2. 메타데이터 저장
#         meta_data = {
#             "modelFile": model_name,
#             "title": base_name,
#             "features": selected_cols,
#             "encodedColumns": list(encoders.keys()),
#             "rows": len(df),
#             "createdAt": datetime.now().isoformat(), 
#             "status": "success",
#             "analyze": analyze_dict,
#             "category_samples": samples_list
#         }

#         with open(meta_path, "w", encoding="utf-8") as f:
#             json.dump(meta_data, f, ensure_ascii=False, indent=4)
        
#         print(f"Saved Metadata to: {meta_path}") # 서버 터미널에서 경로 확인용

#         return {
#             "status": "success",
#             "model_file": model_name,
#             "meta_file": meta_name
#         }
#     except Exception as e:
#         print(f"Training Error: {e}")
#         return {"status": "error", "message": str(e)}

# @app.get("/models")
# def list_models():
#     models = []
#     if not os.path.exists(MODEL_DIR):
#         return []

#     files = os.listdir(MODEL_DIR)
#     for file in files:
#         if file.endswith(".meta.json"):
#             meta_path = os.path.join(MODEL_DIR, file)
#             try:
#                 with open(meta_path, "r", encoding="utf-8") as f:
#                     meta = json.load(f)
#                     models.append(meta)
#             except Exception as e:
#                 print(f"Error reading {file}: {e}")
#                 continue
                
#     # 생성일 기준 역순(최신순) 정렬 서비스 제공
#     models.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
#     return models



# @app.post("/analyze")
# async def analyze_data(data: dict):
#     cols = data.get("columns")
#     samples = data.get("samples")
#     prompt = f"""
#     당신은 데이터 분석 전문가입니다. 아래의 정보를 분석하여 JSON 형식으로만 답변하세요.
#     마크다운 코드 블록 기호(```json)를 쓰지 말고 오직 순수 JSON 데이터만 출력하세요.
    
#     [컬럼 정보]: {cols}
#     [샘플 데이터]: {samples}
    
#     [응답 JSON 구조]:
#     {{
#         "category": "데이터 카테고리",
#         "target_recommendation": "추천 타겟 컬럼명",
#         "description": "데이터셋 한 줄 설명"
#     }}
#     """
    
#     res = llm.invoke(prompt)
#     print(res)
#     content = res.content.strip()

#     try:
#         json_pattern = re.compile(r'\{.*\}', re.DOTALL)
#         match = json_pattern.search(content)
        
#         if match:
#             json_str = match.group()
#             return json.loads(json_str)
#         else:
#             return json.loads(content)
            
#     except json.JSONDecodeError as e:
#         print(f"JSON Parsing Error: {e}")
#         print(f"Raw Content: {content}")
#         return {"status": "error", "message": "JSON 파싱에 실패했습니다.", "raw": content}

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001)