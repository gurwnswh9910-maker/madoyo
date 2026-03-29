import numpy as np
import os
from sqlalchemy.orm import Session
from api.database import SessionLocal, MABEmbedding
from sqlalchemy import text as sql_text

class ContrastivePrompter:
    """[ONLINE VERSION] SQL 기반 실시간 대조 Few-Shot 프롬프트 생성기"""
    
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
        if self.emb_mgr is None: return ""
        query_vec = self.emb_mgr.get_text_embedding(input_copy)
        if query_vec is None: return ""
        matches = self.emb_mgr.get_hybrid_top_k(query_vec, k=top_n)
        if not matches: return ""
        lines = ["\n[당신의 카피와 비슷한 성공 사례]"]
        for m in matches:
            preview = m['content_text'].replace('\n', ' / ')[:100]
            lines.append(f"✅ (MSS {m['mss_score']:.0f}) {preview}")
        return "\n".join(lines)

    def _find_dynamic_contrastive_pair(self, high_post_text, high_mss):
        if self.emb_mgr is None or high_post_text is None: return None, None
        input_emb = self.emb_mgr.get_text_embedding(high_post_text)
        if input_emb is None: return None, None
        low_mss_threshold = high_mss * 0.7
        db: Session = SessionLocal()
        try:
            query = sql_text("""
                SELECT content_text, mss_score, (1 - (embedding <=> CAST(:vec AS vector))) as sim
                FROM mab_embeddings
                WHERE mss_score <= :mss_limit AND content_text != :orig AND embedding_type IN ('text', 'multi')
                ORDER BY (embedding <=> CAST(:vec AS vector)) ASC
                LIMIT 1
            """)
            result = db.execute(query, {"vec": input_emb.tolist(), "mss_limit": low_mss_threshold, "orig": high_post_text}).first()
            if result and result.sim > 0.6: return result.content_text, result.mss_score
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
            if dynamic: parts.append(dynamic)
        if high_post_text and high_mss:
            best_low_text, best_low_mss = self._find_dynamic_contrastive_pair(high_post_text, high_mss)
            if best_low_text:
                lines = ["\n[동적 대조 학습 예시 — 현재 모델이 발견한 텍스트 유사도 기반 쌍]"]
                lines.append("아래 LOW→HIGH 차이를 분석하고, HIGH의 패턴을 파악하세요.\n")
                best_low_preview = best_low_text.replace('\n', ' / ')
                high_preview = high_post_text.replace('\n', ' / ')
                lines.append(f"❌ LOW (MSS {best_low_mss:.0f}): {best_low_preview}")
                lines.append(f"✅ HIGH (MSS {high_mss:.0f}): {high_preview}")
                parts.append("\n".join(lines))
        return "\n".join(parts), best_low_text, best_low_mss
