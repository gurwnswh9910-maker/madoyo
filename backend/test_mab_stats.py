import sys
import os

sys.path.append(r'c:\Users\ding9\Desktop\madoyo\작동중코드')

from mab_engine_v2 import DynamicMAB
from data_feedback_loop_v2 import MSSDataIntegrator

def main():
    try:
        mab = DynamicMAB(gamma=0.9)
        integrator = MSSDataIntegrator(r'c:\Users\ding9\Desktop\madoyo')
        
        sample_strategies = [
            {"category": "Personal_Experience", "본문": "비행기 2시간도 못 버티던 내가 이 사탕 하나로 인생 바뀜;; 진짜 강추함ㅋㅋ", "desc": "개인적인 불편함 해결과 실사용 톤"},
            {"category": "Curated_Tips", "본문": "일본 가면 이건 꼭 사와야 함. 안 사오면 무조건 후회하는 리스트 5가지 정리함", "desc": "정보 제공과 큐레이션"},
            {"category": "Strong_Hook", "본문": "진짜 미쳤음;; 이거 하나로 삶의 질 수직상승함. 왜 이제 알았나 싶을 정도임", "desc": "호기심 유발과 강력한 감정 표현"}
        ]
        
        integrator.clusterer.define_clusters_from_samples(sample_strategies)
        data = integrator.process_all_data(mab)
        
        print("====== MAB ARM STATS ======")
        stats = mab.get_stats()
        for k, v in stats.items():
            print(f"Arm: {k}, EV: {v['expected_value']:.4f}, alpha: {v['alpha']:.2f}, beta: {v['beta']:.2f}")

        if stats:
            top_arm = max(stats.keys(), key=lambda k: stats[k]['expected_value'])
            print(f"\nBEST ARM: {top_arm}")
        else:
            print("No arms found.")

    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
