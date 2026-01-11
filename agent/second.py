import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import LabelEncoder

# 1. 데이터 로드
df = pd.read_csv('Historical_Product_Demand.csv')

# 2. 전처리 (날짜 및 숫자 변환)
df['Order_Demand'] = df['Order_Demand'].str.replace('(', '').str.replace(')', '').astype(float)
df['Date'] = pd.to_datetime(df['Date'])
df.dropna(inplace=True)
df['Month'] = df['Date'].dt.month

# 3. 데이터 인코딩 (문자를 숫자로)
le = LabelEncoder()
df['Warehouse_n'] = le.fit_transform(df['Warehouse'])
df['Category_n'] = le.fit_transform(df['Product_Category'])
df['Product_n'] = le.fit_transform(df['Product_Code'])

# 4. 특징(Feature) 선택
features = ['Month', 'Warehouse_n', 'Category_n', 'Product_n']
X = df[features]
y = df['Order_Demand']

# 5. 데이터 분할 (8:2)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 6. 알고리즘 적용: Random Forest
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# 7. 예측 및 결과 확인
y_pred = model.predict(X_test)
print(f"평균 예측 오차(MAE): {mean_absolute_error(y_test, y_pred):.2f}")

# 8. 어떤 특징이 가장 중요했는지 확인 (Feature Importance)
importances = pd.Series(model.feature_importances_, index=features)
plt.figure(figsize=(10, 5))
importances.sort_values().plot(kind='barh', color='orange')
print("Order_Demand 통계")
print(df['Order_Demand'].describe())

plt.title('Which feature is important for AI?')
plt.show()
