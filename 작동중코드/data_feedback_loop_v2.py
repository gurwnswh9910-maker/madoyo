# data_feedback_loop_v2.py: 엑셀 데이터에서 MSS 성과를 계산하고 MAB 엔진에 학습 데이터를 공급하는 데이터 피드백 루프 모듈.
import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime
from mab_engine_v2 import DynamicMAB
from embedding_utils import EmbeddingManager
from strategy_clusterer import StrategyClusterer

class MSSDataIntegrator:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.mab = DynamicMAB(gamma=0.9)
        self.embed_mgr = EmbeddingManager(os.path.join(data_dir, "embeddings.pkl"))
        self.clusterer = StrategyClusterer(self.embed_mgr)

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
        # Existing columns in benchmark_dotori.py: 
        # ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']
        # External files may use variant names or be garbled in some environments.
        
        df_calc = df.copy()
        
        # Robust column detection logic
        def find_col(possible_names):
            for col in df_calc.columns:
                if any(name in str(col) for name in possible_names):
                    return col
            return None

        # Detect Views Column: '본문조회수', 'Views', '조회', 'ȸ'
        view_col = find_col(['본문조회수', 'Views', '조회수', '조회', 'ȸ'])
        # Detect Conversion (First Comment Views) Column: '첫댓글조회수', 'ConvViews', 'ùȸ', '첫'
        conv_col = find_col(['첫댓글조회수', 'ConvViews', 'ùȸ', 'ù조회', '첫조회', '첫댓글'])
        
        if not view_col or not conv_col:
            print(f"Warning: Could not detect all metrics columns. Views: {view_col}, Conv: {conv_col}")
            return np.zeros(len(df_calc))

        views = df_calc[view_col].apply(self.parse_views)
        conv_views = df_calc[conv_col].apply(self.parse_views)
        
        # MSS = (첫댓글조회수^2) / 본문조회수
        mss = np.where(views > 0, (conv_views**2) / views, 0)
        return mss

    def process_all_data(self, mab, use_cache=True):
        cache_file = os.path.join(self.data_dir, "data_cache.pkl")
        
        if use_cache and os.path.exists(cache_file):
            try:
                print(f"Loading data from cache: {cache_file}")
                df_total = pd.read_pickle(cache_file)
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
            # Standardize columns if needed for user data
            if len(df_user.columns) >= 10:
                cols = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']
                df_user.columns = cols[:len(df_user.columns)]
            if '본문' in df_user.columns:
                df_user['본문'] = df_user['본문'].apply(self.clean_noise_text)
            df_user['is_user'] = True
            all_data.append(df_user)

        # 2. Load External Benchmark Data (Priority: LOW)
        # Scan specific root files, '데이터 참조' folder, and '수집_데이터' folder
        benchmark_paths = [
            os.path.join(self.data_dir, "데이터 참조"),
            os.path.join(self.data_dir, "수집_데이터")
        ]
        
        for b_path in benchmark_paths:
            if not os.path.exists(b_path):
                continue
                
            if os.path.isfile(b_path):
                files = [b_path]
            else:
                files = [os.path.join(b_path, f) for f in os.listdir(b_path) if f.endswith(".xlsx")]
                
            for file_path in files:
                # Skip main user file if it accidentally ends up here
                if "dotori.xlsx" in file_path:
                    continue
                    
                print(f"Loading benchmark data: {file_path}")
                try:
                    df_ext = pd.read_excel(file_path)
                    if '본문' in df_ext.columns:
                        df_ext['본문'] = df_ext['본문'].apply(self.clean_noise_text)
                    df_ext['is_user'] = False
                    all_data.append(df_ext)
                except Exception as e:
                    print(f"Error loading {file_path}: {e}")

        if not all_data:
            return pd.DataFrame()

        df_total = pd.concat(all_data, ignore_index=True)
        df_total['MSS'] = self.calculate_mss(df_total)
        
        # Sort by time for decay simulation if needed
        if '작성시간' in df_total.columns:
            df_total['작성시간'] = pd.to_datetime(df_total['작성시간'], errors='coerce')
            df_total = df_total.sort_values('작성시간')

        # Update MAB with combined data
        last_date = None
        
        # 3. Process Embeddings (Incremental)
        print(f"Refreshing embeddings for {len(df_total)} posts...")
        texts = df_total['본문'].tolist()
        self.embed_mgr.get_many_embeddings(texts)
        self.embed_mgr.save_storage()

        # 4. Attribute rewards to strategic clusters with Weights
        if self.clusterer.clusters:
            print("Attributing rewards with weight-aware MAB...")
            for _, row in df_total.iterrows():
                current_date = row['작성시간'].date() if hasattr(row['작성시간'], 'date') else None
                if last_date is not None and current_date != last_date:
                    mab.decay()
                last_date = current_date
                
                arm = self.clusterer.get_closest_cluster(row['본문'])
                if arm:
                    # User: 1.5, External: 0.5 (Handled by is_user_data flag)
                    mab.update(arm, row['MSS'], timestamp=row['작성시간'], 
                               is_user_data=row['is_user'], apply_decay=False)

        # Cache saving
        try:
            df_total.to_pickle(cache_file)
            print(f"Data cached: {cache_file}")
        except: pass

        return df_total

    def get_top_performing_patterns(self, df, top_n=5):
        if df.empty: return []
        top_posts = df.sort_values('MSS', ascending=False).head(top_n)
        return top_posts[['본문', 'MSS']].to_dict('records')

if __name__ == "__main__":
    import sys
    import io

    # Setup UTF-8 for Windows terminal
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

    from copy_generator_v2 import DynamicCopyGenerator
    
    # Initialize components
    mab = DynamicMAB(gamma=0.9)
    integrator = MSSDataIntegrator(r'c:\Users\ding9\Desktop\madoyo')
    
    # Load past data and update MAB
    print("Updating MAB from historical reports...")
    data = integrator.process_all_data(mab)
    top_patterns = integrator.get_top_performing_patterns(data)
    
    print(f"Loaded {len(data)} posts.")
    print("\n[Top Performing Patterns by MSS]")
    for i, p in enumerate(top_patterns):
        # Using .get and string conversion to prevent errors with variant columns or emojis
        text_preview = str(p.get('본문', '')).replace('\n', ' ')[:50]
        print(f"{i+1}. MSS: {p['MSS']:.1f} | Text: {text_preview}...")
