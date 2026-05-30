# mab_engine_v2.py: 톰슨 샘플링(Bandit) 알고리즘을 통해 어떤 카피 전략이 가장 유망한지 결정하는 핵심 의사결정 엔진.
import numpy as np
from datetime import datetime

class DynamicMAB:
    def __init__(self, gamma=0.9):
        """
        gamma: decay factor (usually 0.9 - 0.95). 
        """
        self.gamma = gamma
        self.arms = {} # arm_name (cluster): {'alpha', 'beta', 'metadata'}
        self.last_update_time = datetime.now()
        self.context_weights = {} # cluster: weight

    def add_arm(self, arm_name, metadata=None):
        if arm_name not in self.arms:
            self.arms[arm_name] = {
                'alpha': 1.0, 
                'beta': 1.0, 
                'metadata': metadata or {}
            }

    def decay(self):
        """Manually trigger decay for all arms."""
        for a in self.arms:
            self.arms[a]['alpha'] = 1.0 + (float(self.arms[a]['alpha']) - 1.0) * self.gamma
            self.arms[a]['beta'] = 1.0 + (float(self.arms[a]['beta']) - 1.0) * self.gamma

    def update(self, arm_name, reward, timestamp=None, is_user_data=True, apply_decay=False):
        """
        reward: MSS score
        is_user_data: If True, higher weight.
        apply_decay: If True, apply decay before updating (standard MAB). 
                     If False, useful for batch/daily updates where decay is manual.
        """
        if arm_name not in self.arms:
            self.add_arm(arm_name)
        
        if apply_decay:
            self.decay()

        # Scale reward
        # User: 1.5, External: 0.5 -> 3:1 Ratio
        weight_multiplier = 1.5 if is_user_data else 0.5
        scaled_reward = float(min(reward / 500.0, 5.0) * weight_multiplier)
        
        self.arms[arm_name]['alpha'] = float(self.arms[arm_name]['alpha']) + scaled_reward
        self.arms[arm_name]['beta'] = float(self.arms[arm_name]['beta']) + max(0.1, (weight_multiplier * 1.0) - (scaled_reward / 5.0))

    def select_arm(self, context_weights=None):
        if not self.arms:
            return None
        
        samples = {}
        for arm_name, stats in self.arms.items():
            # Thompson Sampling
            sample = np.random.beta(stats['alpha'], stats['beta'])
            
            # Apply contextual weight if provided
            if context_weights and arm_name in context_weights:
                sample *= context_weights[arm_name]
            
            samples[arm_name] = sample
        
        if not samples:
            return None
        
        # Select key with max value (using lambda for better lint compatibility)
        return max(samples.keys(), key=lambda k: samples[k])

    def get_arm_metadata(self, arm_name):
        return self.arms.get(arm_name, {}).get('metadata', {})

    def get_stats(self):
        return {
            name: {
                "expected_value": s['alpha'] / (s['alpha'] + s['beta']),
                "alpha": s['alpha'],
                "beta": s['beta']
            } for name, s in self.arms.items()
        }

if __name__ == "__main__":
    mab = DynamicMAB()
    mab.add_arm("Emotional Hook", {"prompt_hint": "Use strong emotions"})
    mab.update("Emotional Hook", 500) # High MSS
    print(mab.get_stats())
    print(f"Selected: {mab.select_arm()}")
