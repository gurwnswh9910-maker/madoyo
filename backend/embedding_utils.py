import os
import numpy as np
from google import genai
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from api.database import SessionLocal, MABEmbedding, User
from sqlalchemy import text as sql_text

load_dotenv()

class EmbeddingManager:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_id = "gemini-embedding-001"
        
        if self.api_key:
            print(f"Initializing Gemini API Client (Model: {self.model_id})...")
            self.client = genai.Client(api_key=self.api_key)
        else:
            print("Error: GEMINI_API_KEY not found. Using DB-only mode.")
            self.client = None

    def get_embedding(self, text):
        text = str(text).strip()
        if not text:
            return None
        
        db: Session = SessionLocal()
        try:
            # 1. Check DB first
            entry = db.query(MABEmbedding).filter(MABEmbedding.content_text == text).first()
            if entry and entry.embedding:
                return entry.embedding
            
            # 2. Fetch from Gemini if not found
            if not self.client:
                return [0.0] * 3072 # Mock if no client
            
            result = self.client.models.embed_content(
                model=self.model_id,
                contents=text
            )
            vector = result.embeddings[0].values
            
            # 3. Save to DB (as global/system entry by default)
            new_entry = MABEmbedding(
                content_text=text,
                embedding=vector,
                is_global=True,
                metadata_json={"source": "api_on_demand"}
            )
            db.add(new_entry)
            db.commit()
            return vector
            
        except Exception as e:
            print(f"Error in get_embedding: {e}")
            return None
        finally:
            db.close()

    def search_weighted(self, query_text, current_user_id=None, limit=5):
        """
        DATABASE NATIVE WEIGHTED SEARCH
        Weight Rules: My SNS (1.5) > My Uploaded (1.0) > Global (0.5)
        """
        query_vec = self.get_embedding(query_text)
        if not query_vec:
            return []
        
        db: Session = SessionLocal()
        try:
            # Convert vector to string format for pgvector
            vec_str = "[" + ",".join(map(str, query_vec)) + "]"
            
            # SQL logic for weighted similarity
            # 1 - (vec <=> query_vec) is similarity (0 to 1 range, usually)
            # We multiply by weight and mss_score bonus
            query = sql_text("""
                SELECT 
                    content_text, 
                    mss_score,
                    metadata_json,
                    (1 - (embedding <=> :vec)) as similarity,
                    (
                        CASE 
                            WHEN uploader_id = :uid AND metadata_json->>'type' = 'sns' THEN 1.5
                            WHEN uploader_id = :uid THEN 1.0
                            WHEN is_global = True THEN 0.5
                            ELSE 0.1
                        END
                    ) as weight
                FROM mab_embeddings
                ORDER BY ( (1 - (embedding <=> :vec)) * 
                           (CASE 
                                WHEN uploader_id = :uid AND metadata_json->>'type' = 'sns' THEN 1.5
                                WHEN uploader_id = :uid THEN 1.0
                                WHEN is_global = True THEN 0.5
                                ELSE 0.1
                            END) * 
                           (1 + ln(mss_score + 1)) ) DESC
                LIMIT :limit
            """)
            
            result = db.execute(query, {"vec": vec_str, "uid": current_user_id, "limit": limit})
            
            matches = []
            for row in result:
                matches.append({
                    "text": row.content_text,
                    "mss": row.mss_score,
                    "similarity": row.similarity,
                    "weight": row.weight,
                    "metadata": row.metadata_json
                })
            return matches
            
        except Exception as e:
            print(f"Weighted search failed: {e}")
            return []
        finally:
            db.close()

    # Legacy compatibility methods
    def get_many_embeddings(self, texts):
        return [self.get_embedding(t) for t in texts]

    def get_embeddings_matrix(self, texts):
        vectors = self.get_many_embeddings(texts)
        return np.array([v if v is not None else np.zeros(3072) for v in vectors])
