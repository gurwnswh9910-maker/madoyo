
import pandas as pd
import os

data_dir = r"c:\Users\ding9\Desktop\madoyo\데이터 참조"
files_to_inspect = ["dotori.xlsx", "threads_slow_report_0218_0218.xlsx"]

for file in files_to_inspect:
    file_path = os.path.join(data_dir, file)
    print(f"--- Inspecting {file} ---")
    try:
        df = pd.read_excel(file_path)
        print("Columns:", df.columns.tolist())
        print(df.head(2))
    except Exception as e:
        print(f"Error reading {file}: {e}")
    print("\n")
