import pandas as pd
import os
import glob
import numpy as np
import sys

# Ensure UTF-8 output for Windows console
sys.stdout.reconfigure(encoding='utf-8')

# Configuration
DATA_DIR = r"c:\Users\ding9\Desktop\madoyo\데이터 참조"
MY_FILE = "dotori.xlsx"
MIN_ELAPSED_HOURS = 24

def parse_korean_metric(val):
    """
    Parses strings like: '조회 812회', '조회 4.4만회', '조회 109.6만회', '조회 5.8천회'
    Returns float or 0 if parsing fails.
    """
    if pd.isna(val):
        return 0
    
    s = str(val).strip()
    # Remove prefix/suffix/commas
    s = s.replace('조회', '').replace('회', '').replace(',', '').strip()
    
    if not s:
        return 0
        
    try:
        multiplier = 1
        if '만' in s:
            multiplier = 10000
            s = s.replace('만', '')
        elif '천' in s:
            multiplier = 1000
            s = s.replace('천', '')
            
        return float(s) * multiplier
    except:
        return 0

def load_and_preprocess(file_path):
    try:
        df = pd.read_excel(file_path)
        
        # Mapping by Index based on verified structure
        if len(df.columns) < 10:
            print(f"Warning: {os.path.basename(file_path)} has fewer than 10 columns. Skipping.")
            return None
            
        # Reassign columns referencing by index
        df.rename(columns={
            df.columns[2]: 'Views',
            df.columns[3]: 'UploadTime',
            df.columns[8]: 'FirstView',
            df.columns[9]: 'CrawlTime'
        }, inplace=True)
        
        # Convert datetime and standardize to UTC -> naive
        df['UploadTime'] = pd.to_datetime(df['UploadTime'], errors='coerce', utc=True).dt.tz_localize(None)
        df['CrawlTime'] = pd.to_datetime(df['CrawlTime'], errors='coerce', utc=True).dt.tz_localize(None)
        
        # Drop rows with invalid dates
        df = df.dropna(subset=['UploadTime', 'CrawlTime'])
        
        # Calculate Elapsed Time (Hours)
        df['elapsed_hours'] = (df['CrawlTime'] - df['UploadTime']).dt.total_seconds() / 3600.0
        
        # Filter: Elapsed time > MIN_ELAPSED_HOURS
        df_filtered = df[df['elapsed_hours'] >= MIN_ELAPSED_HOURS].copy()
        
        if df_filtered.empty:
            # print(f"Warning: No data remaining after {MIN_ELAPSED_HOURS}h filter for {os.path.basename(file_path)}.")
            return None

        # Parse Metrics
        df_filtered['Views'] = df_filtered['Views'].apply(parse_korean_metric)
        df_filtered['FirstView'] = df_filtered['FirstView'].apply(parse_korean_metric)
        
        # Calculate MSS
        # MSS = (First Comment Views ^ 2) / Post Views
        df_filtered['MSS'] = np.where(df_filtered['Views'] > 0, (df_filtered['FirstView'] ** 2) / df_filtered['Views'], 0)
        
        # Extract Day and Hour
        df_filtered['Day'] = df_filtered['UploadTime'].dt.day_name()
        df_filtered['Hour'] = df_filtered['UploadTime'].dt.hour
        
        return df_filtered
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return None

def generate_pivot_table(df, value_col='MSS'):
    # Pivot: Index=Hour, Columns=Day
    # Aggregation: Mean
    
    days_map = {
        'Monday': '월', 'Tuesday': '화', 'Wednesday': '수', 'Thursday': '목', 
        'Friday': '금', 'Saturday': '토', 'Sunday': '일'
    }
    
    df['Day_KR'] = df['Day'].map(days_map)
    days_order_kr = ['월', '화', '수', '목', '금', '토', '일']
    
    pivot = pd.pivot_table(
        df, 
        values=value_col, 
        index='Hour', 
        columns='Day_KR', 
        aggfunc='mean'
    )
    
    # Reindex columns to ensure order (mon-sun)
    pivot = pivot.reindex(columns=days_order_kr)
    
    # Reindex index to ensure all hours 0-23 exist
    pivot = pivot.reindex(range(24))
    
    # Add Row Average (Subtotal) - Average per Hour
    pivot['평균(소계)'] = pivot.mean(axis=1)
    
    # Add Column Average (Subtotal) - Average per Day
    # We calculate mean of the breakdown, or use original df mean? 
    # Using pivot mean treats each hour equally. 
    # Let's calculate the column means from the pivot itself for consistency in the table view.
    column_means = pivot.mean(axis=0)
    column_means.name = '요일별 평균'
    pivot = pd.concat([pivot, column_means.to_frame().T])
    
    # Formatting
    pivot = pivot.round(2)
    
    return pivot

def main():
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)

    # 1. Load My Data
    my_file_path = os.path.join(DATA_DIR, MY_FILE)
    df_my = load_and_preprocess(my_file_path)
    
    if df_my is not None:
        print("\n" + "="*80)
        print(f" [표 1] 내 계정 (My Data) - 평균 MSS 분석 (필터: >{MIN_ELAPSED_HOURS}h, n={len(df_my)})")
        print("="*80)
        # Use to_string() or direct print for simple text table
        print(generate_pivot_table(df_my).fillna('-').to_string())
    else:
        print("내 계정 데이터를 불러오지 못했거나 필터링 후 데이터가 없습니다.")

    # 2. Load All Data (Combined)
    all_files = glob.glob(os.path.join(DATA_DIR, "*.xlsx"))
    df_list = []
    
    print("\nProcessing All Files for Combined Analysis...")
    for f in all_files:
        _df = load_and_preprocess(f)
        if _df is not None:
            df_list.append(_df)
            
    if df_list:
        df_all = pd.concat(df_list, ignore_index=True)
        print("\n" + "="*80)
        print(f" [표 2] 전체 통합 데이터 (All Data) - 평균 MSS 분석 (필터: >{MIN_ELAPSED_HOURS}h, n={len(df_all)})")
        print("="*80)
        print(generate_pivot_table(df_all).fillna('-').to_string())
    else:
        print("통합 데이터를 생성하지 못했습니다.")

if __name__ == "__main__":
    main()
