# contrastive_prompter.py: 대조 Few-Shot 프롬프트 생성기
# 정적 HIGH/LOW 페어로 패턴을 가르치고, 동적으로 입력과 유사한 성공 사례를 검색
import numpy as np
import os

class ContrastivePrompter:
    """
    대조 Few-Shot 프롬프트 생성기.
    
    - 정적 컨텍스트: cosine 0.9+ HIGH/LOW 페어 3쌍 (패턴 학습용)
    - 동적 컨텍스트: 입력 카피와 유사한 HIGH-MSS 성공 사례 (제품별 적용)
    """
    
    # 정적 대조 페어 (cosine 0.9+ / MSS 비율 5x+)
    # 데이터 분석에서 추출한 "거의 같은 글인데 성과가 극단적으로 다른" 쌍
    STATIC_PAIRS = [
        {
            'high': 'NARS 진짜 여자들 마음 너무 잘 알아😍\n건조한 입술이랑 쩍하면 각질… 이게 진짜 고민이었는데\n이 립밤 하나로 싹 정리됐어;;',
            'high_mss': 6009,
            'low': '아니 진짜…\nNARS 진짜 여자들 마음 너무 잘 알아😍',
            'low_mss': 56,
            'cosine': 0.990,
        },
        {
            'high': '이 조합 추천해준 쓰친이 새해 복 다섯번 받자🙏',
            'high_mss': 1875,
            'low': '이 조합 추천해준 쓰친이 자기전에 생각난다;;🙇\u200d♂️',
            'low_mss': 13,
            'cosine': 0.969,
        },
        {
            'high': 'UGG 신고 외출했는데,길에서 만난 아기 고양이가 갑자기 살짝 톡 밟고 가는거야 🐱',
            'high_mss': 5880,
            'low': '어그 첫 개시날부터 길냥이한테 축복받음…🐾',
            'low_mss': 28,
            'cosine': 0.908,
        },
    ]
    
    def __init__(self, embedding_manager=None, all_data=None):
        """
        embedding_manager: EmbeddingManager 인스턴스 (동적 검색용)
        all_data: DataFrame with '본문' and 'MSS' columns (동적 검색용)
        """
        self.emb_mgr = embedding_manager
        self.all_data = all_data
    
    def _build_static_context(self):
        """정적 대조 페어를 프롬프트 문자열로 변환"""
        lines = ["[대조 학습 예시 — 비슷한 글인데 성과가 극단적으로 다른 쌍]"]
        lines.append("아래 LOW→HIGH 차이를 분석하고, HIGH의 패턴을 파악하세요.\n")
        
        for i, pair in enumerate(self.STATIC_PAIRS, 1):
            h_preview = pair['high'].replace('\n', ' / ')
            l_preview = pair['low'].replace('\n', ' / ')
            lines.append(f"❌ LOW (MSS {pair['low_mss']}): {l_preview}")
            lines.append(f"✅ HIGH (MSS {pair['high_mss']}): {h_preview}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _find_dynamic_example(self, input_copy, top_n=1):
        """입력 카피와 유사한 HIGH-MSS 성공 사례를 검색"""
        if self.emb_mgr is None or self.all_data is None:
            return ""
        
        # 입력 카피의 임베딩
        input_emb = self.emb_mgr.get_embedding(input_copy)
        if input_emb is None:
            return ""
        
        input_vec = np.array(input_emb)
        
        # MSS 상위 게시물 중에서 가장 유사한 것 검색
        high_mss_threshold = 500  # MSS 500 이상인 것만 후보
        candidates = []
        
        for _, row in self.all_data.iterrows():
            text = str(row.get('본문', '')).strip()
            mss = float(row.get('MSS', 0))
            
            if mss < high_mss_threshold or text == input_copy:
                continue
            if text not in self.emb_mgr.embeddings:
                continue
            
            vec = np.array(self.emb_mgr.embeddings[text])
            sim = np.dot(input_vec, vec) / (np.linalg.norm(input_vec) * np.linalg.norm(vec) + 1e-10)
            candidates.append((text, mss, sim))
        
        if not candidates:
            return ""
        
        # 유사도 상위 선택
        candidates.sort(key=lambda x: x[2], reverse=True)
        best = candidates[:top_n]
        
        lines = ["\n[당신의 카피와 비슷한 성공 사례]"]
        for text, mss, sim in best:
            preview = text.replace('\n', ' / ')[:100]
            lines.append(f"✅ (MSS {mss:.0f}) {preview}")
        
        return "\n".join(lines)

    def _find_dynamic_contrastive_pair(self, high_post_text, high_mss):
        """고성과 게시물과 유사도가 가장 높으면서 성과가 낮은(고성과의 70% 이하) 게시물 검색"""
        if self.emb_mgr is None or self.all_data is None or high_post_text is None:
            return None, None

        input_emb = self.emb_mgr.get_embedding(high_post_text)
        if input_emb is None:
            return None, None

        input_vec = np.array(input_emb)
        
        # 1. 텍스트 임베딩으로 전체 데이터와 코사인 유사도 계산
        candidates = []
        low_mss_threshold = high_mss * 0.7
        
        for _, row in self.all_data.iterrows():
            text = str(row.get('본문', '')).strip()
            mss = float(row.get('MSS', 0))
            
            # 본인 제외, 그리고 70% 이하인 것들만 후보로 (유사도 기준 서치 후 필터)
            if text == high_post_text or mss > low_mss_threshold:
                continue
            if text not in self.emb_mgr.embeddings:
                continue
            
            vec = np.array(self.emb_mgr.embeddings[text])
            sim = np.dot(input_vec, vec) / (np.linalg.norm(input_vec) * np.linalg.norm(vec) + 1e-10)
            candidates.append((text, mss, sim))
            
        if not candidates:
            return None, None
            
        # 2. 유사도(sim) 기준으로 내림차순 정렬하여 가장 비슷한 것 1개 선택
        candidates.sort(key=lambda x: x[2], reverse=True)
        best_low_text, best_low_mss, best_sim = candidates[0]
        
        # 유사도가 너무 낮으면 페어로 제시하지 않음
        if best_sim < 0.6:
            return None, None

        return best_low_text, best_low_mss
    
    def build_contrastive_context(self, input_copy=None, high_post_text=None, high_mss=None):
        """
        대조 프롬프트 컨텍스트 전체를 생성 (동적 페어 정보 포함 반환).
        
        Returns:
            tuple: (프롬프트 텍스트, low_post_text, low_mss)
        """
        parts = [self._build_static_context()]
        best_low_text, best_low_mss = None, None
        
        if input_copy:
            dynamic = self._find_dynamic_example(input_copy)
            if dynamic:
                parts.append(dynamic)
                
        if high_post_text and high_mss:
            best_low_text, best_low_mss = self._find_dynamic_contrastive_pair(high_post_text, high_mss)
            if best_low_text:
                lines = ["\n[동적 대조 학습 예시 — 현재 모델이 발견한 텍스트 유사도 기반 쌍]"]
                lines.append("아래 LOW→HIGH 차이를 분석하고, HIGH의 패턴을 파악하세요.\n")
                h_preview = high_post_text.replace('\n', ' / ')
                l_preview = best_low_text.replace('\n', ' / ')
                lines.append(f"❌ LOW (MSS {best_low_mss:.0f}): {l_preview}")
                lines.append(f"✅ HIGH (MSS {high_mss:.0f}): {h_preview}")
                parts.append("\n".join(lines))
        
        return "\n".join(parts), best_low_text, best_low_mss


if __name__ == "__main__":
    # 테스트
    prompter = ContrastivePrompter()
    ctx = prompter.build_contrastive_context()
    print(ctx)
