import gc
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np

from app_config import GlobalConfig
from api.logging_utils import get_logger, log_event

CandidateData = Dict[str, Any]
ScoreResult = Dict[str, Any]
logger = get_logger(__name__)

class CopyScorerV5:
    """
    [V5 Online Engine] Synchronized with '3072 + 15' Full Force Logic.
    NO PCA. Raw Embedding (3072) + 15 Meta Features = 3087 Dimensions.
    """

    EMBEDDING_DIM = 3072
    LEAGUE_SIZE = 40

    def __init__(self, use_supabase: bool = False, supabase_url: str = ""):
        model_dir = os.path.join(GlobalConfig.BASE_DIR.parent, "embedding_migration")
        log_event(logger, logging.INFO, "copy_scorer.v5.raw_init", model_dir=model_dir)

        try:
            # 1. 메인 회귀 모델 (3087차원 버전)
            # 대표님이 언급하신 '제일 숫자 큰거' 혹은 '가장 큰 용량' 모델 로드
            self.reg_model = joblib.load(os.path.join(model_dir, "viral_model.pkl"))
            self.hurdle_model = joblib.load(os.path.join(model_dir, "hurdle_model.pkl"))

            # 2. 토너먼트 모델 (3072 Raw 대결용)
            self.tour_model = joblib.load(os.path.join(model_dir, "tournament_model.pkl"))

            # 3. 백분위 맵핑 (V16 기준)
            if os.path.exists(os.path.join(model_dir, "percentile_map.pkl")):
                self.p_map = joblib.load(os.path.join(model_dir, "percentile_map.pkl"))
            else:
                self.p_map = None

            log_event(logger, logging.INFO, "copy_scorer.v5.raw_models_loaded")
        except Exception as e:
            log_event(logger, logging.ERROR, "copy_scorer.v5.raw_load_failed", error=str(e))
            raise e

    def extract_hyper_style_15(self, text: str) -> List[float]:
        """[3072+15] 체제의 핵심 15가지 메타 피처 추출."""
        target_time = datetime.now()

        # 1-4. Time Features (4)
        day_sin = np.sin(2 * np.pi * target_time.weekday() / 7)
        day_cos = np.cos(2 * np.pi * target_time.weekday() / 7)
        hour_sin = np.sin(2 * np.pi * target_time.hour / 24)
        hour_cos = np.cos(2 * np.pi * target_time.hour / 24)

        if not isinstance(text, str): return [day_sin, day_cos, hour_sin, hour_cos] + [0.0]*11

        text = text.strip()
        length = len(text) if len(text) > 0 else 1

        # 5-10. Hard Count Style (6)
        emoji_count = len(re.findall(r'[^\w\s,]', text))
        line_count = text.count('\n')
        tag_count = text.count('#')
        mention_count = text.count('@')
        q_count = text.count('?')
        ex_count = text.count('!')

        # 11-14. Ratios & Avg (4)
        emoji_ratio = emoji_count / length
        line_ratio = line_count / length
        q_ratio = q_count / length
        words = text.split()
        avg_word_len = length / max(len(words), 1)

        # 15. Length (1)
        text_len_val = float(length)

        return [day_sin, day_cos, hour_sin, hour_cos,
                float(emoji_count), float(line_count), float(tag_count), float(mention_count),
                float(q_count), float(ex_count), emoji_ratio, line_ratio, q_ratio, avg_word_len, text_len_val]

    def map_to_percentile(self, val: float) -> float:
        if self.p_map is None: return val
        idx = np.searchsorted(self.p_map['targets'], val)
        return float(self.p_map['percentiles'][min(idx, len(self.p_map['percentiles'])-1)])

    def score_candidates(self, candidates_data: List[CandidateData], orig_index: Optional[int] = None) -> List[ScoreResult]:
        """
        [3072 + 15 Pure Power League]
        NO PCA. DIRECT RAW EMBEDDING.
        """
        if not candidates_data: return []

        raw_embeddings = []
        all_meta_15 = []
        valid_mask = []
        processed_vecs_3087 = []

        # 1. 피처 벡터 생성 (3072 + 15)
        for i, item in enumerate(candidates_data):
            vec = item.get("embedding")
            text = item.get("text", "")

            if vec is None or np.any(np.isnan(vec)) or np.all(vec == 0):
                valid_mask.append(False)
                processed_vecs_3087.append(np.zeros(self.EMBEDDING_DIM + 15))
                all_meta_15.append([0.0]*15)
                raw_embeddings.append(np.zeros(self.EMBEDDING_DIM))
            else:
                meta = self.extract_hyper_style_15(text)
                v_full = np.hstack([vec, meta])
                processed_vecs_3087.append(v_full)
                all_meta_15.append(meta)
                raw_embeddings.append(vec)
                valid_mask.append(True)

        X_3087 = np.array(processed_vecs_3087)
        valid_indices = [i for i, v in enumerate(valid_mask) if v]
        if not valid_indices: return []

        # 2. Regression & Hurdle
        reg_scores = np.zeros(len(X_3087))
        v_input = X_3087[valid_indices]

        # Regression Score (Viral Model)
        reg_preds = self.reg_model.predict(v_input)
        for idx_in_valid, val in enumerate(reg_preds):
            idx = valid_indices[idx_in_valid]
            reg_scores[idx] = self.map_to_percentile(val)

        # Hurdle Probability
        hurdle_probs = np.zeros(len(X_3087))
        h_probs_raw = self.hurdle_model.predict_proba(v_input)[:, 1]
        for idx_in_valid, val in enumerate(h_probs_raw):
            idx = valid_indices[idx_in_valid]
            hurdle_probs[idx] = val

        # 3. 결과 객체 초기화
        results = []
        for i in range(len(X_3087)):
            results.append({
                'index': i,
                'reg_score': float(reg_scores[i]),
                'hurdle_prob': float(hurdle_probs[i]),
                'pass_hurdle': hurdle_probs[i] >= 0.5,
                'league_wins': 0
            })

        # 4. Raw Pairwise Tournament (Tournament Model - 77MB)
        finalists = sorted(valid_indices, key=lambda i: reg_scores[i], reverse=True)[:self.LEAGUE_SIZE]

        def compare_pair_raw(idx1: int, idx2: int) -> bool:
            """원본 3072 임베딩을 생으로 대결시키는 거대 토너먼트."""
            v1, v2 = raw_embeddings[idx1], raw_embeddings[idx2]
            # 토너먼트 모델(6144D)은 Raw Embedding 3072+3072만 사용
            tour_input = np.hstack([v1, v2]).reshape(1, -1)
            win_prob = self.tour_model.predict_proba(tour_input)[0, 1]
            return win_prob >= 0.5

        # 원본(Pivot) 보너스 및 리그전
        pivot_idx = orig_index if (orig_index is not None and orig_index in finalists) else finalists[0]

        for f_idx in finalists:
            if f_idx == pivot_idx: continue
            try:
                if compare_pair_raw(f_idx, pivot_idx):
                    results[f_idx]['league_wins'] += 1
                else:
                    results[pivot_idx]['league_wins'] += 1
            except Exception as e:
                # 차원 불일치 등 예외 발생 시 스킵
                continue

        # 원본 보너스 적용 (max_beaten_reg + 0.05)
        if orig_index is not None and valid_mask[orig_index] and orig_index in finalists:
            beaten_others = []
            for idx in finalists:
                if idx == orig_index: continue
                try:
                    if not compare_pair_raw(idx, orig_index):
                        beaten_others.append(idx)
                except: continue

            if beaten_others:
                max_beaten = max(reg_scores[idx] for idx in beaten_others)
                results[orig_index]['reg_score'] = max_beaten + 0.05
                reg_scores[orig_index] = max_beaten + 0.05

        # 총점 합산
        for res in results:
            res['total_score'] = (res.get('league_wins', 0) * 1000) + res['reg_score']

        gc.collect()
        return sorted(results, key=lambda x: x['total_score'], reverse=True)
