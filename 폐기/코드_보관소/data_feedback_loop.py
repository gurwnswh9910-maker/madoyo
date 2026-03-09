import pandas as pd
import glob
import os
from datetime import datetime
from mab_engine import RecencyWeightedMAB

class ThreadsDataIntegrator:
    def __init__(self, data_dir, mab_engine):
        self.data_dir = data_dir
        self.mab = mab_engine

    def load_and_update(self):
        # find all threads live report files
        files = glob.glob(os.path.join(self.data_dir, "threads_live_report_*.xlsx"))
        if not files:
            print("No report files found.")
            return

        for file in files:
            try:
                # Extract date from filename if possible (e.g., threads_live_report_0209_0243.xlsx)
                # For simplicity, we use the file modification time if name parsing is complex
                file_time = datetime.fromtimestamp(os.path.getmtime(file))
                
                df = pd.read_excel(file)
                
                # Assume columns: 'Text', 'Likes', 'Replies', 'Reposts', 'Quotes'
                # In a real scenario, we'd need to classify the 'Text' into one of the MAB arms
                # For this demo, we'll use a dummy classification or keyword matching
                
                for _, row in df.iterrows():
                    text = str(row.get('Text', ''))
                    arm = self.classify_text(text)
                    
                    # Calculate reward (normalized engagement)
                    # Reward = (Likes*1 + Replies*3 + Reposts*5) / MaxScale
                    likes = row.get('Likes', 0)
                    replies = row.get('Replies', 0)
                    reposts = row.get('Reposts', 0)
                    
                    raw_score = likes + replies * 3 + reposts * 5
                    # Simple normalization (should be tuned based on actual data distribution)
                    reward = min(raw_score / 100.0, 1.0) 
                    
                    self.mab.update(arm, reward, timestamp=file_time)
                    
            except Exception as e:
                print(f"Error processing {file}: {e}")

    def classify_text(self, text):
        """Simplistic keyword-based classification into MAB arms."""
        text = text.lower()
        if any(kw in text for kw in ['방법', '팁', '레시피', '저장', '공유']):
            return 'Sharing'
        if any(kw in text for kw in ['미쳤다', '당황', '인생', '소름']):
            return 'Emotion'
        if any(kw in text for kw in ['전후', '비교', '반응', '친구']):
            return 'Reaction'
        return 'Authority' # Default arm

if __name__ == "__main__":
    from copy_generator import CopyGenerator
    
    # Initialize components
    mab = RecencyWeightedMAB(['Authority', 'Reaction', 'Sharing', 'Emotion'], gamma=0.9)
    integrator = ThreadsDataIntegrator(r'c:\Users\ding9\Desktop\madoyo', mab)
    
    # Load past data and update MAB
    print("Updating MAB from historical reports...")
    integrator.load_and_update()
    
    print("Final MAB Stats after history loading:")
    print(mab.get_stats())
    
    # Generate copy based on best-performing arm
    best_arm = mab.select_arm()
    generator = CopyGenerator()
    product = "자취생 필수템, 3분 만에 끝내는 배수구 세정제"
    
    prompt = generator.generate_prompt(best_arm, product)
    print(f"\nRecommended Strategy: {best_arm}")
    print(f"Generated Prompt:\n{prompt}")
