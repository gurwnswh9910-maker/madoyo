import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity

class CopyScorer:
    def __init__(self, embedding_manager=None):
        self.emb_mgr = embedding_manager
        self.ref_vectors = {} # {key: vector}

    def prepare_reference_vectors(self, top_posts_df, product_info=""):
        """
        초고성과/저성과/제품 정보를 기반으로 한 번만 계산될 채점 기준 벡터를 캐싱함
        """
        if self.emb_mgr is None: return
        
        # 1. 초고성과(Top 5%) 평균 벡터
        top_5_percent = top_posts_df.nlargest(max(1, len(top_posts_df)//20), 'MSS')
        top_texts = top_5_percent['본문'].tolist()
        top_vectors = np.array([self.emb_mgr.get_embedding(t) for t in top_texts if self.emb_mgr.get_embedding(t) is not None])
        if len(top_vectors) > 0:
            self.ref_vectors['avg_top'] = np.mean(top_vectors, axis=0).reshape(1, -1)
        
        # 2. 저성과 평균 벡터
        low_posts = top_posts_df.nsmallest(max(1, len(top_posts_df)//10), 'MSS')
        low_vectors = np.array([self.emb_mgr.get_embedding(t) for t in low_posts.get('본문', []) 
                                if self.emb_mgr.get_embedding(t) is not None])
        if len(low_vectors) > 0:
            self.ref_vectors['avg_low'] = np.mean(low_vectors, axis=0).reshape(1, -1)
        else:
            self.ref_vectors['avg_low'] = None

        # 3. 제품 정보 벡터
        if product_info:
            if isinstance(product_info, dict):
                text_to_embed = product_info.get('marketing_insight') or product_info.get('insight') or str(product_info)
            else:
                text_to_embed = product_info
                
            prod_vector = self.emb_mgr.get_embedding(text_to_embed)
            if prod_vector is not None:
                self.ref_vectors['product'] = np.array(prod_vector).reshape(1, -1)

    def score_batch(self, candidates, top_posts_df, product_info=""):
        """
        여러 카피 후보를 행렬 연산으로 일괄 채점함
        candidates: list of dicts {'id', 'copy', 'embedding'}
        """
        if not self.ref_vectors:
            self.prepare_reference_vectors(top_posts_df, product_info)
            
        avg_top = self.ref_vectors.get('avg_top')
        avg_low = self.ref_vectors.get('avg_low')
        prod_vec = self.ref_vectors.get('product')
        
        if avg_top is None:
            return [{"id": c['id'], "copy": c['copy'], "score_data": {"mss_score_estimate": 0, "reason": "Ref vectors missing"}} for c in candidates]

        # 모든 후보의 임베딩을 하나의 행렬로 결합
        cand_vectors = np.array([c['embedding'] for c in candidates])
        
        # 유사도 일괄 계산
        sim_top = cosine_similarity(cand_vectors, avg_top).flatten()
        sim_low = cosine_similarity(cand_vectors, avg_low).flatten() if avg_low is not None else np.zeros(len(candidates))
        
        # 도메인 유사도 (제품 정보가 있으면 제품 벡터와, 없으면 Top 평균과 비교)
        if prod_vec is not None:
            sim_domain = cosine_similarity(cand_vectors, prod_vec).flatten()
        else:
            sim_domain = sim_top

        results = []
        for i, c in enumerate(candidates):
            d_sim = sim_domain[i]
            s_top = sim_top[i]
            s_low = sim_low[i]
            
            # 의미론적 페널티 (3제곱 스케일링)
            semantic_multiplier = (max(0, d_sim) ** 3) * 2.0
            
            raw_base_score = (s_top * 100) - (s_low * 20)
            final_score = raw_base_score * semantic_multiplier
            
            # 저품질 키워드 패널티 (1/2, Access Denied 등)
            penalty_applied = False
            low_quality_patterns = [r'\d+\s*/\s*\d+', 'access denied', '액세스 거부']
            import re
            for pattern in low_quality_patterns:
                if re.search(pattern, c['copy'].lower()):
                    final_score *= 0.5
                    penalty_applied = True
                    break
            
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
                    "reason": f"초고성과 유사도 {s_top*100:.1f}% (문맥 페널티 적용됨)" + (" (저품질 패턴 감지 패널티 50% 적용)" if penalty_applied else "")
                }
            })
        return results

    def score_by_embedding(self, candidate_copy: str, top_posts_df: pd.DataFrame, product_info: str = "") -> dict:
        # 하위 호환성을 위해 유지하되, 내부적으로 ref_vectors 사용 가능하도록 수정
        if not self.ref_vectors:
            self.prepare_reference_vectors(top_posts_df, product_info)
        
        cand_vector = np.array(self.emb_mgr.get_embedding(candidate_copy)).reshape(1, -1)
        batch_res = self.score_batch([{"id": "single", "copy": candidate_copy, "embedding": cand_vector[0]}], top_posts_df, product_info)
        return batch_res[0]["score_data"]

    def select_top_3(self, scored_candidates):
        """
        scored_candidates: list of {'copy': text, 'score_data': dict}
        """
        sorted_list = sorted(
            scored_candidates, 
            key=lambda x: x['score_data'].get('mss_score_estimate', 0),
            reverse=True
        )
        return sorted_list[:3]
