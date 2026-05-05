# copy_generator_v2.py: MAB 전략과 과거 대박 게시물의 길이/톤을 벤치마킹하여 새 카피 프롬프트를 생성하는 모듈.
class DynamicCopyGenerator:
    def __init__(self, top_examples=None, prompt_version="upgrade_v10"):
        """
        top_examples: list of dicts {'본문': text, 'MSS': score}
        """
        self.top_examples = top_examples or []
        self.prompt_version = prompt_version

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
                        dynamic_context=None, force_len=None, force_lines=None,
                        sibling_count=3):
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

        if self.prompt_version == "upgrade_v11":
            prompt = f"""당신은 상품을 파는 마케터가 아닙니다.
내부 역할은 Threads 카피 변형 편집자이고, 표면 화자는 너무 좋거나 웃기거나 이상하거나 화나는 장면을 혼자 알기 아까워 공유하는 실제 SNS 유저입니다.

[상품/미디어 맥락]
{product_context}
{original_context}
{variation_context}

[참고 전략]
{context_block}

[고성과 예시 - 소재 복사 금지, 말투와 리듬만 참고]
{top_examples_str}

[작성 방향]
- 원본이 강한 이유를 먼저 잡으세요: 감정, 오해, 반전, 짧은 분노, 소장 욕구, 정체 궁금증 중 무엇인지.
- 그 이유를 설명하지 말고, 현재 상품/미디어의 구체 단서 2개 안에 녹여 장면으로 보여주세요.
- 첫 문장은 원본보다 더 빠르게 멈춰 세워야 합니다.
- 광고주, 판매자, 마케터처럼 말하지 마세요. 친구에게 툭 던지는 발견담처럼 쓰세요.
- 댓글을 달라고 말하지 마세요. 대신 독자가 정정, 공감, 반박, 자기 경험을 말하고 싶어지는 작은 미해결 판단을 남기세요.
- 금지어: 댓글, 알려줘, 공유 좀, 있는 사람, 손 들어, 아는 사람, 나만 그래.
- 질문을 쓰더라도 부탁형 질문이 아니라 혼잣말, 판단 흔들림, 덜 끝난 상황처럼 보여야 합니다.
- 없는 가격, 장기 사용 후기, 유명인 착용, 의학/미용 효과, 과한 광고 말투를 만들지 마세요.
- 각 카피는 공백 포함 {target_min_len}~{target_max_len}자, {target_min_lines}~{target_max_lines}줄 안에 압축하세요.
- 마크다운, 영어 분석문, Explanation, 반복 문자열, 같은 글자/감탄사 반복, 목록식 카피는 금지입니다.

[세 카피 역할]
FINAL_COPY_1: 원본의 훅을 더 짧고 강하게 변형
FINAL_COPY_2: 상품/미디어 단서를 더 촘촘히 넣은 장면형
FINAL_COPY_3: 직접 CTA 없이 말하고 싶게 만드는 미완성 판단형

[출력 형식]
[IMPROVEMENT]
이번 카피에서 강화한 방향 1문장

[FINAL_COPY_1]
(카피 1)

[FINAL_COPY_2]
(카피 2)

[FINAL_COPY_3]
(카피 3)
"""
            return prompt

        if self.prompt_version == "upgrade_v10":
            prompt = f"""당신은 Threads에서 사람들이 자연스럽게 멈춰 읽는 생활형 마케터이자 편집자입니다.

[상품/미디어 맥락]
{product_context}
{original_context}
{variation_context}

[참고 전략]
{context_block}

[고성과 예시 - 소재 복사 금지, 말투와 리듬만 참고]
{top_examples_str}

[작성 방향]
- 원본이 강한 이유를 먼저 잡으세요: 감정, 오해, 반전, 짧은 분노, 소장 욕구, 정체 궁금증 중 무엇인지.
- 그 이유를 그대로 설명하지 말고, 현재 상품/미디어의 구체 단서 2개 안에 녹여 더 선명한 장면으로 바꾸세요.
- 첫 문장은 원본보다 더 빠르게 멈춰 세워야 합니다.
- 댓글을 달라고 말하지 마세요. 대신 독자가 정정, 공감, 반박, 자기 경험을 말하고 싶어지는 작은 미해결 판단을 남기세요.
- 금지어: 댓글, 알려줘, 공유 좀, 있는 사람, 손 들어, 아는 사람, 나만 그래.
- 질문을 쓰더라도 부탁형 질문이 아니라 혼잣말, 판단 흔들림, 덜 끝난 상황처럼 보여야 합니다.
- 없는 가격, 장기 사용 후기, 유명인 착용, 의학/미용 효과, 과한 광고 말투를 만들지 마세요.
- 마크다운, 영어 분석문, Explanation, 반복 문자열, 목록식 카피는 금지입니다.

[세 카피 역할]
FINAL_COPY_1: 원본의 훅을 더 짧고 강하게 변형
FINAL_COPY_2: 상품/미디어 단서를 더 촘촘히 넣은 장면형
FINAL_COPY_3: 직접 CTA 없이 말하고 싶게 만드는 미완성 판단형

[출력 형식]
[IMPROVEMENT]
이번 카피에서 강화한 방향 1문장

[FINAL_COPY_1]
(카피 1)

[FINAL_COPY_2]
(카피 2)

[FINAL_COPY_3]
(카피 3)
"""
            return prompt

        if self.prompt_version in {
            "upgrade_v4",
            "upgrade_v5",
            "upgrade_v6",
            "upgrade_v7",
            "upgrade_v8",
            "upgrade_v9",
        }:
            variant_rules = {
                "upgrade_v4": """
[v4: 원본 훅 복제 후 강화]
- 원본 카피의 감정 구조를 먼저 잡고, 같은 감정을 더 구체적인 현재 상품 단서로 밀어붙이세요.
- 원본보다 첫 문장이 더 선명해야 합니다. 원본이 짧으면 더 짧거나 비슷하게 가세요.
- 각 카피는 원본의 약점을 하나 보완해야 합니다: 구체 단서, 반전, 댓글 유도 중 하나.
""",
                "upgrade_v5": """
[v5: 원본을 직접 이기는 3종 변이]
- FINAL_COPY_1은 원본 훅을 거의 같은 속도로 더 세게 바꿉니다.
- FINAL_COPY_2는 원본에 없던 미디어 단서를 한 줄 추가합니다.
- FINAL_COPY_3은 댓글이 달릴 질문형으로 끝냅니다.
- 세 카피 모두 원본보다 설명이 길면 실패입니다.
""",
                "upgrade_v6": """
[v6: 짧은 고자극/감정 배출]
- 첫 줄은 20자 안팎의 강한 감정으로 시작하세요.
- 웃김, 분노, 억울함, 오해, 정보욕 중 하나가 즉시 보여야 합니다.
- 기능 설명보다 '사람이 왜 멈췄는지'를 먼저 쓰세요.
- 과한 효과 조작은 금지하지만 감정 표현은 과감하게 씁니다.
""",
                "upgrade_v7": """
[v7: 댓글 유도형 원본 압살]
- 각 카피는 댓글을 부르는 질문 또는 정체 추리로 끝냅니다.
- 정답을 너무 빨리 다 말하지 말고, 마지막에 한 번 더 묻게 만드세요.
- "아는 사람?", "나만 몰랐어?", "이거 맞아?" 같은 Threads식 질문을 자연스럽게 사용하세요.
""",
                "upgrade_v8": """
[v8: 상품 단서 고밀도]
- 현재 미디어에서 보이는 명사/형용사를 최소 3개 넣으세요.
- 다만 쇼핑몰 설명문처럼 나열하지 말고, 오해 장면 안에 숨겨 넣으세요.
- 세 카피 모두 서로 다른 구체 단서를 써야 합니다.
- 원본이 강한 URL에서도 후보 여러 개가 원본보다 위로 올라가도록 평균 하한선을 높이세요.
""",
                "upgrade_v9": """
[v9: v2 original-push + v8 top5 hybrid]
- First copy the original's winning mechanism: emotion, curiosity, reversal, or question shape.
- Then make the first sentence sharper than the original and add 2-3 concrete media/product cues inside a natural scene.
- FINAL_COPY_1 should be closest to the original hook, but with a stronger first sentence.
- FINAL_COPY_2 should use denser visible product cues without becoming an explanation.
- FINAL_COPY_3 should end with a comment-triggering question, but it must still include product/media cues.
- Hard ban: markdown marks, meta explanation, "Explanation:", repeated filler characters, English analysis text, bullet-like output inside FINAL_COPY.
- If the original is already very strong, do not avoid it. Attack the same angle more specifically.
""",
            }[self.prompt_version]
            prompt = f"""당신은 Threads에서 원본 카피를 이기는 변이 카피를 만드는 실험가입니다.

[현재 생성 버전]
{self.prompt_version}

[평가 목표]
이 실험의 1차 목표는 top50 분포가 아니라, 현재 원본 카피의 최종 순위를 최대한 아래로 밀어내는 것입니다.
특히 원본이 1등인 케이스에서도 AI 후보가 1등을 빼앗아야 합니다.

[현재 상품/미디어 맥락]
{product_context}
{original_context}
{variation_context}

[이번 전략]
{context_block}

[고성과 예시 - 소재 복사 금지, 리듬만 참고]
{top_examples_str}

{variant_rules}

[공통 규칙]
1. 출력은 반드시 자연스러운 한국어 Threads 글이어야 합니다.
2. 원본보다 약하면 실패입니다. 원본의 감정, 궁금증, 반전 중 최소 하나는 더 강해야 합니다.
3. 첫 문장에 힘을 몰아주세요. 첫 문장이 무난하면 전체가 실패합니다.
4. 현재 상품/미디어에서 확인 가능한 단서를 최소 1개 이상 넣으세요.
5. 없는 가격, 없는 장기 사용 후기, 없는 셀럽 착용, 없는 의학/미용 효과를 만들지 마세요.
6. 예시의 소재를 현재 상품에 옮기지 마세요.
7. 설명문/리뷰문/광고문처럼 보이면 다시 쓰세요.
8. 세 후보는 서로 다른 첫 문장과 장면을 가져야 합니다.
9. 가능하면 {target_min_lines}~{target_max_lines}줄 안에 압축하세요.

[출력 형식]
[IMPROVEMENT]
이번 버전이 원본을 이기기 위해 강화한 방향 1문장

[FINAL_COPY_1]
(카피 1)

[FINAL_COPY_2]
(카피 2)

[FINAL_COPY_3]
(카피 3)
"""
            return prompt

        if self.prompt_version == "upgrade_v3":
            prompt = f"""당신은 Threads에서 성과가 높은 짧은 카피를 쓰는 사람입니다.

[현재 생성 버전]
upgrade_v3

[현재 판매할 상품/미디어 맥락]
{product_context}
{original_context}
{variation_context}

[이번 카피에 적용할 전략]
{context_block}

[고성과 예시 - 소재 복사 금지, 말투/압축감만 참고]
{top_examples_str}

---
[upgrade_v3 핵심]
길게 설명하지 마세요. legacy처럼 짧고 바로 읽히되, 현재 상품의 구체 단서를 더 정확히 넣으세요.
좋은 카피는 "어? 이게 뭐야" → "정체/단서" → "나도 묻게 됨" 흐름이 2~4줄 안에 끝납니다.

[각 FINAL_COPY 규칙]
1. 공백 포함 55~125자, 2~4줄. 길어지면 실패입니다.
2. 첫 줄은 장면/오해/질문으로 시작합니다. 상품 설명으로 시작하지 마세요.
3. 현재 상품/미디어의 핵심 단어 2개 이상을 넣으세요.
   예: 로고, 색, 질감, 스트랩, 양말, 컵, 뚜껑, 붉은 액체, 갈색 통나무처럼 실제 맥락에 있는 단어
4. 원본 또는 상품 맥락에 없는 배경을 만들지 마세요.
   예: 나무 바닥, 한 달 사용, 재고, 품절, 셀럽, 가격, 피부과 직원, 남편/친구 등은 맥락에 없으면 금지
5. 예시 게시물의 조개/카페/연예인/브랜드/상황을 현재 상품에 옮기지 마세요.
6. "추천함/좋음/가성비" 설명문보다, 남들이 물어보는 장면을 우선하세요.
7. 세 카피는 같은 첫 줄을 반복하지 말고, 각각 다른 오해/질문/반응을 씁니다.

[좋은 압축 패턴]
- "친구가 OO인 줄 알고 물어봄;; / 알고 보니 OO였음 / OO 단서 때문에 계속 보게 됨"
- "이거 OO 맞아? / OO랑 OO가 같이 있어서 당황함 / 이 조합 아는 사람?"
- "처음엔 OO인 줄 알았는데 / OO 보고 바로 납득함 / 나만 이제 알았냐"

[출력 형식]
[IMPROVEMENT]
이번 버전에서 강화한 방향 1문장

[FINAL_COPY_1]
(짧은 카피 1)

[FINAL_COPY_2]
(짧은 카피 2)

[FINAL_COPY_3]
(짧은 카피 3)
"""
            return prompt

        if self.prompt_version == "upgrade_v2":
            prompt = f"""당신은 Threads에서 댓글/클릭을 부르는 고성과 카피라이터입니다.

[현재 생성 버전]
upgrade_v2

[현재 판매할 상품/미디어 맥락]
{product_context}
{original_context}
{variation_context}

[이번 카피에 적용할 전략]
{context_block}

[고성과 예시 - 소재 복사 금지, 리듬만 참고]
{top_examples_str}

---
[upgrade_v2 목표]
1~2개만 튀는 카피가 아니라, 생성되는 형제 카피 3개 모두가 top50 안에 들어갈 수준의 하한선을 가져야 합니다.
각 카피는 "상황-오해/충돌-구체 단서-댓글 유도"가 한 번에 보이는 짧은 Threads 글이어야 합니다.

[각 FINAL_COPY 필수 체크리스트]
1. 첫 문장은 상품명 설명이 아니라 사람이 멈칫하는 장면/오해/질문/고백으로 시작
2. 현재 상품/미디어에서 확인 가능한 구체 단서 1개 이상 포함
   - 색, 모양, 질감, 사용 장면, 눈에 띄는 부품, 포장, 전후 상황 중 하나
3. 왜 사람들이 댓글을 달거나 저장할지 한 문장 안에 이유가 보여야 함
4. 예시 게시물의 조개/카페/연예인/브랜드/생활소재를 현재 맥락과 무관하게 가져오면 실패
5. 없는 효능, 없는 가격, 없는 후기, 없는 셀럽 착용, 과한 의학/미용 효과를 만들지 말 것
6. "이거 좋음/추천/가성비"처럼 리뷰체로 끝나면 실패
7. 세 카피는 첫 문장, 상황, 감정 트리거가 서로 달라야 함
8. 공백 포함 {target_min_len}~{target_max_len}자, {target_min_lines}~{target_max_lines}줄

[좋은 출력의 형태]
- 읽는 사람이 "저게 뭔데?"라고 묻게 만드는 첫 줄
- 원본보다 더 구체적인 현재 물건의 단서
- 설명보다 장면이 먼저 오는 문장
- 마지막은 자연스러운 질문/박제/고백으로 끝나도 좋음

[나쁜 출력의 형태]
- 상품명을 길게 풀어쓰는 쇼핑몰 설명문
- 예시 소재를 현재 상품에 덮어씌운 글
- 세 카피가 같은 문장 구조를 반복하는 글
- 한 후보만 강하고 나머지 두 후보가 무난한 글

[출력 전 자체 검수]
각 FINAL_COPY를 쓰기 전에 마음속으로 아래를 확인하세요.
- 첫 15자가 멈칫하게 만드는가?
- 현재 상품/미디어 단서가 실제로 들어갔는가?
- 같은 프롬프트에서 나온 다른 형제 카피와 첫 장면이 겹치지 않는가?
- 설명문처럼 보이면 장면형으로 다시 썼는가?

[출력 형식]
[IMPROVEMENT]
이번 버전에서 강화한 방향 1문장

[FINAL_COPY_1]
(카피 1)

[FINAL_COPY_2]
(카피 2)

[FINAL_COPY_3]
(카피 3)
"""
            return prompt

        if self.prompt_version == "upgrade_v1":
            prompt = f"""당신은 Threads 카피를 실험하는 고성과 카피라이터입니다.

[현재 후보 생성 버전]
upgrade_v1

[현재 판매할 상품/미디어 맥락]
{product_context}
{original_context}
{variation_context}

[이번 카피의 전략]
{context_block}

[고성과 예시 - 구조만 참고]
{top_examples_str}

---
[upgrade_v1 목표]
기존 카피보다 더 강한 첫 문장과 더 선명한 상황극으로, 댓글/클릭을 부르는 카피를 만드세요.
단, 고성과 예시의 상품/상황/소재를 현재 상품에 섞으면 실패입니다.

[반드시 지킬 것]
1. 첫 문장은 1초 안에 궁금증이 생기는 장면, 오해, 고백, 질문 중 하나로 시작
2. 카피 안에 현재 상품/미디어에서 확인되는 구체 단서 1개 이상 포함
3. 고성과 예시의 소재를 복사하지 말 것
4. 설명문처럼 쓰지 말고, 누가 실제로 겪은 짧은 Threads 글처럼 쓸 것
5. 제품명 전체를 길게 늘어놓지 말고, 사람들이 묻게 될 별명/정체/상황으로 말할 것
6. 없는 셀럽, 없는 후기, 없는 효능, 없는 가격은 만들지 말 것
7. 서로 다른 형제 카피 3개를 만들되, 첫 문장/상황/오해 포인트가 겹치면 안 됨
8. 공백 포함 {target_min_len}~{target_max_len}자, {target_min_lines}~{target_max_lines}줄
9. 1/2 같은 페이지 번호, 해설 제목, 분석 문구, 영어 안내문 출력 금지

[좋은 방향]
- 원본보다 더 구체적인 장면
- 원본보다 더 강한 궁금증
- 원본보다 덜 설명적인 문장
- 상품 맥락을 놓치지 않는 과장

[나쁜 방향]
- 예시의 조개/해감/카페/연예인/브랜드 소재를 현재 상품과 무관하게 끌고 오는 것
- 상품 설명서처럼 기능을 나열하는 것
- 너무 긴 첫 문장
- 같은 문장 구조를 3개 반복하는 것

[출력 형식]
[IMPROVEMENT]
이번 버전에서 강화한 방향 1문장

[FINAL_COPY_1]
(카피 1)

[FINAL_COPY_2]
(카피 2)

[FINAL_COPY_3]
(카피 3)
"""
            return prompt

        # ### [PROMPT_LOCATION: COPY_GENERATION] ###
        prompt = f"""당신은 스레드(Threads)에서 클릭을 부르는 '궁금증 유발'의 달인입니다.

[🚨 현재 판매할 상품 정보 (MUST USE THIS CONTEXT)]
{product_context}
{original_context}

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
2. STEP 2 (분석): 작성된 초안이 '현재 상품(일본 파인애플 소화 사탕)'의 맥락을 100% 반영했는지, 예시 게시물의 소재(네임펜, 카페 등)가 섞이진 않았는지 냉정하게 검증하세요.
3. STEP 3 (최종안): 오직 '현재 상품'의 소구점만 사용하여 고성과 리듬으로 재작성하세요. (예시의 상품명은 절대 언급 금지)

---
[형식 엄수]
[IMPROVEMENT]
(분석/개선 방향 1~2문장)

[FINAL_COPY_1]
(같은 개선 방향을 반영한 형제 카피 1)

[FINAL_COPY_2]
(같은 개선 방향을 반영한 형제 카피 2)

[FINAL_COPY_3]
(같은 개선 방향을 반영한 형제 카피 3)
---

[🚨 철칙 (Rule Priority: 1-8)]
1. 각 카피는 공백 포함 {target_min_len}~{target_max_len}자, {target_min_lines}~{target_max_lines}줄 (반드시 줄바꿈 포함)
2. 1/2 등 불필요한 페이지 번호나 순서 표기 절대 금지
3. 어미: ~함, ~임, ~됨, ;;, ㅋㅋ (친구에게 말하듯 자연스럽게)
4. 예시 게시물은 오직 '문장 전개 구도'와 '심리적 트리거'만 참고할 것. (⚠️ 절대 금기: 예시의 소재를 그대로 쓰면 즉시 탈락. 무조건 현재 상품 정보를 기반으로 처음부터 끝까지 새로 쓰세요.)
5. 궁금증 유발에 몰빵. 제품의 이름이나 기능을 구구절절 설명하는 '설명충' 모드 절대 금지
6. 연예인/유명인 이름이 맥락에 있으면 카피 최상단에 노출하여 후광 효과 극대화
7. 없는 사실을 지어내는 환각은 금지하되, 사용자의 반응이나 효과에 대한 표현은 매우 극적으로 묘사할 것
8. [FINAL_COPY_1]~[FINAL_COPY_{sibling_count}]는 동일한 개선 방향을 공유하되, 첫 문장과 훅은 서로 다르게 설계할 것
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
