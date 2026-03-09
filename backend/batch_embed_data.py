import sys
import os
import io
import pandas as pd
import re

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

sys.path.append(os.path.join(os.path.dirname(__file__)))
from embedding_utils import EmbeddingManager

# 파일 경로 스캐닝
base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
data_dir = os.path.join(base_path, '데이터 참조')

def get_target_files():
    targets = []
    # 고정 파일 패턴
    for fixed_base in ['dotori', 'otter']:
        for ext in ['.xlsx', '.csv']:
            p = os.path.join(data_dir, fixed_base + ext)
            if os.path.exists(p):
                targets.append(p)
    
    # 패턴 매칭 파일 (Threads 리포트들)
    if os.path.exists(data_dir):
        for f in os.listdir(data_dir):
            if f.startswith('threads_slow_report_') or f.startswith('threads_live_report_'):
                if f.endswith('.xlsx') or f.endswith('.csv'):
                    targets.append(os.path.join(data_dir, f))
    
    # 중복 제거
    return list(set(targets))

def is_korean(text):
    if not isinstance(text, str): return False
    kor_count = len(re.findall('[가-힣]', text))
    return (kor_count / max(len(text), 1)) > 0.3

def extract_texts_from_file(filepath):
    try:
        if filepath.endswith('.xlsx'):
            df = pd.read_excel(filepath)
        elif filepath.endswith('.csv'):
            try:
                df = pd.read_csv(filepath, encoding='utf-8-sig')
            except:
                df = pd.read_csv(filepath, encoding='cp949')
        else:
            return []

        if '본문' in df.columns:
            # 본문 추출 및 NaN 제거
            texts = df['본문'].dropna().astype(str).tolist()
            # 한국어 필터링
            texts = [t.strip() for t in texts if is_korean(t.strip())]
            return texts
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return []

def main():
    print("=" * 60)
    print("데이터 병합 및 일괄 임베딩 (dotori, otter & 최신 수집본)")
    print("=" * 60)
    
    all_texts = []
    
    # 1. 파일에서 데이터 추출
    print(f"1️⃣ 파일 로딩 중...")
    
    target_files = get_target_files()
    for filepath in target_files:
        texts = extract_texts_from_file(filepath)
        all_texts.extend(texts)
        print(f"   - {os.path.basename(filepath)}: {len(texts)}개 (한국어)")
        
    # 중복 텍스트 및 빈 문자열 제거
    unique_texts = list(set([t for t in all_texts if t]))
    print(f"   => 총 유니크(중복제거) 한국어 대상 텍스트 수: {len(unique_texts)}개")

    if not unique_texts:
        print("   임베딩할 데이터가 없습니다.")
        return

    # 2. 임베딩 매니저 초기화 및 일괄 처리
    print(f"\n2️⃣ 임베딩 매니저 로딩 및 신규 데이터 API 호출 (Gemini)..")
    emb_mgr = EmbeddingManager(storage_path=os.path.join(base_path, 'embeddings.pkl'))
    
    start_count = len(emb_mgr.embeddings)
    print(f"   - 기존 저장된 임베딩: {start_count}개")
    
    # get_many_embeddings 호출 시, 없는 것들은 알아서 chunk 돌리고 저장함
    _ = emb_mgr.get_many_embeddings(unique_texts)
    
    end_count = len(emb_mgr.embeddings)
    new_count = end_count - start_count
    
    print(f"\n✅ 완료되었습니다!")
    print(f"   - 새롭게 추가된 임베딩 개수: {new_count}개")
    print(f"   - 최종 총 누적 임베딩: {end_count}개")
    print("=" * 60)

if __name__ == "__main__":
    main()
