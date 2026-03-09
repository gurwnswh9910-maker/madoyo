import numpy as np
from datetime import datetime, timedelta

class RecencyWeightedMAB:
    def __init__(self, arms, gamma=0.95):
        """
        arms: list of arm names (e.g., ['Hook_Authority', 'Hook_Reaction', ...])
        gamma: decay factor (0 < gamma <= 1). 
               Lower means faster decay (more focus on recent data).
        """
        self.arms = arms
        self.gamma = gamma
        # stats for Thompson Sampling: alpha (successes), beta (failures)
        self.alphas = {arm: 1.0 for arm in arms}
        self.betas = {arm: 1.0 for arm in arms}
        self.last_update_time = datetime.now()

    def update(self, arm, reward, timestamp=None):
        """
        reward: continuous reward (e.g., weighted engagement) or binary (0 or 1)
        timestamp: when the reward occurred. If None, uses current time.
        """
        if arm not in self.arms:
            return

        now = timestamp if timestamp else datetime.now()
        
        # Apply decay to all existing stats based on time passed
        # In a real app, you'd apply decay globally or store timestamps per reward
        # Here we use a simpler approach: decay existing knowledge before adding new
        # This approximates exponential moving average of the bandit parameters
        
        # Scaling the existing alpha/beta towards 1.0 (the prior)
        for a in self.arms:
            self.alphas[a] = 1.0 + (self.alphas[a] - 1.0) * self.gamma
            self.betas[a] = 1.0 + (self.betas[a] - 1.0) * self.gamma

        # Update specific arm
        # We assume reward is scaled [0, 1] for simpler beta distribution update
        # If reward is large (engagement count), it should be normalized or 
        # the update logic adjusted.
        self.alphas[arm] += reward
        self.betas[arm] += (1.0 - reward)

    def select_arm(self):
        """Selects an arm using Thompson Sampling."""
        samples = {
            arm: np.random.beta(self.alphas[arm], self.betas[arm])
            for arm in self.arms
        }
        return max(samples, key=samples.get)

    def get_stats(self):
        return {
            arm: {"alpha": self.alphas[arm], "beta": self.betas[arm], "expected_value": self.alphas[arm] / (self.alphas[arm] + self.betas[arm])}
            for arm in self.arms
        }

# Example Usage
if __name__ == "__main__":
    mab = RecencyWeightedMAB(['Authority', 'Reaction', 'Sharing', 'Emotion'])
    
    # Simulate some rewards
    mab.update('Authority', 0.8)
    mab.update('Reaction', 0.2)
    
    print("Initial Stats:", mab.get_stats())
    selected = mab.select_arm()
    print(f"Selected Arm: {selected}")
