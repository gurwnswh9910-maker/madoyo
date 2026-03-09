class CopyGenerator:
    def __init__(self):
        self.templates = {
            'Authority': {
                'description': '연예인/직업 권위를 첫 단어에 배치해 신뢰 확보',
                'format': '[권위/직업] [3초 내 반전컷/후킹] [임팩트 스토리]'
            },
            'Reaction': {
                'description': '제3자 리액션/증언(친구·PD·직군 사례)로 실제 후기 제시',
                'format': '[제3자 반응/사건] [내돈내산 톤] [전후 비교]'
            },
            'Sharing': {
                'description': '방법·레시피 등 저장/공유 유도형 활용',
                'format': '[핵심 정보/방법] [질문형 댓글 유도] [저장 권유]'
            },
            'Emotion': {
                'description': '문제 해결 및 감정 과잉 반응(미쳤다, 인생바뀜) 활용',
                'format': '[문제 제시] [간단한 해결] [감정 표현/행동 변화]'
            }
        }

    def generate_prompt(self, arm, product_info):
        template = self.templates.get(arm)
        if not template:
            return "General marketing copy prompt..."
        
        prompt = f"""
        당신은 실력이 뛰어난 퍼포먼스 마케터입니다.
        다음 정보를 바탕으로 스레드(Threads)에 최적화된 짧고 강력한 카피를 작성하세요.
        
        [제품/서비스 정보]
        {product_info}
        
        [적용 전략: {arm}]
        - 설명: {template['description']}
        - 구조: {template['format']}
        
        [작성 원칙]
        1. 광고 냄새를 제거하세요. (판매 지시 금지, 가격 언급 지양)
        2. 첫 줄 후킹에 모든 것을 거세요.
        3. 과장된 감정 반응을 적절히 섞으세요. (예: 미쳤다, 당황함, 인생바뀜)
        4. 정보 공유(도움이 되는 정보)처럼 느껴지게 하세요.
        5. 말 끝은 문어체보다 구어체(;;, ㅋㅋ, ~함)를 섞어 생동감 있게 하세요.
        """
        return prompt

# Example Usage
if __name__ == "__main__":
    generator = CopyGenerator()
    product = "하루 만에 붓기 빼주는 팥 호박즙"
    
    # 밴딧이 'Emotion' 전략을 선택했다고 가정
    selected_arm = 'Emotion'
    prompt = generator.generate_prompt(selected_arm, product)
    print(f"Generated Prompt for {selected_arm}:\n{prompt}")
