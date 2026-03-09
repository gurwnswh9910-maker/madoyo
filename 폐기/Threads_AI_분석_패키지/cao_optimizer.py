import pandas as pd
import numpy as np
import os
import re
import sys
import math
from collections import Counter

# Windows 터미널 한글 출력 지원
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

FILE_RAW = os.path.join("데이터 참조", "1.1차전처리.xlsx")
FILE_DOTORI = os.path.join("데이터 참조", "dotori.xlsx")

# 계층 구조에 맞춰 경로 수정 (Script is in Desktop/madoyo/프로젝트_패키지/Threads_AI_분석_패키지)
# 1. 패키지 폴더 2. 프로젝트_패키지 폴더 -> madoyo 폴더 도착
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__))) 
DATA_FILE = os.path.join(BASE_DIR, FILE_RAW)
DATA_DOTORI = os.path.join(BASE_DIR, FILE_DOTORI)

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

def get_tokens(text):
    return re.findall(r'\w+', str(text).lower())

def cosine_similarity(v1, v2):
    intersection = set(v1.keys()) & set(v2.keys())
    numerator = sum([v1[x] * v2[x] for x in intersection])
    sum1 = sum([v1[x]**2 for x in v1.keys()])
    sum2 = sum([v2[x]**2 for x in v2.keys()])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    return numerator / denominator if denominator else 0.0

class CAO_Optimizer:
    def __init__(self, data_path=DATA_FILE):
        try:
            # 엘리트 데이터 로드
            self.df = pd.read_excel(data_path)
            self.df.columns = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']
            
            # 데이터 전처리
            self.df['views'] = self.df['본문조회수'].apply(parse_views)
            self.df['conv_views'] = self.df['첫댓글조회수'].apply(parse_views)
            
            # 새로운 성과 지표 MSS (Monetization Success Score)
            # MSS = (첫댓글조회수^2) / 본문조회수
            self.df['MSS'] = np.where(self.df['views'] > 0, (self.df['conv_views']**2) / self.df['views'], 0)
            
            # 사용자(@dotori) 데이터 로드
            if os.path.exists(DATA_DOTORI):
                self.df_dotori = pd.read_excel(DATA_DOTORI)
                # 컬럼 매핑 (데이터 구조가 파일마다 약간 다를 수 있음 대비)
                if len(self.df_dotori.columns) >= 10:
                    self.df_dotori.columns = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']
                
                self.df_dotori['views'] = self.df_dotori['본문조회수'].apply(parse_views)
                self.df_dotori['conv_views'] = self.df_dotori['첫댓글조회수'].apply(parse_views)
                self.df_dotori['MSS'] = np.where(self.df_dotori['views'] > 0, (self.df_dotori['conv_views']**2) / self.df_dotori['views'], 0)
                print(f"✅ @dotori 계정 데이터 학습 완료 ({len(self.df_dotori)}개 포스팅)")
            else:
                self.df_dotori = None
                print("⚠️ @dotori 데이터를 찾을 수 없어 일반 모드로 작동합니다.")
                
        except Exception as e:
            print(f"❌ 데이터 로딩 실패: {e}")
            self.df = pd.DataFrame()
            self.df_dotori = None
        
        # 의미론적 벡터 미리 빌드
        self.df['tokens'] = self.df['본문'].apply(get_tokens)
        self.df['vectors'] = self.df['tokens'].apply(Counter)

    def optimize_copy(self, input_text):
        input_vec = Counter(get_tokens(input_text))
        
        # 1. 유사도 상위 20개 추출
        self.df['similarity'] = self.df['vectors'].apply(lambda x: cosine_similarity(input_vec, x))
        top_20 = self.df.sort_values('similarity', ascending=False).head(20).copy()
        
        # 2. 수익화 성과(MSS) 기준 정렬 (Top 5 vs Bot 5)
        # 단순히 조회수가 아닌, '수수료 수익성'이 높은 글을 정답으로 채택
        sorted_20 = top_20.sort_values('MSS', ascending=False)
        top_5 = sorted_20.head(5)
        bot_5 = sorted_20.tail(5)

        # 3. 대조적 프롬프트(CAO Strategy) 생성
        print(f"\n[CAO: Contrastive Attention Optimizer - Personalized Mode] 가동")
        print("-" * 80)
        print(f"🎯 @dotori 스타일 + 엘리트 성과 대조 최적화 중...")
        
        strategy_prompt = "### [CAO Personalized Guide for @dotori]\n"
        strategy_prompt += "사용자님의 과거 성과와 엘리트 데이터의 '수익화 효율(MSS)' 성공 패턴을 결합했습니다.\n\n"
        
        if self.df_dotori is not None:
            user_top = self.df_dotori.sort_values('MSS', ascending=False).head(3)
            strategy_prompt += "⭐️ [Your Personal Best] 사용자님의 글 중 가장 잘 먹혔던 패턴:\n"
            for i, row in user_top.iterrows():
                strategy_prompt += f"  - (MSS {row['MSS']:.1f}) \"{str(row['본문']).replace('\n', ' ')[:60]}...\"\n"
            strategy_prompt += "\n"

        strategy_prompt += "✅ [Elite Targets] 수익성이 검증된 상위 5개 엘리트 구조:\n"
        for i, row in top_5.iterrows():
            strategy_prompt += f"  - (MSS {row['MSS']:.1f}) \"{str(row['본문']).replace('\n', ' ')[:60]}...\"\n"
            
        strategy_prompt += "\n❌ [Avoidance] 유입 대비 실속이 없었던 하위 5개 구조:\n"
        for i, row in bot_5.iterrows():
            strategy_prompt += f"  - (MSS {row['MSS']:.1f}) \"{str(row['본문']).replace('\n', ' ')[:60]}...\"\n"

        print(strategy_prompt)
        print("-" * 80)
        return strategy_prompt

if __name__ == "__main__":
    optimizer = CAO_Optimizer()
    test_copy = "뉴욕사는 친구가 이렇게 먹길래 무슨통인지 알아내서 나도 간식 이렇게 가지고 다녀🥨"
    optimizer.optimize_copy(test_copy)
