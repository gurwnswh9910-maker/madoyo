import pandas as pd
import numpy as np
import os
import re
import sys

# Windows 터미널 한글/이모지 출력 지원
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.detach(), encoding='utf-8')

# --- [설정] ---
DATA_FILE = "데이터 참조/threads_slow_report_0212_0320.xlsx"

def analyze_patterns():
    if not os.path.exists(DATA_FILE):
        print(f"[*] '{DATA_FILE}' 파일이 없어 가상 데이터로 분석을 시뮬레이션합니다.")
        # 가상 데이터 생성 (실제 파일 없을 시 데모용)
        data = {
            '본문': ["안녕!", "이거 대박이다 😊", "팁 알려줌: 1. 코딩 2. 휴식", "오늘 점심 뭐 먹지?"],
            '본문조회수': [100, 500, 300, 50],
            '좋아요': [10, 50, 20, 5],
            '답글수': [2, 10, 5, 1],
            '공유수': [1, 5, 2, 0],
            '리포스트': [0, 2, 1, 0]
        }
        df = pd.DataFrame(data)
    else:
        # 1. 데이터 로드 및 전처리
        df = pd.read_excel(DATA_FILE)
        # 컬럼명 강제 매핑 (데이터 순서 기준)
        df.columns = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']

    # 수치 데이터 변환 및 결측치 처리
    numeric_cols = ['본문조회수', '좋아요', '답글수', '리포스트', '공유수']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 2. 성과 점수(Success Score) 계산
    # 가중치: 조회수(1) + 좋아요(10) + 답글(5) + 공유(15)
    df['성과점수'] = df['본문조회수'] + (df['좋아요'] * 10) + (df['답글수'] * 5) + (df['공유수'] * 15)
    
    # 상위 10% 게시물 추출
    top_count = max(1, int(len(df) * 0.1))
    top_10_percent = df.nlargest(top_count, '성과점수')

    print(f"\n[분석 완료] 총 {len(df)}개 데이터 분석")
    print("-" * 50)
    print(f"🏆 상위권 성공 게시물의 특징:")
    
    avg_len = top_10_percent['본문'].apply(lambda x: len(str(x))).mean()
    print(f"1. 평균 본문 길이: 약 {int(avg_len)}자")
    
    def count_emojis(text):
        return len(re.findall(r'[^\w\s,.]', str(text)))
    avg_emojis = top_10_percent['본문'].apply(count_emojis).mean()
    print(f"2. 평균 이모지 사용: {avg_emojis:.1f}개")

    print("\n🔥 가장 반응이 좋았던 문구 (TOP 3):")
    for i, row in enumerate(top_10_percent['본문'].head(3), 1):
        clean_text = str(row).replace('\n', ' ')[:50] + "..."
        print(f"   {i}. \"{clean_text}\"")
    print("-" * 50)

    return top_10_percent

def generate_optimized_copy(draft, patterns):
    print("\n✍️ 입력하신 초안을 분석된 성공 패턴에 맞춰 최적화합니다...")
    # 실제 AI 제안은 에이전트(Antigravity)가 이 분석 결과를 바탕으로 대화창에서 수행합니다.
    print(f"[원문 초안]: {draft}")
    print("\n💡 [패턴 적용 팁]")
    print(f"- 현재 성공한 글들은 평균 {int(patterns['본문'].apply(lambda x: len(str(x))).mean())}자 정도입니다.")
    print(f"- 이모지를 조금 더 섞어서 친근하게 다가가 보세요.")

if __name__ == "__main__":
    top_patterns = analyze_patterns()
    
    if top_patterns is not None:
        print("\n[AI 카피라이터 가동]")
        print("초안을 입력하시면 분석 결과를 바탕으로 수정안을 제안해 드립니다.")
        # 사용자 입력을 기다리는 예시 (실제 실행 시 사용)
        # user_draft = input("새로운 포스팅 초안을 입력하세요: ")
        # generate_optimized_copy(user_draft, top_patterns)
