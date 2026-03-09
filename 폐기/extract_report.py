import pandas as pd
import os
import openpyxl

def extract_report():
    path = r'c:\Users\ding9\Desktop\madoyo\threads_live_report_0214_2101.xlsx'
    
    # Check if file exists
    if not os.path.exists(path):
        print(f"File not found at: {path}")
        return

    try:
        # Read Excel file
        df = pd.read_excel(path)
        
        # Filter for today's date (2/14)
        # Using simple string matching for robustness
        today_df = df[df['작성시간'].astype(str).str.contains('2026-02-14', na=False)] 
        
        # If no today data found, fallback to showing last 10 rows (might be a date format issue)
        target_df = today_df if not today_df.empty else df.tail(10)

        print(f"2/14 총업로드 {len(target_df)}")
        print("")
        
        for _, row in target_df.iterrows():
            link = row.get('게시물주소', 'N/A')
            # Extract title: first line, truncate to 20 chars
            title_full = str(row.get('본문', 'N/A'))
            title = title_full.split('\n')[0][:20] 
            
            views = row.get('본문조회수', 0)
            conv_views = row.get('첫댓글조회수', 0)
            
            print(f"{link}")
            print(f"{title}[조회수 : {views}/ 댓글조회수 : {conv_views}]")
            print("")

    except ImportError:
        print("Required libraries not found. Ensure pandas and openpyxl are installed.")
    except Exception as e:
        print(f"Error reading excel: {e}")

if __name__ == "__main__":
    extract_report()
