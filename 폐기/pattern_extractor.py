import sys
import io
import re
from typing import Dict, List, Any

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

class MicroscopicPatternExtractor:
    """
    copy_analysis_guideline.md 기반으로 카피의 미시적 패턴을 분석하는 엔진
    목표: 문장 리듬, 감정, 키워드, 어투를 정량화하여 AI 프롬프트에 주입
    """
    
    def __init__(self, guideline_path=None):
        self.guideline_path = guideline_path
        # 감정 어미 패턴
        self.emotion_endings = {
            'ㅋㅋ': ('가벼운 웃음', 3),
            ';;': ('놀라움/믿기 어려움', 4),
            'ㅠㅠ': ('감동/안타까움', 4),
            'ㅠ': ('감동/안타까움', 3),
            '함': ('단정/확신', 3),
            '임': ('단정/확신', 3),
            '래': ('전달/소문', 2),
            '!': ('강조', 3),
            '?': ('의문', 2)
        }
    
    def analyze_rhythm(self, text: str) -> Dict[str, Any]:
        """
        문장 리듬 분석: 줄 구조, 글자수, 강약 패턴
        """
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        chars_per_line = [len(l) for l in lines]
        
        # 리듬 패턴 감지 (상승/하강/평평)
        rhythm = "flat"
        if len(chars_per_line) >= 2:
            if chars_per_line[0] < chars_per_line[-1]:
                rhythm = "ascending"  # 짧→긴
            elif chars_per_line[0] > chars_per_line[-1]:
                rhythm = "descending"  # 긴→짧
        
        return {
            'line_count': len(lines),
            'total_chars': sum(chars_per_line),
            'chars_per_line': chars_per_line,
            'avg_chars_per_line': sum(chars_per_line) / len(lines) if lines else 0,
            'rhythm_pattern': rhythm
        }
    
    def analyze_emotion(self, text: str) -> Dict[str, Any]:
        """
        감정 강도 1~5 분류 및 톤 추출
        """
        emotion_score = 0
        detected_endings = []
        
        # 어미 패턴으로 감정 강도 계산
        for ending, (desc, score) in self.emotion_endings.items():
            if ending in text:
                emotion_score = max(emotion_score, score)
                detected_endings.append(desc)
        
        # 톤 유형 판별
        tone_type = "neutral"
        if "엄마가" in text or "친구가" in text or "물어봄" in text or "놀람" in text:
            tone_type = "external_validation"  # 외부 검증 톤 (고성과)
        elif "샵" in text or "전문가" in text or "원장" in text:
            tone_type = "authority"  # 권위 톤
        elif "나" in text or "내" in text:
            tone_type = "confession"  # 고백 톤
        elif "ㅋ" in text or "ㅠ" in text:
            tone_type = "friend"  # 친구 톤
        
        return {
            'emotion_intensity': emotion_score,
            'detected_endings': detected_endings,
            'tone_type': tone_type
        }
    
    def extract_keywords(self, text: str) -> Dict[str, Any]:
        """
        핵심 키워드, 이모지 위치/밀도 분석
        """
        # 이모지 추출
        emoji_pattern = re.compile(r'[\U0001F300-\U0001F9FF]')
        emojis = emoji_pattern.findall(text)
        
        # 감정 키워드
        high_impact_keywords = ['인생템', '대박', '미쳤음', '심폐소생', '광명', '졸업', '역전']
        found_keywords = [kw for kw in high_impact_keywords if kw in text]
        
        # 장소/출처 키워드
        source_keywords = ['일본', '샵', '전문가', '원장', '비법']
        found_sources = [kw for kw in source_keywords if kw in text]
        
        return {
            'emoji_count': len(emojis),
            'emojis': emojis,
            'high_impact_keywords': found_keywords,
            'source_keywords': found_sources
        }
    
    def get_comprehensive_pattern(self, top_posts: List[str]) -> Dict[str, Any]:
        """
        Top-N 게시물의 공통 패턴을 종합 분석
        """
        all_patterns = []
        
        for post in top_posts:
            pattern = {
                'text': post,
                'rhythm': self.analyze_rhythm(post),
                'emotion': self.analyze_emotion(post),
                'keywords': self.extract_keywords(post)
            }
            all_patterns.append(pattern)
        
        # 공통 패턴 추출
        common_pattern = {
            'avg_line_count': sum(p['rhythm']['line_count'] for p in all_patterns) / len(all_patterns),
            'avg_total_chars': sum(p['rhythm']['total_chars'] for p in all_patterns) / len(all_patterns),
            'dominant_rhythm': self._get_most_common([p['rhythm']['rhythm_pattern'] for p in all_patterns]),
            'dominant_tone': self._get_most_common([p['emotion']['tone_type'] for p in all_patterns]),
            'avg_emotion_intensity': sum(p['emotion']['emotion_intensity'] for p in all_patterns) / len(all_patterns),
            'common_endings': self._get_common_endings(all_patterns),
            'emoji_density': sum(p['keywords']['emoji_count'] for p in all_patterns) / len(all_patterns),
            'high_impact_keywords': self._merge_keywords([p['keywords']['high_impact_keywords'] for p in all_patterns])
        }
        
        return {
            'individual_patterns': all_patterns,
            'common_pattern': common_pattern
        }
    
    def _get_most_common(self, items: List[str]) -> str:
        """가장 많이 등장하는 항목 반환"""
        from collections import Counter
        if not items:
            return "unknown"
        return Counter(items).most_common(1)[0][0]
    
    def _get_common_endings(self, patterns: List[Dict]) -> List[str]:
        """공통 어미 패턴 추출"""
        all_endings = []
        for p in patterns:
            all_endings.extend(p['emotion']['detected_endings'])
        from collections import Counter
        return [ending for ending, count in Counter(all_endings).most_common(3)]
    
    def _merge_keywords(self, keyword_lists: List[List[str]]) -> List[str]:
        """키워드 리스트 병합 (중복 제거)"""
        merged = []
        for kw_list in keyword_lists:
            merged.extend(kw_list)
        return list(set(merged))

# 테스트 코드
if __name__ == "__main__":
    extractor = MicroscopicPatternExtractor()
    
    # 예시 Top-3 MSS 게시물
    top_posts = [
        "엄마가 \"루이비통\" 샀냐고 물어봄ㅋㅋ 👜✨\n루이비통 디자이너가 \"코치\"로 오면서\n디자인이 넘 예뻐짐ㅠ💗",
        "Kalau kulit sawo matang, trust me… Warm Teddy menang 😌 i dah grab buat raya nnti🤪",
        "我要心疼死了😭😭😭從一個兩個變成三個...連知珉都撐不住了😭欸里這樣蹲真的越看越心疼😭"
    ]
    
    pattern = extractor.get_comprehensive_pattern(top_posts)
    
    print("=== 공통 패턴 분석 결과 ===")
    cp = pattern['common_pattern']
    print(f"평균 줄 수: {cp['avg_line_count']:.1f}줄")
    print(f"평균 글자 수: {cp['avg_total_chars']:.0f}자")
    print(f"주요 리듬: {cp['dominant_rhythm']}")
    print(f"주요 톤: {cp['dominant_tone']}")
    print(f"감정 강도: {cp['avg_emotion_intensity']:.1f}/5")
    print(f"공통 어미: {', '.join(cp['common_endings'])}")
    print(f"이모지 밀도: 평균 {cp['emoji_density']:.1f}개/게시물")
