import os
import pandas as pd
import numpy as np
import pickle
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found.")
        return

    client = genai.Client(api_key=api_key)
    model_id = "gemini-embedding-001"
    storage_path = "embeddings.pkl"
    
    # Load existing embeddings
    embeddings = {}
    if os.path.exists(storage_path):
        with open(storage_path, "rb") as f:
            embeddings = pickle.load(f)
        # Dimension check
        if embeddings:
            sample = next(iter(embeddings.values()))
            if len(sample) != 3072:
                print("Incorrect dimension in storage. Clearing.")
                embeddings = {}
    
    print(f"Loaded {len(embeddings)} existing embeddings.")

    # Load data to embed
    data_dir = r"c:\Users\ding9\Desktop\madoyo"
    files = [
        os.path.join(data_dir, "데이터 참조", "dotori.xlsx"),
        os.path.join(data_dir, "데이터 참조", "threads_slow_report_0215_0322.xlsx")
    ]
    
    # Also scan "데이터 참조" folder
    ref_dir = os.path.join(data_dir, "데이터 참조")
    if os.path.exists(ref_dir):
        files += [os.path.join(ref_dir, f) for f in os.listdir(ref_dir) if f.endswith(".xlsx")]

    all_texts = set()
    for f in files:
        if os.path.exists(f):
            print(f"Reading {f}...")
            try:
                df = pd.read_excel(f)
                # Find content column
                content_col = None
                for col in df.columns:
                    if '본문' in str(col) or 'Text' in str(col):
                        content_col = col
                        break
                if content_col:
                    texts = df[content_col].dropna().astype(str).unique()
                    all_texts.update(texts)
            except Exception as e:
                print(f"Error reading {f}: {e}")

    missing_texts = [t for t in all_texts if t not in embeddings]
    print(f"Total unique texts: {len(all_texts)}")
    print(f"Missing embeddings: {len(missing_texts)}")

    if not missing_texts:
        print("All texts already embedded!")
        return

    # Batch embedding (Optimized for Paid Tier)
    chunk_size = 100 
    total_missing = len(missing_texts)
    start_time = time.time()
    
    print(f"\n[작동 중] 전공 정밀 분석(임베딩)을 시작합니다. (대상: {total_missing}개)")
    
    for i in range(0, total_missing, chunk_size):
        chunk = missing_texts[i:i+chunk_size]
        chunk_num = i // chunk_size + 1
        total_chunks = (total_missing - 1) // chunk_size + 1
        
        # Calculate progress info
        processed_count = i + len(chunk)
        elapsed = time.time() - start_time
        avg_time = elapsed / processed_count if processed_count > 0 else 0
        remaining = avg_time * (total_missing - processed_count)
        
        print(f"\n[작동 중] {chunk_num}/{total_chunks} 번째 묶음 분석 중... ({processed_count}/{total_missing} 완료)")
        print(f" - 진행률: {processed_count/total_missing*100:.1f}% | 예상 남은 시간: {remaining/60:.1f}분")
        
        retries = 3
        while retries > 0:
            try:
                response = client.models.embed_content(
                    model=model_id,
                    contents=chunk
                )
                for idx, emb in enumerate(response.embeddings):
                    embeddings[chunk[idx]] = emb.values
                
                # Save after every chunk
                with open(storage_path, "wb") as f:
                    pickle.dump(embeddings, f)
                break
            except Exception as e:
                if "429" in str(e):
                    print(f" !!! [일시 중지] API 속도 제한 감지. 30초 대기 후 재시도... (시도 {4-retries}/3)")
                    time.sleep(30)
                    retries -= 1
                else:
                    print(f" !!! [오류] 분석 중 예외 발생: {e}")
                    break
        
        # Throttling to stay safe even with paid tier
        time.sleep(1.0) 

    print("\n[완료] 모든 데이터에 대한 정밀 분석이 성공적으로 마무리되었습니다!")
    print(f" - 총 저장된 데이터: {len(embeddings)}개")

if __name__ == "__main__":
    main()
