import sys
import io
import os
import json
import pandas as pd
from dotenv import load_dotenv
import google.generativeai as genai

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

# Mock or absolute paths for imports
base_path = r'c:\Users\ding9\Desktop\madoyo'
src_path = os.path.join(base_path, '작동중코드')
sys.path.append(src_path)

from data_feedback_loop_v2 import MSSDataIntegrator
from copy_scorer_v3 import CopyScorer
from copy_generator_v2 import DynamicCopyGenerator

def main():
    load_dotenv(os.path.join(base_path, '.env'))
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-2.0-flash')
    
    def safe_generate(prompt):
        import time
        for attempt in range(5):
            try:
                res = model.generate_content(prompt)
                time.sleep(5) # Cooldown after success
                return res
            except Exception as e:
                if "429" in str(e) and attempt < 4:
                    wait_time = 15 * (attempt + 1)
                    print(f"  429 hit (Attempt {attempt+1}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise e


    # original copy from user
    original_copy = """이거 요즘 일본에서 난리 난 정착템임 🔥
작은 패드 하나로 메이크업 전에 습포하면
피부 촉촉 + 유분 정리까지 한 번에 😍"""
    
    product_focus = "일본 SNS 화제템, 메이크업 전 유분 정리 및 수분 충전 패드 (습포법)"

    print("1. Loading historical data from 데이터 참조/dotori.xlsx...")
    integrator = MSSDataIntegrator(base_path)
    # We use a dummy MAB just to trigger data processing
    class DummyMAB:
        def update_reward(self, cluster_idx, reward): pass
    
    data = integrator.process_all_data(DummyMAB())
    top_examples = integrator.get_top_performing_patterns(data, top_n=5)
    
    # 2. Setup Generator and Scorer
    generator = DynamicCopyGenerator(top_examples)
    scorer = CopyScorer(top_examples)

    print("\n2. Generating optimized candidates using Gemini...")
    
    strategies = [
        {"name": "Viral_Secret", "desc": "주변에서 '피부 뭐 발랐냐'고 물어보게 만드는 비밀 폭로 톤 (MSS 24,000 이상 루이비통 패턴 응용)"},
        {"name": "MUA_Insider", "desc": "일본 샵 원장님이 안 알려주는 메이크업 밀착 비결. '이거 하나면 샵 갔다온 피부 됨' 강조"},
        {"name": "Benefit_Extreme", "desc": "유분기 때문에 화장 다 지워지던 과거와 현재의 극명한 대비. '내 인생은 이 패드 전후로 나뉨'"}
    ]

    candidates = []
    # Add original as a baseline candidate
    candidates.append({"id": "Original", "strategy": "User_Input", "copy": original_copy})

    import time
    for i, strat in enumerate(strategies):
        print(f"Generating candidate {i+1} ({strat['name']})...")
        time.sleep(2) # Prevent burst 429
        prompt = generator.generate_prompt(strat['name'], product_focus, strat['desc'])
        response = safe_generate(prompt)
        candidates.append({
            "id": f"Opt_{i+1}",
            "strategy": strat['name'],
            "copy": response.text.strip()
        })

    print(f"Generated {len(candidates)} total candidates for scoring.")

    # 3. Scoring Stage
    print("\n3. Scoring candidates for performance prediction...")
    scored_results = []
    
    for c in candidates:
        print(f"Scoring {c['id']}...")
        time.sleep(2) # Prevent burst 429
        scoring_prompt = scorer.generate_scoring_prompt(c['copy'], product_focus)
        response = safe_generate(scoring_prompt)
        
        # Parse JSON from response
        try:
            # Handle potential markdown code blocks in response
            clean_text = response.text.strip()
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[1].split("```")[0].strip()
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
            score_data = json.loads(clean_text)
            
            # If LLM returns a list, take the first item
            if isinstance(score_data, list) and len(score_data) > 0:
                score_data = score_data[0]
            
            if not isinstance(score_data, dict):
                raise ValueError("LLM result is not a dictionary")

            scored_results.append({
                "id": c['id'],
                "strategy": c['strategy'],
                "copy": c['copy'],
                "score_data": score_data
            })
            print(f"Scored {c['id']}: {score_data.get('predicted_mss_level', 'N/A')} (MSS: {score_data.get('mss_score_estimate', 0)})")
        except Exception as e:
            print(f"Error scoring {c['id']}: {e}")
            # Fallback
            scored_results.append({
                "id": c['id'],
                "strategy": c['strategy'],
                "copy": c['copy'],
                "score_data": {"predicted_mss_level": "Error", "mss_score_estimate": 0, "category_similarity": 0, "reason": str(e)}
            })

    # 4. Final Selection and Comparison
    top_3 = scorer.select_top_3(scored_results)
    
    print("\n" + "="*70)
    print("MAB Copy Optimization Report: 'Japanese Beauty Pad'")
    print("="*70)
    
    # Show Original first for baseline
    orig = next(x for x in scored_results if x['id'] == 'Original')
    print(f"Baseline (Original Content):\n{orig['copy']}")
    print(f"Predicted Score: {orig['score_data'].get('mss_score_estimate')} ({orig['score_data'].get('predicted_mss_level')})")
    print("-" * 70)

    print("\nOptimized Top 3 Recommendations:")
    for i, item in enumerate(top_3):
        sd = item['score_data']
        print(f"RANK {i+1} [{item['id']} - {item['strategy']}]")
        print(f"Outcome: {sd['predicted_mss_level']} (Predicted MSS: {sd['mss_score_estimate']})")
        print(f"Insight: {sd['reason']}")
        print(f"Final Copy:\n{item['copy']}")
        print("-" * 70)

if __name__ == "__main__":
    main()
