import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder
import joblib

# 1. 데이터 로드 및 기본 전처리
df = pd.read_csv('Historical_Product_Demand.csv')
df['Order_Demand'] = df['Order_Demand'].str.replace('(', '').str.replace(')', '').astype(float)
df['Date'] = pd.to_datetime(df['Date'])
df.dropna(inplace=True)
# 월별 분리
df['Month'] = df['Date'].dt.month 

# 공통 LabelEncoder (모든 창고의 제품 코드를 커버해야 함)
le_product = LabelEncoder()
le_category = LabelEncoder()
df['Product_n'] = le_product.fit_transform(df['Product_Code'])
df['Category_n'] = le_category.fit_transform(df['Product_Category'])

# 2. 창고 목록 추출
warehouses = df['Warehouse'].unique()

# 3. 창고별 모델 생성 루프
for wh in warehouses:
    print(f"--- [Training] Model for {wh} ---")
    
    # 해당 창고 데이터만 필터링
    wh_df = df[df['Warehouse'] == wh].copy()
    
    # 특징(Feature)과 정답(Target) 설정
    # 창고 정보는 이미 사용중으로, 월/카테고리/제품 정보만 활용
    features = ['Month', 'Category_n', 'Product_n']
    X = wh_df[features]
    y = wh_df['Order_Demand']
    
    # 모델 학습
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # 창고 이름을 파일명에 넣어 각각 저장
    joblib.dump(model, f'model_{wh}.pkl')
    print(f"Successfully saved: model_{wh}.pkl")

# 전체 공통 인코더 저장
joblib.dump(le_product, 'le_product.pkl')
joblib.dump(le_category, 'le_category.pkl')