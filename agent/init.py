import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# 1. 데이터 로드 Kaggle 데이터
df = pd.read_csv('Historical_Product_Demand.csv')

# 2. 데이터 타입 변환 및 정제
# Order_Demand 컬럼의 괄호 제거 및 숫자, Date 날짜 데이터 형태로 변환
df['Order_Demand'] = df['Order_Demand'].str.replace('(', '').str.replace(')', '').astype(float)
df['Date'] = pd.to_datetime(df['Date'])

# 3. Null값 제거
df.dropna(inplace=True)

# 4. X축 데이터 특징(Feature) 날짜에서 시계열 요소 추출
df['Month'] = df['Date'].dt.month

# 5. 시각화 그래프 표현 J 창고의 월별 수요 합계 확인
wh_a = df[df['Warehouse'] == 'Whse_J'].groupby('Month')['Order_Demand'].sum()
plt.figure(figsize=(10, 5)) # 가로 10인치 세로 5인치
wh_a.plot(kind='line', color='green')
plt.title('Monthly Demand at Warehouse J')
plt.show()