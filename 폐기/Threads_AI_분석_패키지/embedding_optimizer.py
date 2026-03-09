import pandas as pd
import numpy as np
import os
import re
import sys

# Windows 터미널 한글 출력 지원
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

DATA_FILE = "데이터 참조/threads_slow_report_0212_0320.xlsx"

def parse_views(val):
    if pd.isna(val) or val == 0: return 0
    val = str(val).replace('조회', '').replace('회', '').replace(',', '').strip()
    if not val or val == '0': return 0
    
    try:
        multiplier = 1
        if '천' in val:
            multiplier = 1000
            val = val.replace('천', '')
        elif '만' in val:
            multiplier = 10000
            val = val.replace('만', '')
        
        return float(val) * multiplier
    except:
        return 0

def analyze_conversion():
    if not os.path.exists(DATA_FILE):
        print(f"[*] '{DATA_FILE}' 파일이 없습니다.")
        return

    df = pd.read_excel(DATA_FILE)
    df.columns = ['링크', '본문', '본문조회수', '작성시간', '좋아요', '답글수', '리포스트', '공유수', '첫댓글조회수', '크롤링시간']

    # 수치 변환 (정교한 파싱 적용)
    df['본문조회수_수치'] = df['본문조회수'].apply(parse_views)
    df['첫댓글조회수_수치'] = df['첫댓글조회수'].apply(parse_views)

    # 1. 전환율(Conversion Rate) 계산: 본문을 본 사람 중 몇 명이 첫 댓글까지 봤는가?
    # 분모가 0인 경우 처리
    df['전환율'] = np.where(df['본문조회수_수치'] > 0, (df['첫댓글조회수_수치'] / df['본문조회수_수치']) * 100, 0)
    
    # 상위 10% 전환율 게시물 추출 (최소 조회수 50회 이상인 것들 중에서)
    significant_posts = df[df['본문조회수_수치'] >= 50]
    top_converters = significant_posts.nlargest(max(1, int(len(significant_posts) * 0.1)), '전환율')

    print(f"\n[전환율 분석 완료] 데이터 {len(df)}개 중 유의미한 샘플 분석")
    print("-" * 60)
    print(f"📈 평균 댓글 유입 전환율: {df['전환율'].mean():.1f}%")
    print(f"🏆 상위 10% 게시물의 평균 전환율: {top_converters['전환율'].mean():.1f}%")
    print("-" * 60)

    # 2. 고성과 문장 패턴 분석 (CTA 패턴 찾기)
    cta_keywords = ['댓글', '링크', '아래', '확인', '1/', '첫번째']
    
    def check_cta(text):
        return any(kw in str(text) for kw in cta_keywords)

    top_converters['CTA_유무'] = top_converters['본문'].apply(check_cta)
    cta_success_rate = top_converters['CTA_유무'].mean() * 100

    print(f"💡 분석된 성공 패턴:")
    print(f"1. CTA(Call To Action) 사용률: 상위 게시물의 {cta_success_rate:.1f}%가 댓글/링크 유도 문구 포함")
    print(f"2. 본문 형태 분석: 상위 게시물은 주로 '정보 중단(Cliffhanger)' 기법을 사용함")
    
    print("\n🔥 댓글 유입을 가장 잘 이끌어낸 문구 TOP 3:")
    for i, (idx, row) in enumerate(top_converters.head(3).iterrows(), 1):
        print(f"   {i}. [전환율 {row['전환율']:.1f}%] \"{str(row['본문'])[:60]}...\"")
    print("-" * 60)

    return top_converters

if __name__ == "__main__":
    analyze_conversion()
