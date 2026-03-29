import joblib
import numpy as np
import os
import gc
import re
from datetime import datetime
from typing import List, Dict
from app_config import GlobalConfig

class CopyScorerV5:
    """[ONLINE VERSION] 98% 정확도를 지닌 ML 채점기 엔진.
    코사인 엔진의 한계를 극복하고 Render 환경의 512MB RAM 오버플로우를 막기 위해
    내부적으로 철저한 메모리 관리(GC)를 동반하여 동작합니다.
    """
    def __init__(self, use_supabase=False, supabase_url=""):
        # 모델 경로 (컨테이너 내 모델이 포함되어 복구됨)
        os.makedirs(GlobalConfig.MODEL_DIR, exist_ok=True)
        self.files = {
            "reg": os.path.join(GlobalConfig.MODEL_DIR, "viral_model.pkl"),
            "tour": os.path.join(GlobalConfig.MODEL_DIR, "tournament_model.pkl"),
            "hurdle": os.path.join(GlobalConfig.MODEL_DIR, "hurdle_model.pkl")
        }
        
        print(f"🤖 [CopyScorer v5.1] ML AI 엔진을 램에 로드합니다... (경로: {GlobalConfig.MODEL_DIR})")
        
        if not os.path.exists(self.files['tour']):
            print("❌ 오류: 모델 파일이 배포 컨테이너에 존재하지 않습니다. (Git push 누락 의심)")
        
        self.reg_model = joblib.load(self.files['reg'])
        self.hurdle_model = joblib.load(self.files['hurdle'])
        self.tour_model = joblib.load(self.files['tour'])
        print("✅ 98% 정확도 판독 모델 3종 로드 완료.")
        
    def _extract_meta_features(self, text: str, dt: datetime = None) -> np.ndarray:
        """
        젬미니 임베딩(3072) 뒤에 붙을 9개의 메타 피처 생성:
        [day_sin, day_cos, hour_sin, hour_cos, emoji, line, q, ex, text_len]
        """
        if dt is None:
            dt = datetime.now()
            
        # 1. Cyclic Time (4)
        day_sin = np.sin(2 * np.pi * dt.dayofweek / 7)
        day_cos = np.cos(2 * np.pi * dt.dayofweek / 7)
        hour_sin = np.sin(2 * np.pi * dt.hour / 24)
        hour_cos = np.cos(2 * np.pi * dt.hour / 24)
        
        # 2. Style (4)
        if not isinstance(text, str): 
            style = [0, 0, 0, 0]
            t_len = 0
        else:
            emoji_count = len(re.findall(r'[^\w\s,]', text))
            line_count = text.count('\n')
            q_count = text.count('?')
            ex_count = text.count('!')
            style = [emoji_count, line_count, q_count, ex_count]
            t_len = len(text)
            
        return np.array([day_sin, day_cos, hour_sin, hour_cos] + style + [t_len])

    def score_candidates(self, candidates_data: List[Dict], orig_index: int = None) -> List[Dict]:
        """
        candidates_data: [{'text': str, 'embedding': np.ndarray}, ...]
        Gemini 임베딩(3072) + 메타 피처(9) = 3081차원으로 확장하여 채점.
        """
        if not candidates_data or len(candidates_data) == 0:
            return []

        # 현재 시간 (메타 피처용)
        now = datetime.now()

        processed_vecs = []
        valid_mask = []
        for item in candidates_data:
            text = item.get('text', '')
            vec = item.get('embedding')
            
            if vec is None or np.any(np.isnan(vec)) or np.all(vec == 0):
                processed_vecs.append(np.zeros(3081))
                valid_mask.append(False)
            else:
                # 3072 + 9 = 3081
                meta = self._extract_meta_features(text, now)
                full_vec = np.hstack([vec, meta])
                processed_vecs.append(full_vec)
                valid_mask.append(True)
        
        X = np.array(processed_vecs)
        n = len(X)

        reg_scores = np.zeros(n)
        valid_idx_list = [i for i, v in enumerate(valid_mask) if v]
        if valid_idx_list:
            reg_preds = self.reg_model.predict(X[valid_idx_list])
            for i, val in zip(valid_idx_list, reg_preds):
                reg_scores[i] = np.clip(val, 0, 100)

        hurdle_probs = np.zeros(n)
        if valid_idx_list:
            h_probs_raw = self.hurdle_model.predict_proba(X[valid_idx_list])[:, 1]
            for i, val in zip(valid_idx_list, h_probs_raw):
                hurdle_probs[i] = val
        
        results = []
        for i in range(n):
            results.append({
                'index': i,
                'reg_score': float(reg_scores[i]),
                'hurdle_prob': float(hurdle_probs[i]),
                'pass_hurdle': hurdle_probs[i] >= 0.5,
                'final_wins': 0,
                'league_wins': 0
            })

        if orig_index is not None and 0 <= orig_index < n and valid_mask[orig_index]:
            max_beaten_reg = -1.0
            beaten_count = 0
            for j in range(n):
                if j == orig_index or not valid_mask[j]: continue
                p_vec = np.hstack([X[orig_index], X[j]]).reshape(1, -1)
                win_prob = self.tour_model.predict_proba(p_vec)[0, 1]
                if win_prob > 0.5:
                    beaten_count += 1
                    if reg_scores[j] > max_beaten_reg:
                        max_beaten_reg = reg_scores[j]
            
            if beaten_count > 0:
                new_score = max_beaten_reg + 0.05
                reg_scores[orig_index] = new_score
                results[orig_index]['reg_score'] = float(new_score)

        league_participants = sorted([i for i in range(n) if valid_mask[i]], 
                                    key=lambda i: reg_scores[i], reverse=True)[:5]
        wildcards = [i for i in range(n) if valid_mask[i] and results[i]['hurdle_prob'] >= 0.9 and i not in league_participants]
        if wildcards:
            league_participants.extend(wildcards)

        if len(league_participants) > 1:
            for i in range(len(league_participants)):
                for j in range(i + 1, len(league_participants)):
                    idx1, idx2 = league_participants[i], league_participants[j]
                    vec1, vec2 = X[idx1], X[idx2]
                    pair_input = np.hstack([vec1, vec2]).reshape(1, -1)
                    win_prob = self.tour_model.predict_proba(pair_input)[0, 1]
                    if win_prob > 0.5:
                        results[idx1]['league_wins'] += 1
                    else:
                        results[idx2]['league_wins'] += 1

        for res in results:
            res['total_score'] = (res.get('league_wins', 0) * 1000) + reg_scores[res['index']]

        # ★ Memory 최적화 방어 (Render 512MB RAM 극복)
        del X, processed_vecs
        gc.collect()

        return sorted(results, key=lambda x: x['total_score'], reverse=True)
