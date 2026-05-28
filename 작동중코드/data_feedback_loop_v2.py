# data_feedback_loop_v2.py: 엑셀 데이터에서 MSS 성과를 계산하고 MAB 엔진에 학습 데이터를 공급하는 데이터 피드백 루프 모듈.
import pandas as pd
import numpy as np
import glob
import os
from pathlib import Path
from datetime import datetime
from mab_engine_v2 import DynamicMAB
from embedding_utils import EmbeddingManager
from strategy_clusterer import StrategyClusterer
from app_config import GlobalConfig

class MSSDataIntegrator:
    def __init__(self, data_dir=None):
        self.data_dir = data_dir or str(GlobalConfig.BASE_DIR)
        self.mab = DynamicMAB(gamma=0.9)
        # GlobalConfig.STORAGE_PATH를 기본값으로 사용하도록 EmbeddingManager 수정됨
        self.embed_mgr = EmbeddingManager() 
        self.clusterer = StrategyClusterer(self.embed_mgr)
        # 표준 컬럼 순서 (위치 기반 강제 매핑용)
        self.standard_cols = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']

    def apply_standard_columns(self, df):
        """환경에 상관없이 엑셀의 순서(Index)를 기준으로 컬럼명을 강제 통일합니다."""
        if df.empty: return df
        
        # 실제 엑셀의 컬럼 개수만큼만 매핑 (보통 10개)
        new_cols = []
        for i in range(len(df.columns)):
            if i < len(self.standard_cols):
                new_cols.append(self.standard_cols[i])
            else:
                new_cols.append(f"extra_{i}")
        
        df.columns = new_cols
        return df

    def clean_noise_text(self, text):
        if not isinstance(text, str): return ""
        import re
        # 1. 페이지 넘김 표시 제거 (1 / 2, 2 / 5 등)
        text = re.sub(r'\s*\d+\s*/\s*\d+\s*$', '', text).strip()
        # 2. 스크래핑 노이즈 제거
        noises = ['번역하기', ' See translation', ' See original', '원문 보기']
        for n in noises:
            text = text.replace(n, '')
        return text.strip()

    def parse_views(self, val):
        if pd.isna(val) or val == 0: return 0
        val = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
        try:
            multiplier = 1
            if '천' in val: multiplier = 1000; val = val.replace('천', '')
            elif '만' in val: multiplier = 10000; val = val.replace('만', '')
            return float(val) * multiplier
        except: return 0

    def calculate_mss(self, df):
        if df.empty or '본문' not in df.columns:
            return np.zeros(len(df))

        # 이미 apply_standard_columns를 거쳤으므로 표준 이름을 사용하면 됨
        views = df['본문조회수'].apply(self.parse_views)
        conv_views = df['첫댓글조회수'].apply(self.parse_views)
        
        # MSS = (첫댓글조회수^2) / 본문조회수
        mss = np.where(views > 0, (conv_views**2) / views, 0)
        return mss

    def process_all_data(self, mab, use_cache=True):
        if Path(self.data_dir).resolve() == GlobalConfig.BASE_DIR.resolve():
            cache_file = str(GlobalConfig.CACHE_PATH)
        else:
            cache_file = os.path.join(self.data_dir, "data_cache.pkl")
        
        if use_cache and os.path.exists(cache_file):
            try:
                print(f"Loading data from cache: {cache_file}")
                df_total = pd.read_pickle(cache_file)
                # 캐시 데이터라도 '본문' 컬럼이 없으면 강제 매핑 시도
                if '본문' not in df_total.columns:
                    df_total = self.apply_standard_columns(df_total)
                print(f"   Cache loaded: {len(df_total)} posts.")
                return df_total
            except Exception as e:
                print(f"Cache load failed: {e}. Re-processing...")

        all_data = []

        # 1. Load User Data (Priority: HIGH)
        user_file = os.path.join(self.data_dir, "데이터 참조", "dotori.xlsx")
        if os.path.exists(user_file):
            print(f"Loading user data: {user_file}")
            df_user = pd.read_excel(user_file)
            df_user = self.apply_standard_columns(df_user) # 인덱스 기반 강제 매핑
            if '본문' in df_user.columns:
                df_user['본문'] = df_user['본문'].apply(self.clean_noise_text)
            df_user['is_user'] = True
            all_data.append(df_user)

        # 2. Load External Benchmark Data (Priority: LOW)
        benchmark_paths = [
            os.path.join(self.data_dir, "데이터 참조"),
            os.path.join(self.data_dir, "수집_데이터")
        ]
        
        for b_path in benchmark_paths:
            if not os.path.exists(b_path): continue
            
            if os.path.isfile(b_path): files = [b_path]
            else: files = [os.path.join(b_path, f) for f in os.listdir(b_path) if f.endswith(".xlsx")]
                
            for file_path in files:
                if "dotori.xlsx" in file_path: continue
                print(f"Loading benchmark data: {file_path}")
                try:
                    df_ext = pd.read_excel(file_path)
                    df_ext = self.apply_standard_columns(df_ext) # 인덱스 기반 강제 매핑
                    if '본문' in df_ext.columns:
                        df_ext['본문'] = df_ext['본문'].apply(self.clean_noise_text)
                    df_ext['is_user'] = False
                    all_data.append(df_ext)
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")

        if not all_data: return pd.DataFrame()

        df_total = pd.concat(all_data, ignore_index=True)
        
        # 한국어 데이터 필터링
        def is_korean_strict(text):
            if not isinstance(text, str): return False
            import re
            kor_count = len(re.findall('[가-힣]', text))
            return (kor_count / max(len(text), 1)) > 0.3
            
        if '본문' in df_total.columns:
            print(f"   Filtering Korean posts... (Current: {len(df_total)})")
            df_total = df_total[df_total['본문'].apply(is_korean_strict)].copy()
            print(f"   ✅ Filtered: {len(df_total)} posts.")

        df_total['MSS'] = self.calculate_mss(df_total)
        
        if '작성시간' in df_total.columns:
            df_total['작성시간'] = pd.to_datetime(df_total['작성시간'], errors='coerce')
            df_total = df_total.sort_values('작성시간')

        # Cache saving (UTF-8 환경 보장을 위해 pickle 사용)
        try:
            df_total.to_pickle(cache_file)
            print(f"Data cached: {cache_file}")
        except: pass

        return df_total

    def get_top_performing_patterns(self, df, top_n=5):
        if df.empty: return []
        # '본문' 컬럼이 있는지 확인 (인덱스 기반 로직 보호)
        if '본문' not in df.columns:
            df = self.apply_standard_columns(df)
            
        top_posts = df.sort_values('MSS', ascending=False).head(top_n)
        return top_posts[['본문', 'MSS']].to_dict('records')

if __name__ == "__main__":
    import sys
    import io
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
    mab = DynamicMAB(gamma=0.9)
    integrator = MSSDataIntegrator(str(GlobalConfig.BASE_DIR))
    data = integrator.process_all_data(mab)
    top_patterns = integrator.get_top_performing_patterns(data)
    print(f"Loaded {len(data)} posts.")
