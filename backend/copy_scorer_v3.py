import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from api.database import SessionLocal, MABEmbedding
from sqlalchemy import text as sql_text

class CopyScorer:
    def __init__(self, embedding_manager=None):
        self.emb_mgr = embedding_manager
        self.ref_vectors = {} # {key: vector}

    def prepare_reference_vectors(self, product_info="", user_id=None):
        """
        DATABASE NATIVE: 
        Fetch top-performing and low-performing vectors from DB to set scoring anchors.
        """
        if self.emb_mgr is None: return
        
        db: Session = SessionLocal()
        try:
            # 1. Fetch Top 5% Global or User-specific data
            # Logic: Higher MSS is better.
            top_query = db.query(MABEmbedding).filter(MABEmbedding.embedding_type.in_(["text", "multi"])).order_by(MABEmbedding.mss_score.desc()).limit(20).all()
            top_vectors = [np.array(e.embedding) for e in top_query if e.embedding is not None]
            if top_vectors:
                self.ref_vectors['avg_top'] = np.mean(top_vectors, axis=0).reshape(1, -1)
            
            # 2. Fetch Low 10% 
            low_query = db.query(MABEmbedding).filter(MABEmbedding.embedding_type.in_(["text", "multi"]), MABEmbedding.mss_score > 0).order_by(MABEmbedding.mss_score.asc()).limit(10).all()
            low_vectors = [np.array(e.embedding) for e in low_query if e.embedding is not None]
            if low_vectors:
                self.ref_vectors['avg_low'] = np.mean(low_vectors, axis=0).reshape(1, -1)
            else:
                self.ref_vectors['avg_low'] = None

            # 3. Product Info Vector
            if product_info:
                text_to_embed = product_info
                if isinstance(product_info, dict):
                    text_to_embed = product_info.get('marketing_insight') or product_info.get('insight') or str(product_info)
                
                prod_vector = self.emb_mgr.get_text_embedding(text_to_embed)
                if prod_vector is not None:
                    self.ref_vectors['product'] = np.array(prod_vector).reshape(1, -1)
        finally:
            db.close()

    def score_batch(self, candidates, product_info="", user_id=None):
        """
        Score a batch of candidates based on cached reference vectors.
        """
        from sklearn.metrics.pairwise import cosine_similarity # Import here for speed
        
        if not self.ref_vectors:
            self.prepare_reference_vectors(product_info, user_id)
            
        avg_top = self.ref_vectors.get('avg_top')
        avg_low = self.ref_vectors.get('avg_low')
        prod_vec = self.ref_vectors.get('product')
        
        if avg_top is None:
            return [{"id": c['id'], "copy": c['copy'], "score_data": {"mss_score_estimate": 0, "reason": "Anchor vectors missing"}} for c in candidates]

        cand_vectors = np.array([c['embedding'] for c in candidates])
        
        sim_top = cosine_similarity(cand_vectors, avg_top).flatten()
        sim_low = cosine_similarity(cand_vectors, avg_low).flatten() if avg_low is not None else np.zeros(len(candidates))
        
        if prod_vec is not None:
            sim_domain = cosine_similarity(cand_vectors, prod_vec).flatten()
        else:
            sim_domain = sim_top

        results = []
        for i, c in enumerate(candidates):
            d_sim = sim_domain[i]
            s_top = sim_top[i]
            s_low = sim_low[i]
            
            # Semantic Penalty (contextual alignment)
            semantic_multiplier = (max(0, d_sim) ** 3) * 2.0
            raw_base_score = (s_top * 100) - (s_low * 20)
            final_score = raw_base_score * semantic_multiplier
            
            level = "평타"
            if final_score > 75: level = "초대박"
            elif final_score > 60: level = "대박"
            elif final_score < 40: level = "망함"

            results.append({
                "id": c['id'],
                "copy": c['copy'],
                "strategy": c.get('strategy', 'unknown'),
                "score_data": {
                    "predicted_mss_level": level,
                    "mss_score_estimate": int(final_score * 300),
                    "reason": f"초고성과 유사도 {s_top*100:.1f}% (DB 기반 검증)"
                }
            })
        return results

    def score_by_embedding(self, candidate_copy: str, product_info: str = "", user_id=None) -> dict:
        if not self.ref_vectors:
            self.prepare_reference_vectors(product_info, user_id)
        
        cand_vector = np.array(self.emb_mgr.get_text_embedding(candidate_copy)).reshape(1, -1)
        batch_res = self.score_batch([{"id": "single", "copy": candidate_copy, "embedding": cand_vector[0]}], product_info, user_id)
        return batch_res[0]["score_data"]

    def select_top_3(self, scored_candidates):
        sorted_list = sorted(
            scored_candidates, 
            key=lambda x: x['score_data'].get('mss_score_estimate', 0),
            reverse=True
        )
        return sorted_list[:3]
