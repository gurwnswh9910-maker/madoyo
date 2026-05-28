import joblib
import numpy as np
import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from app_config import GlobalConfig

# 모델 경로 (GlobalConfig 기반)
_MODEL_DIR = GlobalConfig.BASE_DIR / 'embedding_migration'

class CopyScorerV4:
    """
    [CopyScorer v4.5] 3072+9 통합 피처 시스템
    NO PCA. Raw Embedding (3072) + 9 Meta Features = 3081 Dimensions.
    Synchronized with viral_model.pkl (Ridge) and hurdle_model.pkl (RF).
    """
    def __init__(self):
        print("🤖 [CopyScorer v4.5] 3081-D 고정밀 엔진 로드 중...")
        
        model_dir = str(_MODEL_DIR)
        
        try:
            # 1. 3081차원 통합 모델 로드
            self.reg_model = joblib.load(os.path.join(model_dir, "viral_model.pkl"))
            self.hurdle_model = joblib.load(os.path.join(model_dir, "hurdle_model.pkl"))
            self.p_map = joblib.load(os.path.join(model_dir, "percentile_map.pkl"))
            
            # 2. 토너먼트 모델 로드 (6144차원 = 3072 * 2 Raw 대결)
            # Tournament v8 is the most advanced version provided
            self.tour_model = joblib.load(os.path.join(model_dir, "tournament_model.pkl"))
            
            print(f"✅ 3081-D 모델 로드 완료 (Reg Features: {self.reg_model.n_features_in_})")
        except Exception as e:
            print(f"❌ Scorer 로드 중 기술적 오류 발생: {str(e)}")
            raise e

    def extract_style_3081(self, text: str, target_time: datetime = None) -> List[float]:
        """
        [3081-D Spec]
        1-4: Time Cyclic (4)
        5-8: Style Counts (4)
        9: Text Length (1)
        Total: 9 meta features.
        """
        if target_time is None: target_time = datetime.now()
        
        # 1-4. Time Features (Cyclic)
        day_sin = np.sin(2 * np.pi * target_time.weekday() / 7)
        day_cos = np.cos(2 * np.pi * target_time.weekday() / 7)
        hour_sin = np.sin(2 * np.pi * target_time.hour / 24)
        hour_cos = np.cos(2 * np.pi * target_time.hour / 24)
        
        if not isinstance(text, str): 
            return [day_sin, day_cos, hour_sin, hour_cos, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        text = text.strip()
        length = float(len(text))
        
        # 5-8. Style Features (Exact match with train_scorer_v5.py)
        emoji_count = float(len(re.findall(r'[^\w\s,]', text)))
        line_count = float(text.count('\n'))
        q_count = float(text.count('?'))
        ex_count = float(text.count('!'))
        
        # 9. Text Length
        return [day_sin, day_cos, hour_sin, hour_cos, 
                emoji_count, line_count, q_count, ex_count, 
                length]

    def map_to_percentile(self, val: float) -> float:
        if self.p_map is None: return val
        # Ridge model output is in log1p space (0~10+), map to 0~100 percentile
        idx = np.searchsorted(self.p_map['targets'], val)
        return float(self.p_map['percentiles'][min(idx, len(self.p_map['percentiles'])-1)])

    def score_candidates(self, candidates_embeddings: np.ndarray, orig_index: int = None, target_time: datetime = None, candidate_texts: List[str] = None) -> List[Dict]:
        """
        [3081 Pure Power League]
        NO PCA. DIRECT RAW EMBEDDING + 9 META FEATURES.
        """
        if candidates_embeddings is None or len(candidates_embeddings) == 0:
            return []

        if target_time is None: target_time = datetime.now()

        processed_vecs_3081 = []
        raw_embeddings = []
        valid_mask = []

        for i, vec in enumerate(candidates_embeddings):
            if vec is None or np.any(np.isnan(vec)) or np.all(vec == 0):
                processed_vecs_3081.append(np.zeros(3081))
                raw_embeddings.append(np.zeros(3072))
                valid_mask.append(False)
            else:
                text = candidate_texts[i] if candidate_texts and i < len(candidate_texts) else ""
                meta = self.extract_style_3081(text, target_time)
                v_full = np.hstack([vec, meta])
                processed_vecs_3081.append(v_full)
                raw_embeddings.append(vec)
                valid_mask.append(True)
        
        X_3081 = np.array(processed_vecs_3081)
        valid_indices = [i for i, v in enumerate(valid_mask) if v]
        if not valid_indices: return []

        # 1. Regression & Hurdle (3081-D)
        reg_scores = np.zeros(len(X_3081))
        hurdle_probs = np.zeros(len(X_3081))
        
        v_input = X_3081[valid_indices]
        
        # Regression
        reg_preds = self.reg_model.predict(v_input)
        for i, val in zip(valid_indices, reg_preds):
            reg_scores[i] = self.map_to_percentile(val)
            
        # Hurdle
        h_probs_raw = self.hurdle_model.predict_proba(v_input)[:, 1]
        for i, val in zip(valid_indices, h_probs_raw):
            hurdle_probs[i] = val
            
        results = []
        for i in range(len(X_3081)):
            results.append({
                'index': i,
                'reg_score': float(reg_scores[i]),
                'hurdle_prob': float(hurdle_probs[i]),
                'pass_hurdle': hurdle_probs[i] >= 0.5,
                'league_wins': 0
            })

        # 2. Tournament (High-Efficiency Timsort Refinement)
        # STEP A: Get Top 40 by Regression Score as Initial Pool
        initial_pool_indices = sorted(valid_indices, key=lambda i: reg_scores[i], reverse=True)[:40]
        
        def compare_pair_raw(idx1: int, idx2: int) -> bool:
            """Tournament Model Comparator: Returns True if idx1 wins over idx2."""
            v1, v2 = raw_embeddings[idx1], raw_embeddings[idx2]
            tour_input = np.hstack([v1, v2]).reshape(1, -1)
            try:
                # 6144-D Model Prediction
                win_prob = self.tour_model.predict_proba(tour_input)[0, 1]
                return win_prob >= 0.5
            except:
                # Fallback to Regression Score
                return reg_scores[idx1] >= reg_scores[idx2]

        # STEP B: Qualifier - Only keep those that beat the Original
        if orig_index is not None:
            # finalists are those in initial pool who outperform the original
            finalists_indices = [i for i in initial_pool_indices if i == orig_index or compare_pair_raw(i, orig_index)]
            print(f"      🏆 [Tournament Qualifier] {len(finalists_indices)}/40 candidates outperformed Original.")
        else:
            finalists_indices = initial_pool_indices

        # STEP C: Timsort League - Sort the winners using the Tournament Model
        from functools import cmp_to_key
        def tournament_cmp(idx_a, idx_b):
            if compare_pair_raw(idx_a, idx_b): return -1 # idx_a is better
            return 1 # idx_b is better

        # Timsort is O(N log N) and optimized for nearly-sorted data
        # Since finalists_indices is already sorted by reg_score, this is extremely efficient.
        sorted_finalists = sorted(finalists_indices, key=cmp_to_key(tournament_cmp))
        
        # 3. Score Mapping & Final Aggregation
        # Winners get a significantly higher base score based on tournament rank
        for rank, f_idx in enumerate(sorted_finalists):
            # Tournament Rank Score: 5000 for #1, decreasing by 50 per rank
            tour_score = max(0, 5000 - (rank * 50))
            results[f_idx]['total_score'] = tour_score + (results[f_idx]['reg_score'] / 10.0) # Reg score as minor tie-breaker
            results[f_idx]['league_wins'] = len(sorted_finalists) - rank - 1 # Proxy for wins

        # Non-finalists (defeated by Original) keep their reg_score but rank lower
        for i, res in enumerate(results):
            if 'total_score' not in res:
                res['total_score'] = res['reg_score']

        return sorted(results, key=lambda x: x['total_score'], reverse=True)

if __name__ == "__main__":
    # Self-test for 3081 Dimension Consistency
    try:
        scorer = CopyScorerV4()
        dummy_vecs = np.random.randn(5, 3072)
        dummy_texts = ["오늘의 핫딜! 사야할 물건 #추천 #쿠팡" for _ in range(5)]
        res = scorer.score_candidates(dummy_vecs, candidate_texts=dummy_texts)
        print(f"✅ Scorer V4.5 (3081-D) Dry Run Successful. Top Score: {res[0]['total_score']:.2f}")
    except Exception as e:
        print(f"❌ Scorer V4.5 (3081-D) Dry Run Failed: {str(e)}")
        import traceback
        traceback.print_exc()
