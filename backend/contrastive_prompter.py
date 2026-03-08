import numpy as np
import os
from sqlalchemy.orm import Session
from api.database import SessionLocal, MABEmbedding
from sqlalchemy import text as sql_text

class ContrastivePrompter:
    """
    대조 Few-Shot 프롬프트 생성기 (DB Native Version).
    """
    
    # 정적 대조 페어 (패턴 학습용 핵심 데이터)
    STATIC_PAIRS = [
        {
            'high': 'NARS 진짜 여자들 마음 너무 잘 알아😍\n건조한 입술이랑 쩍하면 각질… 이게 진짜 고민이었는데\n이 립밤 하나로 싹 정리됐어;;',
            'high_mss': 6009,
            'low': '아니 진짜…\nNARS 진짜 여자들 마음 너무 잘 알아😍',
            'low_mss': 56,
        },
        {
            'high': '이 조합 추천해준 쓰친이 새해 복 다섯번 받자🙏',
            'high_mss': 1875,
            'low': '이 조합 추천해준 쓰친이 자기전에 생각난다;;🙇\u200d♂️',
            'low_mss': 13,
        },
        {
            'high': 'UGG 신고 외출했는데,길에서 만난 아기 고양이가 갑자기 살짝 톡 밟고 가는거야 🐱',
            'high_mss': 5880,
            'low': '어그 첫 개시날부터 길냥이한테 축복받음…🐾',
            'low_mss': 28,
        },
    ]
    
    def __init__(self, embedding_manager=None):
        self.emb_mgr = embedding_manager
    
    def _build_static_context(self):
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
        """입력 카피와 유사한 HIGH-MSS 성공 사례를 DB에서 검색"""
        if self.emb_mgr is None: return ""
        
        # search_weighted를 활용하여 관련성 높은 고성과 사례 추출
        matches = self.emb_mgr.search_weighted(input_copy, limit=top_n)
        
        if not matches:
            return ""
        
        lines = ["\n[당신의 카피와 비슷한 성공 사례]"]
        for m in matches:
            preview = m['text'].replace('\n', ' / ')[:100]
            lines.append(f"✅ (MSS {m['mss']:.0f}) {preview}")
        
        return "\n".join(lines)

    def _find_dynamic_contrastive_pair(self, high_post_text, high_mss):
        """고성과 게시물과 유사도가 가장 높으면서 성과가 낮은 게시물을 DB에서 검색"""
        if self.emb_mgr is None or high_post_text is None:
            return None, None

        input_emb = self.emb_mgr.get_embedding(high_post_text)
        if input_emb is None:
            return None, None

        vec_str = "[" + ",".join(map(str, input_emb)) + "]"
        low_mss_threshold = high_mss * 0.7
        
        db: Session = SessionLocal()
        try:
            # SQL: 유사도 순으로 정렬하되 MSS가 일정 수준 이하인 것 1개 검색
            query = sql_text("""
                SELECT content_text, mss_score, (1 - (embedding <=> :vec)) as sim
                FROM mab_embeddings
                WHERE mss_score <= :mss_limit AND content_text != :orig
                ORDER BY (embedding <=> :vec) ASC
                LIMIT 1
            """)
            result = db.execute(query, {"vec": vec_str, "mss_limit": low_mss_threshold, "orig": high_post_text}).first()
            
            if result and result.sim > 0.6:
                return result.content_text, result.mss_score
            return None, None
            
        except Exception as e:
            print(f"Error finding contrastive pair: {e}")
            return None, None
        finally:
            db.close()
    
    def build_contrastive_context(self, input_copy=None, high_post_text=None, high_mss=None):
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
    from embedding_utils import EmbeddingManager
    prompter = ContrastivePrompter(embedding_manager=EmbeddingManager())
    ctx, _, _ = prompter.build_contrastive_context(input_copy="NARS 립밤 추천")
    print(ctx)
