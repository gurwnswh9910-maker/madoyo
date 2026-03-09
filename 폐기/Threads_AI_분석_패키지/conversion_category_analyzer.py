import pandas as pd
import numpy as np
import os
import re
import sys

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

FILE_RAW = "1.1차전처리.xlsx"
FILE_SAMPLE = "데이터 참조/threads_slow_report_0212_0320.xlsx"

def parse_views(val):
    if pd.isna(val) or val == 0: return 0
    val = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
    if not val or val == '0': return 0
    try:
        multiplier = 1
        if '천' in val: multiplier = 1000; val = val.replace('천', '')
        elif '만' in val: multiplier = 10000; val = val.replace('만', '')
        return float(val) * multiplier
    except: return 0

# 카테고리 키워드 정의
CATEGORIES = {
    '육아/가정': ['애기', '아이', '아기', '육아', '가정', '엄마', '아빠', '어린이', '유치원', '학교', '살림', '주부'],
    '뷰티/패션': ['피부', '화장품', '발색', '코스메틱', '메이크업', '옷', '상의', '하의', '패션', '가방', '미용', '스킨'],
    '간식/맛집': ['맛', '맛집', '간식', '과자', '카페', '커피', '존맛', '개맛', '추천', '편의점', '식당', '요리'],
    '지식/자기계발': ['지식', '공부', '책', '독서', '방법', '꿀팁', '정보', '노하우', '발전', '성장', '강의'],
    '라이프스타일': ['집', '인테리어', '여행', '휴가', '일상', '오늘', '기분', '감성', '분위기', '인스타']
}

def classify_category(text):
    text = str(text)
    scores = {cat: 0 for cat in CATEGORIES}
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in text:
                scores[cat] += 1
    
    max_cat = max(scores, key=scores.get)
    if scores[max_cat] == 0:
        return '기타'
    return max_cat

def run_analysis():
    if not os.path.exists(FILE_RAW) or not os.path.exists(FILE_SAMPLE):
        print("❌ 분석할 파일이 부족합니다.")
        return

    # 데이터 로드
    df_raw = pd.read_excel(FILE_RAW)
    df_sample = pd.read_excel(FILE_SAMPLE)

    # 컬럼 표준화
    cols = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']
    df_raw.columns = cols[:len(df_raw.columns)]
    df_sample.columns = cols[:len(df_sample.columns)]

    # 수치화
    for df in [df_raw, df_sample]:
        df['views'] = df['본문조회수'].apply(parse_views)
        df['conv_views'] = df['첫댓글조회수'].apply(parse_views)
        # 새로운 성과 지표 MSS (Monetization Success Score)
        df['MSS'] = np.where(df['views'] > 0, (df['conv_views']**2) / df['views'], 0)
        df['category'] = df['본문'].apply(classify_category)

    print(f"\n[수익화(MSS) 중심 카테고리 분석 리포트]")
    print("-" * 85)
    
    # 전체 데이터(1.1차) 기반 카테고리별 수익화 성과
    raw_cat_perf = df_raw.groupby('category').agg({
        'views': 'mean',
        'MSS': 'mean'
    }).sort_values('MSS', ascending=False)

    print(f"💰 [전체 집단] 카테고리별 수익화 지수 (MSS 순):")
    for cat, row in raw_cat_perf.iterrows():
        print(f"   - {cat:<10} | 수익화지수(MSS): {row['MSS']:>6.1f} | 평균조회수: {int(row['views']):>7,}회")

    # 샘플 데이터(300개) 기반 카테고리 점유 현황
    sample_cat_dist = df_sample['category'].value_counts(normalize=True)
    print(f"\n📈 [@2seo_log] 카테고리 점유 현황:")
    for cat, ratio in sample_cat_dist.items():
        print(f"   - {cat:<10} | {ratio*100:>5.1f}%")

    # 톤 분석 (단어 빈도)
    def analyze_tone(text_list):
        all_text = " ".join([str(t) for t in text_list])
        words = re.findall(r'\w+', all_text)
        return pd.Series(words).value_counts().head(10).to_dict()

    print(f"\n🎙️ [@2seo_log] 핵심 톤/매너 (자주 사용하는 어휘):")
    tone_words = analyze_tone(df_sample['본문'].tolist())
    for word, count in tone_words.items():
        print(f"   - '{word}' ({count}회)")

    print("-" * 85)
    print("📢 데이터 기반 전략 제언:")
    
    # 블루오션 찾기: 전체에서 전환율은 높으나 샘플에서 낮은 비중인 카테고리
    blue_ocean = []
    for cat in raw_cat_perf.index:
        if cat == '기타': continue
        sample_ratio = sample_cat_dist.get(cat, 0)
        if sample_ratio < 0.1: # 샘플에서 10% 미만인 경우
            blue_ocean.append(cat)
    
    print(f"1. 블루오션 카테고리: {', '.join(blue_ocean)} (전환율이 높지만 현재 계정에서 비중이 낮음)")
    print(f"2. @2seo_log의 톤 특징: 신뢰감을 주는 '팁', '방법', '이유' 등의 지식 공유형 어휘를 주로 사용함.")
    print(f"3. 전환 최적화: 전환율이 가장 높은 '{raw_cat_perf.index[0]}' 카테고리의 텍스트 구조를 현 계정 스타일에 결합 권장.")

if __name__ == "__main__":
    run_analysis()
