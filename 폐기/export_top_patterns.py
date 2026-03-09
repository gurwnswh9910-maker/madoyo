import sys
import io
import json
import os

# Setup UTF-8 for Windows terminal
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.detach(), encoding='utf-8')

base_path = r'c:\Users\ding9\Desktop\madoyo'
src_path = os.path.join(base_path, '작동중코드')
sys.path.append(src_path)

from data_feedback_loop_v2 import MSSDataIntegrator

def main():
    integrator = MSSDataIntegrator(base_path)
    class DummyMAB:
        def update_reward(self, i, r): pass
    
    data = integrator.process_all_data(DummyMAB())
    top_examples = integrator.get_top_performing_patterns(data, top_n=10)
    
    print(json.dumps(top_examples, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
