import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import matplotlib.pyplot as plt

# 1. 데이터 로드 (사용자님의 수집된 엑셀 파일이 있다고 가정)
# 파일명이 다를 수 있으니 실제 파일명으로 수정 필요
try:
    # 가장 최근에 수집된 파일 이름을 예시로 사용
    df = pd.read_excel("데이터 참조/threads_slow_report_0212_0320.xlsx")
    print("✅ 데이터 로드 완료!")
except:
    # 파일이 없을 경우를 대비한 가상 데이터 생성 (데모용)
    print("⚠️ 실제 파일이 없어 가상 데이터를 생성하여 시연합니다.")
    data = {
        '본문': ["안녕" for _ in range(300)],
        '좋아요': np.random.randint(0, 100, 300),
        '답글수': np.random.randint(0, 50, 300),
        '본문조회수': np.random.randint(100, 5000, 300)
    }
    df = pd.DataFrame(data)

# 2. 전처리 및 특성 추출 (Feature Engineering)
# 간단한 예시: 본문 길이와 조회수를 기반으로 좋아요 수 예측
df['본문길이'] = df['본문'].apply(lambda x: len(str(x)))
df['조회수'] = pd.to_numeric(df['본문조회수'], errors='coerce').fillna(0)
df['목표_좋아요'] = pd.to_numeric(df['좋아요'], errors='coerce').fillna(0)

# 분석에 사용할 데이터 선택
X = df[['본문길이', '조회수']]
y = df['목표_좋아요']

# 3. 데이터 분할 (학습용 80% / 테스트용 20%)
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# 4. 머신러닝 모델 생성 (Random Forest)
model = RandomForestRegressor(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

# 5. 예측 및 결과 확인
y_pred = model.predict(X_test)

print("\n📊 머신러닝 모델 성능 보고서 (300개 기준)")
print(f"- 결정계수 (R²): {r2_score(y_test, y_pred):.2.f}")
print("  (1에 가까울수록 모델이 정확하게 예측한다는 의미입니다.)")

# 6. 중요 변수 확인 (어떤 게 좋아요에 영향을 많이 주나?)
importances = model.feature_importances_
print("\n💡 영향력 분석 결과:")
for name, importance in zip(X.columns, importances):
    print(f"- {name}: {importance*100:.1f}%")

print("\n✨ 이처럼 300개의 데이터만으로도 어떤 게시물이 인기 있을지 '수치화'된 예측이 가능합니다.")
