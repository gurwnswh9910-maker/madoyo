# benchmark_dotori.py: 데이터셋 간(내 계정, 외부 리포트, 엘리트 그룹) 성과 비교 및 톤 분석 도구.
import pandas as pd
import numpy as np
import os
import re
import sys

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

FILE_ELITE = os.path.join("데이터 참조", "1.1차전처리.xlsx")
FILE_2SEO = os.path.join("데이터 참조", "threads_slow_report_0212_0320.xlsx")
FILE_USER = os.path.join("데이터 참조", "dotori.xlsx")

def parse_views_robust(val):
    if pd.isna(val) or val == 0: return 0
    val = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
    if not val or val == '0': return 0
    try:
        multiplier = 1
        if '천' in val: multiplier = 1000; val = val.replace('천', '')
        elif '만' in val: multiplier = 10000; val = val.replace('만', '')
        return float(val) * multiplier
    except: return 0

def calculate_metrics(df):
    df.columns = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']
    df['views'] = df['본문조회수'].apply(parse_views_robust)
    df['conv_views'] = df['첫댓글조회수'].apply(parse_views_robust)
    # MSS = (첫댓글조회수^2) / 본문조회수
    df['MSS'] = np.where(df['views'] > 0, (df['conv_views']**2) / df['views'], 0)
    return df

def run_benchmark():
    try:
        df_elite = calculate_metrics(pd.read_excel(FILE_ELITE))
        df_2seo = calculate_metrics(pd.read_excel(FILE_2SEO))
        df_user = calculate_metrics(pd.read_excel(FILE_USER))
        
        print("\n[📊 Across-Dataset Performance Benchmark]")
        print("-" * 80)
        
        results = []
        for name, df in [("Elite Group", df_elite), ("@2seo_log", df_2seo), ("@dotori (User)", df_user)]:
            results.append({
                "Dataset": name,
                "Avg Views": df['views'].mean(),
                "Avg Conv Views": df['conv_views'].mean(),
                "Avg MSS": df['MSS'].mean(),
                "Post Count": len(df)
            })
        
        benchmark_df = pd.DataFrame(results)
        print(benchmark_df)
        
        print("\n[📝 Tone Analysis: @dotori (User)]")
        all_text = " ".join(df_user['본문'].astype(str))
        words = re.findall(r'\w+', all_text)
        common_words = pd.Series(words).value_counts().head(10)
        print("자주 사용하는 어휘:")
        print(common_words)

        # @dotori의 최상위 성과글 (Positive Reinforcement)
        top_user_posts = df_user.sort_values('MSS', ascending=False).head(3)
        print("\n[🏆 @dotori's Personal Best (High MSS)]")
        for i, (idx, row) in enumerate(top_user_posts.iterrows()):
            print(f"{i+1}. MSS: {row['MSS']:.1f} | 본문: {str(row['본문'])[:60]}...")

    except Exception as e:
        print(f"Error during benchmark: {e}")

if __name__ == "__main__":
    run_benchmark()
