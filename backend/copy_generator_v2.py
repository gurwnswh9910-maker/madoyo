# copy_generator_v2.py: MAB 전략과 과거 대박 게시물의 길이/톤을 벤치마킹하여 새 카피 프롬프트를 생성하는 모듈.
class DynamicCopyGenerator:
    def __init__(self, top_examples=None):
        """
        top_examples: list of dicts {'본문': text, 'MSS': score}
        """
        self.top_examples = top_examples or []

    def _build_top_examples_str(self):
        """top_examples에서 프롬프트용 고성과 게시물 문자열을 빌드."""
        parts = []
        for i, ex in enumerate(self.top_examples[:5]):
            text = str(ex.get('본문', ''))
            mss = ex.get('MSS', 0)
            parts.append(f"예시 {i+1} (MSS: {mss:.0f}):\n{text}")
        return "\n\n".join(parts)

    def _calculate_length_constraints(self, examples):
        """예시 데이터들의 길이를 분석하여 동적 제약조건 생성."""
        if not examples:
            return 30, 80, 2, 3  # 기본값 (30~80자, 2~3줄)
            
        lengths = [len(str(ex.get('본문', ''))) for ex in examples]
        avg_len = sum(lengths) / len(lengths)
        
        # 여유 범위 설정 (평균의 0.6배 ~ 1.2배) - 더 타이트하게 조정
        min_len = max(20, int(avg_len * 0.6))
        max_len = max(80, int(avg_len * 1.2)) # 최대 80자 내외 권장
        
        # 줄 바꿈 수 분석
        lines = [str(ex.get('본문', '')).count('\n') + 1 for ex in examples]
        avg_lines = sum(lines) / len(lines)
        min_lines = max(2, int(avg_lines - 1))
        max_lines = max(3, int(avg_lines + 1)) # 기본 3줄 내외 권장
        
        return min_len, max_len, min_lines, max_lines
        
    def generate_prompt(self, product_info, strategy_name=None, strategy_desc=None,
                        original_copy=None, variation_idx=None, contrastive_context=None,
                        dynamic_context=None, force_len=None, force_lines=None):
        """
        유연한 프롬프트 생성기.
        """
        top_examples_str = self._build_top_examples_str()
        
        # 동적 길이 제약 계산 (외부 강제값이 없으면 자동 계산)
        a_min_len, a_max_len, a_min_lines, a_max_lines = self._calculate_length_constraints(self.top_examples)
        
        target_min_len = force_len[0] if force_len else a_min_len
        target_max_len = force_len[1] if force_len else a_max_len
        target_min_lines = force_lines[0] if force_lines else a_min_lines
        target_max_lines = force_lines[1] if force_lines else a_max_lines

        # 동적 컨텍스트 (실시간 도출된 인사이트/금기 사항)
        insight_block = ""
        if dynamic_context:
            insight_block = f"\n\n[📢 실시간 분석된 핵심 인사이트]\n{dynamic_context}\n* 주의: 위 내용을 참고하여 실패 사례의 패턴을 피하고, 고성과 게시물의 호흡을 반영하세요."

        # 전략 블록
        strategy_block = ""
        if strategy_name and strategy_desc:
            strategy_block = f"\n[적용한 전략: {strategy_name}]\n{strategy_desc}"
        
        # 병합
        context_block = strategy_block + insight_block

        # 원본 블록
        original_block = ""
        if original_copy:
            original_block = f"\n[원본 카피 (참고 소재)]\n{original_copy}\n* 참고: 원본의 핵심 뉘앙스만 가져오되, 카피 자체는 완전히 새롭게 창조하세요."

        # 변형 지시
        variation_note = ""
        if variation_idx is not None:
            variation_note = f"\n8. 변형 번호 {variation_idx}이므로 이전 버전과 완전히 다른 접근 방식을 택할 것"

        # 제품 정보 블록 (배경 맥락으로 격하)
        if isinstance(product_info, dict):
            obj = product_info.get('objective_description') or product_info.get('objective', '')
            ins = product_info.get('marketing_insight') or product_info.get('insight', '')
            product_context = f"사진/영상: {obj} | 톤 힌트: {ins}"
        else:
            product_context = str(product_info)

        # 원본 카피 컨텍스트
        original_context = f"원본 참고: {original_copy}" if original_copy else ""
        
        # 변형 지시 컨텍스트
        variation_context = f"(변형 #{variation_idx} — 이전과 완전히 다른 접근)" if variation_idx else ""

        prompt = f"""당신은 스레드(Threads)에서 클릭을 부르는 '궁금증 유발'의 달인입니다.

[🎯 적용할 전략]
{context_block}

[고성과 게시물 — 위 전략을 이 리듬과 호흡으로 구현하세요]
{top_examples_str}

---
(아래는 배경 맥락입니다. 카피에 직접 서술하지 마세요. 맥락이 어긋나지 않게만 참고하세요.)
{product_context}
{original_context}
{variation_context}
---

[🚨 철칙]
1. 위 고성과 게시물의 길이·리듬·호흡을 최우선으로 따를 것. 그보다 길면 실패임
2. 궁금증 유발에 몰빵. 제품명/기능을 구구절절 설명하지 말 것
3. 연예인/유명인 이름이 맥락에 있으면 카피 앞부분에 노출하여 후광 효과 극대화
4. 공백 포함 {target_min_len}~{target_max_len}자, {target_min_lines}~{target_max_lines}줄 (반드시 줄바꿈 포함)
5. 어미: ~함, ~임, ~됨, ;;, ㅋㅋ (친구한테 말하듯 자연스럽게)
6. 환각 금지. 무관한 상황을 지어내지 말되 반응/효과는 극적으로
7. 하나의 카피만 출력 (설명·주석·번호 금지). 1/2 등 페이지 번호 절대 포함 금지

카피 텍스트 하나만 출력하세요."""
        return prompt


if __name__ == "__main__":
    examples = [
        {"본문": "일본 가면 이건 꼭 챙겨… 진짜 인생 바뀜;; 비행기 2시간도 못 버티던 내가 이 사탕 하나로 '화장실 SOS' 사라짐;; 🍍🤯", "MSS": 1250.5},
        {"본문": "나 족저근막염 때문에 신발 고를 때 예민한데 살로몬 이 신발은 진짜 편함;; 이젠 가방에 없으면 불안할 정도ㅋㅋ", "MSS": 980.2}
    ]
    generator = DynamicCopyGenerator(examples)
    product = "피부 열감 확 내려주는 수분 쿨링 스틱"
    prompt = generator.generate_prompt(product, strategy_name="개인적 경험 공유형",
                                        strategy_desc="본인이 직접 겪은 불편함을 해결한 사례처럼 서술")
    print(prompt)
