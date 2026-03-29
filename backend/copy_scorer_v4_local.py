import joblib
import numpy as np
import os
from typing import List, Dict
from app_config import GlobalConfig

# 모델 경로 (GlobalConfig 기반)
_MODEL_DIR = GlobalConfig.BASE_DIR / 'embedding_migration'
REG_PATH = _MODEL_DIR / 'viral_model.pkl'
TOUR_PATH = _MODEL_DIR / 'tournament_model.pkl'
HURDLE_PATH = _MODEL_DIR / 'hurdle_model.pkl'

class CopyScorerV4:
    def __init__(self):
        print(f"🤖 [CopyScorer v4.3.2] 로컬 AI 엔진 로드 중... (경로: {_MODEL_DIR})")
        if not REG_PATH.exists():
            print(f"❌ 오류: 모델 파일을 찾을 수 없습니다: {REG_PATH}")
        self.reg_model = joblib.load(REG_PATH)
        self.tour_model = joblib.load(TOUR_PATH)
        self.hurdle_model = joblib.load(HURDLE_PATH)
        print("✅ 모든 판독 모델 로드 완료.")

    def score_candidates(self, candidates_embeddings: np.ndarray, orig_index: int = None) -> List[Dict]:
        """
        입력된 카피 벡터들에 대해 정밀 판독 수행.
        orig_index가 주어지면 해당 원본 카피를 기준으로 벤치마크 수행.
        """
        if candidates_embeddings is None or len(candidates_embeddings) == 0:
            return []

        # 0. 전처리
        processed_vecs = []
        valid_mask = []
        for vec in candidates_embeddings:
            if vec is None or np.any(np.isnan(vec)) or np.all(vec == 0):
                processed_vecs.append(np.zeros(3072))
                valid_mask.append(False)
            else:
                processed_vecs.append(vec)
                valid_mask.append(True)
        
        X = np.array(processed_vecs)
        n = len(X)

        # 1. 1차 필터링: 회귀 점수 산출
        reg_scores = np.zeros(n)
        valid_idx_list = [i for i, v in enumerate(valid_mask) if v]
        if valid_idx_list:
            reg_preds = self.reg_model.predict(X[valid_idx_list])
            for i, val in zip(valid_idx_list, reg_preds):
                reg_scores[i] = np.clip(val, 0, 100)

        # 2. 2차 필터링: P90 허들 검사
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
                'final_wins': 0
            })

        # [Phase 1] 글로벌 벤치마크 및 실력 기반 점수 보정
        # 원본이 이긴 상대 중 가장 강한 놈보다 0.05점 높게 설정하여 실질적 위상 반영
        if orig_index is not None and 0 <= orig_index < n and valid_mask[orig_index]:
            max_beaten_reg = -1.0
            beaten_count = 0
            
            print(f"    🔍 [Benchmark] 원본 vs 도전자 전원(n={n-1}) 매치 시작...")
            for j in range(n):
                if j == orig_index or not valid_mask[j]: continue
                
                p_vec = np.hstack([X[orig_index], X[j]]).reshape(1, -1)
                win_prob = self.tour_model.predict_proba(p_vec)[0, 1]
                
                if win_prob > 0.5: # 원본 승리
                    beaten_count += 1
                    if reg_scores[j] > max_beaten_reg:
                        max_beaten_reg = reg_scores[j]
            
            # [PROMOTION] 실력에 따른 점수 상향 조정
            if beaten_count > 0:
                new_score = max_beaten_reg + 0.05
                print(f"    🚀 [Promotion] 원본이 {beaten_count}명을 꺾고 점수 승격: {reg_scores[orig_index]:.1f} -> {new_score:.1f}")
                reg_scores[orig_index] = new_score
                results[orig_index]['reg_score'] = float(new_score)
            else:
                print(f"    ⚠️ [Benchmark] 원본이 모든 대결에서 패배하여 점수를 유지합니다.")

        # [Phase 2] 결승 리그 선발 (승격된 점수 기반)
        league_participants = sorted([i for i in range(n) if valid_mask[i]], 
                                    key=lambda i: reg_scores[i], reverse=True)[:5]
        
        # P90 허들 돌파 와일드카드 (여전히 유효)
        wildcards = [i for i in range(n) if valid_mask[i] and results[i]['hurdle_prob'] >= 0.9 and i not in league_participants]
        if wildcards:
            print(f"    🃏 [Wildcard] P90 허들 돌파자 {len(wildcards)}명 리그 추가 합류!")
            league_participants.extend(wildcards)

        # [Phase 3] 결승 리그전 (Elite League Round-Robin)
        if len(league_participants) > 1:
            match_count = 0
            for res in results: res['league_wins'] = 0
            
            for i in range(len(league_participants)):
                for j in range(i + 1, len(league_participants)):
                    idx1, idx2 = league_participants[i], league_participants[j]
                    match_count += 1
                    
                    vec1, vec2 = X[idx1], X[idx2]
                    pair_input = np.hstack([vec1, vec2]).reshape(1, -1)
                    win_prob = self.tour_model.predict_proba(pair_input)[0, 1]
                    
                    if win_prob > 0.5:
                        results[idx1]['league_wins'] += 1
                    else:
                        results[idx2]['league_wins'] += 1
            print(f"    ⚔️  [Elite League] {len(league_participants)}인 리그전 완료 (총 {match_count}경기)")

        # 최종 가중치 합산 및 정렬 (리그 승수 우선)
        for res in results:
            res['total_score'] = (res.get('league_wins', 0) * 1000) + reg_scores[res['index']]

        return sorted(results, key=lambda x: x['total_score'], reverse=True)

if __name__ == "__main__":
    # 간단 테스트
    scorer = CopyScorerV4()
    dummy_vecs = np.random.randn(10, 3072)
    res = scorer.score_candidates(dummy_vecs)
    print(f"Top 1 score: {res[0]['total_score']:.2f} (Hurdle: {res[0]['pass_hurdle']})")
