import pandas as pd
import os
import numpy as np

def analyze_character_counts():
    path = r'c:\Users\ding9\Desktop\madoyo\데이터 참조\dotori.xlsx'
    if not os.path.exists(path):
        print("File not found.")
        return
    
    df = pd.read_excel(path)
    
    def parse_views(val):
        if pd.isna(val) or val == 0: return 0
        val = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
        try:
            multiplier = 1
            if '천' in val: multiplier = 1000; val = val.replace('천', '')
            elif '만' in val: multiplier = 10000; val = val.replace('만', '')
            return float(val) * multiplier
        except: return 0
    
    try:
        # Standardizing based on data_feedback_loop_v2.py
        if len(df.columns) >= 10:
            df.columns = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간'][:len(df.columns)]
        
        views = df['본문조회수'].apply(parse_views)
        conv_views = df['첫댓글조회수'].apply(parse_views)
        df['MSS'] = np.where(views > 0, (conv_views**2) / views, 0)
        
        # Character count (excluding spaces slightly differently or including them?)
        # Let's count full length (including spaces) for visual impact
        df['char_count'] = df['본문'].apply(lambda x: len(str(x)))
        df['line_count'] = df['본문'].apply(lambda x: len([l for l in str(x).split('\n') if l.strip()]))
        
        top_20 = df.sort_values('MSS', ascending=False).head(20)
        
        print(f"--- Top 20 MSS Analysis ---")
        print(f"Average Char Count: {top_20['char_count'].mean():.1f}")
        print(f"Median Char Count: {top_20['char_count'].median():.1f}")
        print(f"Average Line Count: {top_20['line_count'].mean():.1f}")
        
        print("\n--- Detailed Top 10 ---")
        for i, row in top_20.head(10).iterrows():
            print(f"MSS: {row['MSS']:.1f} | Chars: {row['char_count']} | Lines: {row['line_count']} | Text: {str(row['본문'])[:30]}...")
            
    except Exception as e:
        print(f"Error during analysis: {e}")

if __name__ == "__main__":
    analyze_character_counts()
