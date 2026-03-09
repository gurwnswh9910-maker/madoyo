import re
import random
import pandas as pd
from typing import List, Dict
from pattern_extractor import MicroscopicPatternExtractor

class LocalTemplateGenerator:
    """
    API 없이 로컬에서 고성과 한국어 게시물의 '구조적 골격'만 추출하고,
    사용자 원본 카피의 키워드를 채워 넣어 후보를 생성하는 엔진.
    
    핵심 원칙: 고성과 게시물의 '내용'은 절대 가져오지 않는다.
    오직 '구조'(줄수, 글자수 비율, 어미, 이모지 위치)만 복제한다.
    """
    def __init__(self, all_data: pd.DataFrame):
        def is_korean(text):
            if not isinstance(text, str): return False
            kor_count = len(re.findall('[가-힣]', text))
            return (kor_count / max(len(text), 1)) > 0.3

        self.data = all_data[all_data['본문'].apply(is_korean)].copy()
        # 중복 제거
        self.data = self.data.drop_duplicates(subset='본문')
        self.extractor = MicroscopicPatternExtractor()
        self.top_posts = self.data.nlargest(10, 'MSS')

    def _extract_structural_skeleton(self, text: str) -> Dict:
        """고성과 게시물에서 '구조적 골격'만 추출 (내용 무시)"""
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        chars_per_line = [len(l) for l in lines]
        
        # 각 줄의 어미 패턴 추출
        endings = []
        for line in lines:
            if line.endswith('ㅋㅋ') or line.endswith('ㅋ'):
                endings.append('ㅋㅋ')
            elif line.endswith(';;'):
                endings.append(';;')
            elif line.endswith('ㅠㅠ') or line.endswith('ㅠ'):
                endings.append('ㅠㅠ')
            elif line.endswith('함') or line.endswith('임') or line.endswith('됨'):
                endings.append(line[-1])
            elif line.endswith('...'):
                endings.append('...')
            else:
                endings.append('')
        
        # 이모지 위치 분석 (어떤 줄에 이모지가 있는지)
        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF\U00002700-\U000027BF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]')
        emoji_positions = []
        for i, line in enumerate(lines):
            emojis = emoji_pattern.findall(line)
            if emojis:
                emoji_positions.append({'line_idx': i, 'count': len(emojis)})
        
        return {
            'line_count': len(lines),
            'chars_per_line': chars_per_line,
            'char_ratios': [c / max(sum(chars_per_line), 1) for c in chars_per_line],
            'endings': endings,
            'emoji_positions': emoji_positions,
            'total_chars': sum(chars_per_line)
        }

    def _split_original_into_segments(self, original_copy: str) -> Dict:
        """원본 카피를 의미 단위로 분해"""
        lines = [l.strip() for l in original_copy.split('\n') if l.strip()]
        
        # 이모지 추출
        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF\U00002700-\U000027BF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]')
        all_emojis = emoji_pattern.findall(original_copy)
        
        # 순수 텍스트만 분리 (이모지 제거)
        clean_text = emoji_pattern.sub('', original_copy).strip()
        words = [w for w in clean_text.split() if w.strip()]
        
        return {
            'lines': lines,
            'words': words,
            'emojis': all_emojis,
            'clean_text': clean_text
        }

    def _assemble_with_skeleton(self, skeleton: Dict, segments: Dict, variation_idx: int) -> str:
        """구조적 골격에 원본 키워드를 채워 넣기"""
        words = segments['words'].copy()
        emojis = segments['emojis'].copy()
        target_lines = skeleton['line_count']
        char_ratios = skeleton['char_ratios']
        endings = skeleton['endings']
        emoji_positions = skeleton['emoji_positions']
        
        # 단어를 골격의 줄 비율에 맞게 분배
        total_words = len(words)
        new_lines = []
        word_idx = 0
        
        for line_idx in range(target_lines):
            if line_idx < len(char_ratios):
                ratio = char_ratios[line_idx]
            else:
                ratio = 1.0 / target_lines
            
            word_count = max(1, round(total_words * ratio))
            line_words = words[word_idx:word_idx + word_count]
            word_idx += word_count
            
            if not line_words and word_idx < total_words:
                line_words = [words[word_idx]]
                word_idx += 1
            
            line_text = ' '.join(line_words) if line_words else ''
            
            # 어미 패턴 적용
            if line_idx < len(endings) and endings[line_idx]:
                # 기존 어미 제거 후 새 어미 연결
                ending = endings[line_idx]
                # 마지막 문자가 이미 같은 어미면 중복 방지
                if not line_text.endswith(ending):
                    line_text = line_text.rstrip('ㅋㅠ;.!? ') + ending
            
            # 이모지 배치
            emoji_here = [ep for ep in emoji_positions if ep['line_idx'] == line_idx]
            if emoji_here and emojis:
                count = min(emoji_here[0]['count'], len(emojis))
                line_text += ''.join(emojis[:count])
                emojis = emojis[count:]
            
            if line_text.strip():
                new_lines.append(line_text.strip())
        
        # 남은 단어 마지막 줄에 추가
        if word_idx < total_words:
            remaining = ' '.join(words[word_idx:])
            if new_lines:
                new_lines[-1] += ' ' + remaining
            else:
                new_lines.append(remaining)
        
        # 남은 이모지 마지막 줄에 추가
        if emojis and new_lines:
            new_lines[-1] += ''.join(emojis)
        
        return '\n'.join(new_lines)

    def _create_ending_variations(self, original_copy: str) -> List[str]:
        """어미만 교체한 3가지 변형"""
        lines = [l.strip() for l in original_copy.split('\n') if l.strip()]
        
        # 어미 스타일 3가지
        styles = [
            {'name': '단정톤', 'endings': ['임', '함', '됨']},
            {'name': '놀람톤', 'endings': [';;', 'ㅋㅋ', ';;']},
            {'name': '감성톤', 'endings': ['ㅠㅠ', '💗', '🥹']},
        ]
        
        results = []
        for style in styles:
            new_lines = []
            for i, line in enumerate(lines):
                # 이모지 분리
                emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF\U00002700-\U000027BF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]')
                emojis_in_line = ''.join(emoji_pattern.findall(line))
                clean = emoji_pattern.sub('', line).strip()
                
                # 마지막 어미 교체
                if i < len(style['endings']):
                    clean = clean.rstrip('ㅋㅠ;.!?어 ')
                    new_line = f"{clean}{style['endings'][i]}"
                else:
                    new_line = clean
                
                if emojis_in_line:
                    new_line += emojis_in_line
                    
                new_lines.append(new_line)
            results.append('\n'.join(new_lines))
        
        return results

    def generate_candidates(self, original_copy: str, product_info: str, count=9) -> List[str]:
        """
        9개 후보 생성 (API 0회):
        - 3개: 구조 복제형 (고성과 골격 + 원본 키워드)
        - 3개: 어미 교체형 (원본 구조 + 다른 톤 어미)
        - 3개: 압축/확장형 (글자수 조절)
        """
        segments = self._split_original_into_segments(original_copy)
        candidates = []
        
        # ── 전략 1: 구조 복제형 (3개) ──
        # 고성과 게시물의 골격(줄수, 비율, 어미, 이모지)에 원본 단어를 채움
        skeletons = []
        for _, row in self.top_posts.iterrows():
            skel = self._extract_structural_skeleton(str(row['본문']))
            skeletons.append(skel)
        
        for i, skel in enumerate(skeletons[:3]):
            result = self._assemble_with_skeleton(skel, segments, i)
            if result.strip():
                candidates.append(result)
        
        # ── 전략 2: 어미 교체형 (3개) ──
        ending_variants = self._create_ending_variations(original_copy)
        candidates.extend(ending_variants)
        
        # ── 전략 3: 압축/확장형 (3개) ──
        lines = [l.strip() for l in original_copy.split('\n') if l.strip()]
        
        # 3-1: 2줄 압축 (Hook + 결론)
        if len(lines) >= 2:
            compressed = f"{lines[0]}\n{lines[-1]}"
            candidates.append(compressed)
        
        # 3-2: 4줄 확장 (중간에 강조 삽입)
        if len(lines) >= 2:
            expanded = f"{lines[0]}\n이거 진짜임..\n" + '\n'.join(lines[1:])
            candidates.append(expanded)
        
        # 3-3: 역순 (결론 먼저)
        reversed_copy = '\n'.join(reversed(lines))
        candidates.append(reversed_copy)
        
        return candidates[:count]


if __name__ == "__main__":
    print("=== LocalTemplateGenerator v2 단독 테스트 ===")
    mock_df = pd.DataFrame({
        '본문': [
            "엄마가 루이비통 샀냐고 물어봄ㅋㅋ 👜✨\n루이비통 디자이너가 코치로 오면서\n디자인이 넘 예뻐짐ㅠ💗",
            "일본 가면 이건 꼭 사야함;; 🔥\n안 사면 무조건 후회함\n진짜 인생템임",
            "이거 틴트 정착함 💖\n발색 미쳤고 퀄대박ㅠㅠ",
            "올영 갔다가 발견한 인생템;;\n가격도 착하고 퀄도 좋음🩷",
        ],
        'MSS': [30000, 28000, 25000, 22000]
    })
    
    gen = LocalTemplateGenerator(mock_df)
    original = "올리브영 갔다가 샤넬이랑 존똑인\n메이블린 틴트 발견함😮😮\n퀄은 똑같은데 가격이 너무 착해서 쟁여놨어🩷"
    
    results = gen.generate_candidates(original, "메이블린 틴트", count=9)
    for i, r in enumerate(results):
        print(f"\n── 후보 {i+1} ──")
        print(r)
