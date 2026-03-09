import sys
import os
import pandas as pd
from dotenv import load_dotenv

import io
# Set path
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
base_path = r'c:\Users\ding9\Desktop\madoyo'
sys.path.append(os.path.join(base_path, '작동중코드'))

from data_feedback_loop_v2 import MSSDataIntegrator

class DummyMAB:
    def decay(self): pass
    def update(self, *args, **kwargs): pass
    @property
    def clusters(self): return {}

def main():
    integrator = MSSDataIntegrator(base_path)
    df = integrator.process_all_data(DummyMAB())
    
    if df.empty:
        print("No data.")
        return
        
    top_posts = df.sort_values('MSS', ascending=False).head(5)
    print("--- TOP 5 PERFORMANCE PATTERNS ---")
    for i, row in top_posts.iterrows():
        print(f"MSS: {row['MSS']:.1f}")
        print(f"Content: {row['본문']}")
        print("-" * 30)

if __name__ == "__main__":
    main()
