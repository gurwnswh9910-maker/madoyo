# copy_generator_v2.py: MAB 전략과 과거 대박 게시물의 길이/톤을 벤치마킹하여 새 카피 프롬프트를 생성하는 모듈.
class DynamicCopyGenerator:
    def __init__(self, top_examples=None):
        """
        top_examples: list of dicts {'본문': text, 'MSS': score}
        """
        self.top_examples = top_examples or []

    def _build_top_examples_str(self):
        """top_examples에서 프롬프트용 고성과 게시물 문자열을 빌드하며 구체적인 소재를 익명화."""
        parts = []
        # 고성과 게시물의 소재가 현재 카피에 섞이는 것을 방지하기 위해 일반화(Generalization) 시도
        keywords_to_scrub = ["네임펜", "샤넬", "까르띠에", "인쇄소", "어린이집", "유리컵", "의류", "공장", "브랜드", "로고", "스티커"]
        for i, ex in enumerate(self.top_examples[:5]):
            text = str(ex.get('본문', ''))
            mss = ex.get('MSS', 0)

            # 구체적 소재를 [대상]으로 치환하여 구조만 남김
            scrubbed_text = text
            for kw in keywords_to_scrub:
                scrubbed_text = scrubbed_text.replace(kw, "[상품/소재]")

            parts.append(f"예시 {i+1} (MSS: {mss:.0f}):\n{scrubbed_text}")
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

        # ### [PROMPT_LOCATION: COPY_GENERATION] ###
        prompt = f"""당신은 스레드(Threads)에서 클릭을 부르는 '궁금증 유발'의 달인입니다.

[🚨 현재 판매할 상품 정보 (MUST USE THIS CONTEXT)]
{product_context}
{original_context}
{variation_context}

[🎯 적용할 마케팅 전략]
{context_block}

[🔥 고성과 게시물 벤치마킹 (구조적 참고용)]
{top_examples_str}
[위 고성과 게시물들의 리듬, 호흡, 문장 구성 및 훅(Hook) 설계 '방식'만 벤치마킹하여 현재 상품에 적용하세요]

---
[💡 필승 공식: 구조는 빌리고, 알맹이는 상품으로 바꾼다]
(예시) 구조: "맘카페 난리길래 광고인 줄... 근데 써보니 대박"
(변환) 상품: 파인애플 사탕
(최종) "맘카페 난리길래 또 일본 광고인 줄 알았거든?? 근데 소화 안 돼서 함 먹어보고 소름 돋음;; 이거 진짜 여행 필수템 맞네ㅋㅋ"

---
[🚨 초정밀 카피 생성 지시]
1. STEP 1 (초안): 현재 상품 정보와 마케팅 전략을 바탕으로, 고성과 리듬을 반영하여 하나의 카피를 작성하세요.
2. STEP 2 (분석): 작성된 초안이 '현재 상품 정보'의 맥락을 100% 반영했는지, 예시 게시물의 소재가 섞이진 않았는지 냉정하게 검증하세요.
3. STEP 3 (최종안): 오직 '현재 상품'의 소구점만 사용하여 고성과 리듬으로 재작성하세요. (예시의 상품명은 절대 언급 금지)

---
[형식 엄수]
[DRAFT_COPY]
(초안)

[IMPROVEMENT]
(분석/개선점)

[FINAL_COPY]
(최종 개선안)
---

[🚨 철칙 (Rule Priority: 1-8)]
1. 각 카피는 공백 포함 {target_min_len}~{target_max_len}자, {target_min_lines}~{target_max_lines}줄 (반드시 줄바꿈 포함)
2. 1/2 등 불필요한 페이지 번호나 순서 표기 절대 금지
3. 어미: ~함, ~임, ~됨, ;;, ㅋㅋ (친구에게 말하듯 자연스럽게)
4. 예시 게시물은 오직 '문장 전개 구도'와 '심리적 트리거'만 참고할 것. (⚠️ 절대 금기: 예시의 소재를 그대로 쓰면 즉시 탈락. 무조건 현재 상품 정보를 기반으로 처음부터 끝까지 새로 쓰세요.)
5. 궁금증 유발에 몰빵. 제품의 이름이나 기능을 구구절절 설명하는 '설명충' 모드 절대 금지
6. 연예인/유명인 이름이 맥락에 있으면 카피 최상단에 노출하여 후광 효과 극대화
7. 없는 사실을 지어내는 환각은 금지하되, 사용자의 반응이나 효과에 대한 표현은 매우 극적으로 묘사할 것
8. [DRAFT_COPY]와 [FINAL_COPY]는 서로 다른 방향의 훅(Hook)을 시도하여 가장 '터질 것 같은' 최종안을 도출할 것
"""
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
