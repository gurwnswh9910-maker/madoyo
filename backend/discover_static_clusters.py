import sys
import os
import io
import re
import json
import time

# UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

sys.path.append(os.path.join(os.path.dirname(__file__)))

from google import genai
from dotenv import load_dotenv
from data_feedback_loop_v2 import MSSDataIntegrator
from embedding_utils import EmbeddingManager
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def main():
    load_dotenv(os.path.join(base_path, '.env'))
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    MODEL = "gemini-2.5-flash"

    print("=" * 80)
    print("🚀 정적 카피 클러스터 자동 발굴 시스템 (Static Cluster Discovery)")
    print("=" * 80)

    # 1. 데이터 로딩 및 임베딩 준비
    print("\n1. 데이터 및 임베딩 로딩...")
    integrator = MSSDataIntegrator(base_path)
    # Dummy MAB for loading purposes
    class DummyMAB:
        def update_reward(self, *args, **kwargs): pass
        clusters = {}
    
    all_data = integrator.process_all_data(DummyMAB())
    
    def is_korean(text):
        if not isinstance(text, str): return False
        kor_count = len(re.findall('[가-힣]', text))
        return (kor_count / max(len(text), 1)) > 0.3

    kor_data = all_data[all_data['본문'].apply(is_korean)].drop_duplicates(subset='본문').copy()
    print(f"   한국어 대상 데이터: {len(kor_data)}개")

    emb_mgr = EmbeddingManager(storage_path=os.path.join(base_path, 'embeddings.pkl'))
    
    # 2. 임베딩 매트릭스 구성
    texts = kor_data['본문'].tolist()
    msses = kor_data['MSS'].tolist()
    embeddings = emb_mgr.get_many_embeddings(texts)
    
    valid_indices = [i for i, emb in enumerate(embeddings) if emb is not None]
    valid_texts = [texts[i] for i in valid_indices]
    valid_msses = [msses[i] for i in valid_indices]
    valid_embs = np.array([embeddings[i] for i in valid_indices])

    # 3. 대조군(Top vs Similar Low) 페어 3쌍 추출
    print("\n2. 대조 분석 페어링 (Top vs Similar-Low)...")
    TOP_N = 3
    top_indices = np.argsort(valid_msses)[::-1][:TOP_N]
    
    contrast_pairs = []
    for idx in top_indices:
        target_emb = valid_embs[idx].reshape(1, -1)
        sims = cosine_similarity(target_emb, valid_embs)[0]
        
        # 자기 자신 제외하고, 성과가 현저히 낮은 것(MSS < 100 등) 중 유사도 가장 높은 것
        candidates = []
        for j, sim in enumerate(sims):
            if j == idx: continue
            if valid_msses[j] < (valid_msses[idx] * 0.2): # 20% 미만 성과
                candidates.append((j, sim))
        
        if candidates:
            # Sort by similarity desc
            candidates.sort(key=lambda x: x[1], reverse=True)
            bottom_idx = candidates[0][0]
            contrast_pairs.append({
                "top_text": valid_texts[idx],
                "top_mss": valid_msses[idx],
                "bottom_text": valid_texts[bottom_idx],
                "bottom_mss": valid_msses[bottom_idx],
                "similarity": candidates[0][1]
            })

    for i, pair in enumerate(contrast_pairs, 1):
        print(f"\n[Pair {i}] 유사도: {pair['similarity']:.2f}")
        print(f"  🟢 성공 (MSS {pair['top_mss']:.0f}): {pair['top_text'][:60]}...")
        print(f"  🔴 실패 (MSS {pair['bottom_mss']:.0f}): {pair['bottom_text'][:60]}...")

    # 4. LLM을 통한 복합 피처 추출
    print("\n3. Gemini를 활용한 복합 피처(Static Clusters) 추출...")
    prompt = f"""
당신은 대한민국 최고의 퍼포먼스 마케팅 카피라이터 분석가입니다.
아래는 주제나 내용은 매우 유사하지만 성과(MSS 점수)에서 극명한 차이를 보인 카피 대조 쌍들입니다.

[분석 대상 쌍]
"""
    for i, pair in enumerate(contrast_pairs, 1):
        prompt += f"""
쌍 {i}:
- 성공 카피 (점수: {pair['top_mss']:.0f}): {pair['top_text']}
- 실패 카피 (점수: {pair['bottom_mss']:.0f}): {pair['bottom_text']}
"""

    prompt += """
이 쌍들을 분석하여, "결정적으로 성공을 만든 복합적인 특징(Static Cluster)" 3가지를 명시화해주세요.
단순히 "사진이 있다/없다", "길다/짧다" 같은 단일 속성이 아니라, **여러 심리적/구조적 장치들이 결합하여 강력한 후킹을 만드는 복합 피처**여야 합니다. (예: 구체적 수치 제시 + 타인의 반응 묘사 결합)

출력 형식은 반드시 아래 JSON 배열 포맷을 따르세요:
[
  {
    "cluster_name": "클러스터 이름 (예: 구체적 통점 공감 + 타인 검증형)",
    "description": "해당 클러스터의 상세 설명",
    "feature_1": "필수 속성 1 (예: 아주 구체적인 일상적 불편함 묘사)",
    "feature_2": "필수 속성 2 (예: 엘리베이터, 친구 등 제3자의 즉각적 반응 포함)"
  }
]
"""
    
    print("   Gemini 분석 요청 중...")
    response = client.models.generate_content(model=MODEL, contents=prompt)
    res_text = response.text.strip()
    res_text = re.sub(r'^```(json)?|```$', '', res_text, flags=re.MULTILINE).strip()
    
    try:
        discovered_clusters = json.loads(res_text)
    except:
        print("JSON 파싱 에러, 원본 텍스트 출력:")
        print(res_text)
        return

    print(f"\n✅ {len(discovered_clusters)}개의 정적 클러스터 후보 발견!")

    # 5. 가설 검증 (전체 데이터 대상 평균 성과 차이 비교)
    print("\n4. 발견된 클러스터 피처 스코어링 검증...")
    
    # 텍스트 내 키워드 매칭이나 LLM 일괄 스코어링은 비용/시간 상 제한이 큼.
    # 따라서 각 클러스터 정의를 LLM에게 주고, "이 피처가 적용된 카피인지 O/X로 평가"하는 프롬프트를
    # 전체 텍스트 중 무작위 50개 샘플에 던져서, O 그룹과 X 그룹의 평균 성과를 본다.
    
    sample_size = min(50, len(valid_texts))
    sample_indices = np.random.choice(len(valid_texts), sample_size, replace=False)
    sample_texts = [valid_texts[i] for i in sample_indices]
    sample_msses = [valid_msses[i] for i in sample_indices]

    results_report = []

    for cluster in discovered_clusters:
        c_name = cluster['cluster_name']
        f1 = cluster['feature_1']
        f2 = cluster['feature_2']
        
        print(f"\n   [검증 진행 중] {c_name}")
        
        # Batch evaluation to save time
        eval_prompt = f"""
다음은 마케팅 카피 클러스터 기준입니다:
이름: {c_name}
필수 속성 1: {f1}
필수 속성 2: {f2}

아래 카피들이 위의 2가지 필수 속성을 "모두(복합적으로)" 만족하는지 O 또는 X로만 판별하세요.
응답은 줄바꿈으로 구분된 O, X 리스트여야 하며, 카피 번호 순서와 동일하게 정확히 {sample_size}줄로 출력하세요.

"""
        for i, text in enumerate(sample_texts):
            clean_text = text.replace('\n', ' ')[:100]
            eval_prompt += f"{i+1}. {clean_text}\n"

        try:
            eval_res = client.models.generate_content(model=MODEL, contents=eval_prompt)
            eval_lines = [line.strip().upper() for line in eval_res.text.strip().split('\n') if line.strip()]
            
            # 매칭
            match_msses = []
            non_match_msses = []
            
            for score_str, mss in zip(eval_lines, sample_msses):
                if 'O' in score_str:
                    match_msses.append(mss)
                else:
                    non_match_msses.append(mss)
            
            avg_match = sum(match_msses)/len(match_msses) if match_msses else 0
            avg_non = sum(non_match_msses)/len(non_match_msses) if non_match_msses else 0
            
            uplift = avg_match - avg_non if avg_non > 0 else 0
            
            print(f"      적용 그룹({len(match_msses)}개) 평균 MSS: {avg_match:.0f}")
            print(f"      미적용 그룹({len(non_match_msses)}개) 평균 MSS: {avg_non:.0f}")
            print(f"      👉 피처 복합 적용 시 효과: {uplift:+.0f}점")
            
            cluster['validation'] = {
                'match_count': len(match_msses),
                'match_avg_mss': avg_match,
                'non_match_count': len(non_match_msses),
                'non_match_avg_mss': avg_non,
                'uplift': uplift
            }
            results_report.append(cluster)
            
        except Exception as e:
            print(f"      검증 중 에러 발생: {e}")
            break
            
        time.sleep(2) # rate limit prevention

    # 6. 최종 보고서 작성 (마크다운)
    report_path = os.path.join(base_path, '내부_문서', 'static_clusters_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("# 카피 스플릿 대조 분석 기반 정적 클러스터 발굴 보고서\n\n")
        f.write("> 고성과 게시물과 유사도(Cosine)가 높지만 성과가 낮은 페어들을 LLM으로 역추적하여 발굴한 '복합 특징성' 정적 클러스터입니다.\n\n")
        
        for c in results_report:
            f.write(f"## 🎯 {c['cluster_name']}\n")
            f.write(f"- **설명**: {c['description']}\n")
            f.write(f"- **필수 복합 피처 1**: {c['feature_1']}\n")
            f.write(f"- **필수 복합 피처 2**: {c['feature_2']}\n\n")
            
            v = c.get('validation')
            if v:
                f.write(f"### 📊 성과 검증 (샘플 테스트)\n")
                f.write(f"- 해당 복합 피처 보유 카피 ({v['match_count']}개) 평균 MSS: **{v['match_avg_mss']:.0f}점**\n")
                f.write(f"- 미보유 카피 ({v['non_match_count']}개) 평균 MSS: **{v['non_match_avg_mss']:.0f}점**\n")
                f.write(f"- **증분(Uplift)**: 📈 **{v['uplift']:+.0f}점**\n\n")
                f.write("---\n\n")
                
    print(f"\n최종 분석 보고서가 생성되었습니다: {report_path}")

if __name__ == "__main__":
    main()
