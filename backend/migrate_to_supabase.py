
import os
import pickle
import pandas as pd
import numpy as np
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import glob
import hashlib
import json

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_hash(text):
    return hashlib.md5(text.encode()).hexdigest()

def migrate():
    print("🚀 Starting Migration to Supabase...")
    
    # 1. Load Embeddings
    pkl_path = os.path.join("..", "embeddings_v2_final.pkl")
    embeddings_data = {}
    if os.path.exists(pkl_path):
        with open(pkl_path, "rb") as f:
            embeddings_data = pickle.load(f)
            print(f"✅ Loaded {len(embeddings_data.get('text', {}))} text embeddings from PKL.")
    
    # 2. Connect to DB
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    # 3. Process XLSX files
    xlsx_files = glob.glob(os.path.join("..", "threads_live_report_*.xlsx"))
    xlsx_files += glob.glob(os.path.join("..", "threads_report_*.xlsx"))
    
    total_migrated = 0
    
    for file in xlsx_files:
        print(f"📖 Processing {file}...")
        try:
            df = pd.read_excel(file)
            # Normalize columns
            df.columns = [c.strip() for c in df.columns]
            
            for _, row in df.iterrows():
                content = str(row.get('본문', '')).strip()
                url = str(row.get('링크', '')).strip()
                mss = float(row.get('MSS', 0))
                
                if not content or content == "nan": continue
                
                # Check duplication in DB (by content hash or URL)
                cur.execute("SELECT id FROM mab_embeddings WHERE content_text = %s", (content,))
                if cur.fetchone(): continue
                
                # Get Embedding
                c_hash = get_hash(content)
                vec = embeddings_data.get('text', {}).get(c_hash)
                if vec is None:
                    vec = embeddings_data.get('text', {}).get(content) # fallback
                
                # Prepare Metadata
                meta = {
                    "source_file": file,
                    "likes": int(row.get('좋아요', 0)) if '좋아요' in row else 0,
                    "replies": int(row.get('댓글', 0)) if '댓글' in row else 0,
                    "url": url
                }
                
                # Insert to mab_embeddings
                if vec is not None:
                    vec_list = vec.tolist() if isinstance(vec, np.ndarray) else vec
                    cur.execute(
                        "INSERT INTO mab_embeddings (content_text, embedding, mss_score, is_global, metadata_json) VALUES (%s, %s, %s, %s, %s)",
                        (content, vec_list, mss, True, json.dumps(meta))
                    )
                    total_migrated += 1
                
            conn.commit()
        except Exception as e:
            print(f"❌ Error processing {file}: {e}")
            conn.rollback()

    print(f"🎉 Migration Complete! Total items migrated: {total_migrated}")
    cur.close()
    conn.close()

if __name__ == "__main__":
    migrate()
