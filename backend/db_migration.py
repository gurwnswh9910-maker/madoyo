import os
import pickle
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from db_init import SessionLocal, User, MABEmbedding, Generation
from data_feedback_loop_v2 import MSSDataIntegrator
from dotenv import load_dotenv
import uuid

load_dotenv()

def migrate_data():
    db: Session = SessionLocal()
    try:
        # 1. Create Default User (System/Admin)
        admin_user = db.query(User).filter(User.email == "admin@madoyo.io").first()
        if not admin_user:
            print("Creating default admin user...")
            admin_user = User(
                id=uuid.uuid4(),
                email="admin@madoyo.io",
                plan="enterprise",
                credits=999999
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
        
        # 2. Setup Data Integrator (using existing logic)
        root_dir = r"C:\Users\ding9\Desktop\madoyo"
        integrator = MSSDataIntegrator(root_dir)
        
        # Load local data (as per data_feedback_loop_v2 logic)
        print("Processing all local excel data...")
        df_total = integrator.process_all_data(integrator.mab, use_cache=False)
        
        # Load local embeddings
        print("Loading local embeddings.pkl...")
        emb_manager = integrator.embed_mgr
        local_embs = emb_manager.embeddings # {text: vector}
        
        print(f"Found {len(df_total)} posts in excels and {len(local_embs)} embeddings.")
        
        # 3. Migrate to mab_embeddings table
        # We'll use the df_total which already handles is_user flag
        print("Migrating to mab_embeddings table...")
        
        # Track migrated texts to avoid duplicates and handle orphans (embeddings without excel entry)
        migrated_texts = set()
        
        # First, migrate from excels (with MSS and metadata)
        batch_size = 100
        buffer = []
        
        # Helper for cleaning numeric strings in migration
        def safe_int(val):
            if pd.isna(val): return 0
            if isinstance(val, (int, float)): return int(val)
            # Use the same logic as parse_views but return int
            s = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
            try:
                multiplier = 1
                if '천' in s: multiplier = 1000; s = s.replace('천', '')
                elif '만' in s: multiplier = 10000; s = s.replace('만', '')
                return int(float(s) * multiplier)
            except: return 0

        for i, row in df_total.iterrows():
            text = row['본문']
            if pd.isna(text) or not str(text).strip():
                continue
                
            text = str(text).strip()
            vec = local_embs.get(text)
            
            # If no embedding in pkl, skip or generate? 
            # In Phase 1, we expect them to be there. If not, integrator already tried in process_all_data.
            if vec is None: continue
            
            is_user = row.get('is_user', False)
            
            mab_entry = MABEmbedding(
                uploader_id=admin_user.id if is_user else None,
                is_global=not is_user,
                content_text=text,
                embedding=vec,
                mss_score=float(row.get('MSS', 0.0)),
                metadata_json={
                    "type": "sns" if is_user else "external",
                    "url": str(row.get('링크', '')),
                    "created_at": str(row.get('작성시간', '')),
                    "metrics": {
                        "views": safe_int(row.get('본문조회수')),
                        "likes": safe_int(row.get('좋아요')),
                    }
                }
            )
            buffer.append(mab_entry)
            migrated_texts.add(text)
            
            if len(buffer) >= batch_size:
                db.add_all(buffer)
                db.commit()
                print(f"   Migrated {i+1} records...")
                buffer = []
        
        # Handle orphan embeddings (those in pkl but NOT in current excels)
        print("Checking for orphan embeddings...")
        orphan_count = 0
        for text, vec in local_embs.items():
            if text not in migrated_texts:
                mab_entry = MABEmbedding(
                    uploader_id=None,
                    is_global=True,
                    content_text=text,
                    embedding=vec,
                    mss_score=0.0,
                    metadata_json={"type": "legacy_orphan"}
                )
                buffer.append(mab_entry)
                orphan_count += 1
                if len(buffer) >= batch_size:
                    db.add_all(buffer)
                    db.commit()
                    buffer = []
        
        if buffer:
            db.add_all(buffer)
            db.commit()
            
        print(f"Migration successful! Total migrated from excels: {len(migrated_texts)}, Orphans: {orphan_count}")

    except Exception as e:
        db.rollback()
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    migrate_data()
