import pandas as pd
import sys
import io

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

f1 = '1.1차전처리.xlsx'
f2 = '데이터 참조/threads_slow_report_0212_0320.xlsx'

def inspect(filename):
    print(f"\n--- Inspecting: {filename} ---")
    try:
        df = pd.read_excel(filename)
        print(f"Columns: {df.columns.tolist()}")
        print(f"Shape: {df.shape}")
        print("Sample Data:")
        print(df.head(3))
        return df
    except Exception as e:
        print(f"Error reading {filename}: {e}")
        return None

df1 = inspect(f1)
df2 = inspect(f2)

if df1 is not None and df2 is not None:
    # 계정 식별자 확인 (예: 링크에서 추출)
    print("\n[Comparison Summary]")
    # 링크 컬럼이 있다고 가정하고 계정명 추출 시도
    # (실제 컬럼명은 데이터 보고 확인 필요)
