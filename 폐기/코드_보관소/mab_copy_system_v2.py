import sys
import io

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

from data_feedback_loop_v2 import MSSDataIntegrator
from mab_engine_v2 import DynamicMAB
from copy_generator_v2 import DynamicCopyGenerator

def main():
    # 1. Initialize and Load Data
    integrator = MSSDataIntegrator(r'c:\Users\ding9\Desktop\madoyo')
    data = integrator.process_all_data()
    
    if data.empty:
        print("No data found in dotori.xlsx or reports.")
        return

    # 2. Extract Top Patterns and Update MAB
    top_examples = integrator.get_top_performing_patterns(data, top_n=5)
    
    # In v2, we define dynamic arms based on these top patterns
    # For simulation, we create arm names based on the top 2 types of success
    mab = DynamicMAB(gamma=0.9)
    for i, ex in enumerate(top_examples[:2]):
        arm_name = f"Successful_Pattern_{i+1}"
        mab.add_arm(arm_name, {"pattern": ex['본문'][:50]})
        mab.update(arm_name, ex['MSS'])

    # 3. Select Best Arm and Generate Copy
    best_arm = mab.select_arm()
    metadata = mab.get_arm_metadata(best_arm)
    
    generator = DynamicCopyGenerator(top_examples)
    product = "자취생 필수템, 3분 만에 끝내는 배수구 세정제"
    
    prompt = generator.generate_prompt(
        best_arm, 
        product, 
        extra_strategy_desc=f"기존 성공 패턴 기반: {metadata.get('pattern', '')}..."
    )
    
    print("\n" + "="*50)
    print("MAB v2 최적화 결과")
    print("="*50)
    print(f"학습된 게시물 수: {len(data)}")
    print(f"추천 전략: {best_arm}")
    print(f"패턴 근거: {metadata.get('pattern', '')[:40]}...")
    print("-" * 50)
    print("생성된 프롬프트 (LLM 입력용):")
    print(prompt)

if __name__ == "__main__":
    main()
