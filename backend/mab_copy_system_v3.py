# mab_copy_system_v3.py: 전체 시스템의 메인 파이프라인. 데이터 로딩, 전략 선택, 카피 생성 및 최종 선별을 조율하는 실행 파일.
import sys
import io
import json

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

from data_feedback_loop_v2 import MSSDataIntegrator
from mab_engine_v2 import DynamicMAB
from copy_generator_v2 import DynamicCopyGenerator
from copy_scorer_v3 import CopyScorer
from strategy_clusterer import StrategyClusterer

def main():
    # 1. Initialize MAB and Load Data
    mab = DynamicMAB(gamma=0.9)
    integrator = MSSDataIntegrator(r'c:\Users\ding9\Desktop\madoyo')
    
    # Define Core Strategic Clusters (The "Shindang-dong" Districts)
    sample_strategies = [
        {"category": "Personal_Experience", "본문": "비행기 2시간도 못 버티던 내가 이 사탕 하나로 인생 바뀜;; 진짜 강추함ㅋㅋ", "desc": "개인적인 불편함 해결과 실사용 톤"},
        {"category": "Curated_Tips", "본문": "일본 가면 이건 꼭 사와야 함. 안 사오면 무조건 후회하는 리스트 5가지 정리함", "desc": "정보 제공과 큐레이션"},
        {"category": "Strong_Hook", "본문": "진짜 미쳤음;; 이거 하나로 삶의 질 수직상승함. 왜 이제 알았나 싶을 정도임", "desc": "호기심 유발과 강력한 감정 표현"}
    ]
    integrator.clusterer.define_clusters_from_samples(sample_strategies)
    
    # Process all data (This will now use the defined clusters for reward attribution)
    data = integrator.process_all_data(mab)
    
    if data.empty:
        print("No data found.")
        return

    # Helper: Get top examples for few-shot prompting
    top_examples = integrator.get_top_performing_patterns(data, top_n=10)

    # 2. Setup Strategic Clustering (Already done above via integrator.clusterer)
    clusterer = integrator.clusterer
    
    # 3. Contextual Selection & Generation
    product = "자취생 필수템, 3분 만에 끝내는 배수구 세정제"
    print(f"\n[Step 3] Analyzing context for product: '{product}'...")
    
    # Compute contextual weights based on product-cluster similarity
    context_weights = clusterer.compute_context_weights(product)
    
    chosen_cluster = mab.select_arm(context_weights)
    cluster_info = clusterer.clusters[chosen_cluster]
    
    print(f"🎯 Selected Cluster: {cluster_info['name']} (Weight: {context_weights[chosen_cluster]:.2f})")
    print(f"💡 Strategy: {cluster_info['description']}")

    # Generate 9 Candidates based on the chosen strategy
    # (In this version, we focus on the chosen cluster to maximize relevance)
    generator = DynamicCopyGenerator(top_examples)
    candidates = []
    print("\n[Stage 1: Generating 9 Candidate Copies within the best cluster...]")
    
    for j in range(1, 10):
        candidate_id = f"C{j}"
        # Simplified simulation: generating variations of the strategy
        fake_copy = f"[{cluster_info['name']} 후보 {j}] {product}. {cluster_info['description']} 스타일로 작성된 예시 문구... 진짜 인생템임;;"
        
        candidates.append({
            "id": candidate_id,
            "strategy": cluster_info['name'],
            "copy": fake_copy
        })
    
    print(f"Successfully generated {len(candidates)} candidates.")

    # 4. Scoring Stage (Sub-agent Logic)
    scorer = CopyScorer(top_examples)
    scored_candidates = []
    
    print("\n[Stage 2: Scoring Candidates with Sub-agent...]")
    for c in candidates:
        # Generate scoring prompt
        scoring_prompt = scorer.generate_scoring_prompt(c['copy'], product)
        
        # Simulated Scoring Result (In a real flow, LLM would return this JSON)
        # We simulate variations in scores
        import random
        simulated_mss = random.randint(300, 2500)
        simulated_sim = random.randint(60, 95)
        
        level = "망함"
        if simulated_mss >= 2000: level = "초대박"
        elif simulated_mss >= 1000: level = "대박"
        elif simulated_mss >= 500: level = "평타"
        
        score_data = {
            "predicted_mss_level": level,
            "mss_score_estimate": simulated_mss,
            "category_similarity": simulated_sim,
            "reason": f"전략 {c['strategy']}의 후킹을 잘 살렸으며 사용자의 이전 고성과 게시물과 문체가 유사함.",
            "final_weight": simulated_mss * (simulated_sim / 100.0)
        }
        
        scored_candidates.append({
            "id": c['id'],
            "copy": c['copy'],
            "score_data": score_data
        })
        print(f"Scored {c['id']}: {level} (Predicted MSS: {simulated_mss})")

    # 5. Final Selection (Top 3)
    final_top_3 = scorer.select_top_3(scored_candidates)

    print("\n" + "="*60)
    print("MAB v3 스코어러 최종 선정 결과 (Top 3)")
    print("="*60)
    for i, item in enumerate(final_top_3):
        sd = item['score_data']
        print(f"RANK {i+1} [{item['id']}] - 성과예측: {sd['predicted_mss_level']} (Score: {sd['mss_score_estimate']:.0f})")
        print(f"카테고리 유사도: {sd['category_similarity']}%")
        print(f"평가 사유: {sd['reason']}")
        print(f"카피 내용:\n{item['copy']}")
        print("-" * 60)

if __name__ == "__main__":
    main()
