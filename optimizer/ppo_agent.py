"""
Reinforcement Learning PPO (Proximal Policy Optimization) Agent (Objective 3)
Learns optimal optomechanical lightweighting policies balancing mass, optical figure, and launch stiffness
across Zerodur, Silicon Carbide (SiC), ULE, and Beryllium.
"""

import os
import sys
import time
import json
import math
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.distributions import Normal

# Ensure workspace root is in sys.path
workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from optimizer.rl_environment import OptoMechanicalMirrorEnv


class ActorCritic(nn.Module):
    """
    Continuous Action Gaussian Actor-Critic Network.
    State Dim: 15, Action Dim: 5
    """
    def __init__(self, state_dim=15, action_dim=5, hidden_dim=128):
        super().__init__()
        # Shared Feature Backbone
        self.actor_base = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh()
        )
        self.actor_mean = nn.Linear(hidden_dim, action_dim)
        self.actor_log_std = nn.Parameter(torch.full((action_dim,), -0.5, dtype=torch.float32))

        self.critic = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(self, state):
        feat = self.actor_base(state)
        mean = torch.tanh(self.actor_mean(feat))
        std = torch.exp(torch.clamp(self.actor_log_std, -2.0, 1.0))
        dist = Normal(mean, std)
        val = self.critic(state)
        return dist, val

    def get_action(self, state, deterministic=False):
        with torch.no_grad():
            s_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
            dist, val = self(s_t)
            if deterministic:
                action = dist.mean.squeeze(0).numpy()
            else:
                action = dist.sample().squeeze(0).numpy()
            action = np.clip(action, -1.0, 1.0)
            log_prob = dist.log_prob(torch.tensor(action, dtype=torch.float32)).sum().item()
            return action, log_prob, val.item()


class PPOAgent:
    """
    Proximal Policy Optimization (PPO-Clip) Agent with GAE.
    """
    def __init__(self, state_dim=15, action_dim=5, lr=3e-4, gamma=0.99, gae_lambda=0.95,
                 clip_eps=0.2, c_val=0.5, c_ent=0.01):
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_eps = clip_eps
        self.c_val = c_val
        self.c_ent = c_ent

        self.policy = ActorCritic(state_dim, action_dim, hidden_dim=128)
        self.optimizer = optim.Adam(self.policy.parameters(), lr=lr)

    def compute_gae(self, rewards, values, dones, next_val):
        advantages = []
        gae = 0.0
        vals = values + [next_val]
        for t in reversed(range(len(rewards))):
            delta = rewards[t] + self.gamma * vals[t + 1] * (1.0 - float(dones[t])) - vals[t]
            gae = delta + self.gamma * self.gae_lambda * (1.0 - float(dones[t])) * gae
            advantages.insert(0, gae)
        returns = [adv + v for adv, v in zip(advantages, values)]
        return advantages, returns

    def train_step(self, states, actions, old_log_probs, returns, advantages, ppo_epochs=4, batch_size=32):
        states_t = torch.tensor(np.array(states), dtype=torch.float32)
        actions_t = torch.tensor(np.array(actions), dtype=torch.float32)
        old_log_probs_t = torch.tensor(np.array(old_log_probs), dtype=torch.float32)
        returns_t = torch.tensor(np.array(returns), dtype=torch.float32)
        adv_t = torch.tensor(np.array(advantages), dtype=torch.float32)

        # Normalize advantages
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

        dataset_size = len(states)
        for _ in range(ppo_epochs):
            indices = np.random.permutation(dataset_size)
            for start in range(0, dataset_size, batch_size):
                end = start + batch_size
                b_idx = indices[start:end]

                dist, val = self.policy(states_t[b_idx])
                new_log_probs = dist.log_prob(actions_t[b_idx]).sum(dim=1)
                entropy = dist.entropy().sum(dim=1).mean()

                ratio = torch.exp(new_log_probs - old_log_probs_t[b_idx])
                surr1 = ratio * adv_t[b_idx]
                surr2 = torch.clamp(ratio, 1.0 - self.clip_eps, 1.0 + self.clip_eps) * adv_t[b_idx]

                actor_loss = -torch.min(surr1, surr2).mean()
                val_loss = nn.functional.mse_loss(val.squeeze(1), returns_t[b_idx])

                loss = actor_loss + (self.c_val * val_loss) - (self.c_ent * entropy)

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=0.5)
                self.optimizer.step()

    def train_environment(self, env, total_timesteps=4000, rollout_len=200):

        obs = env.reset()
        timesteps = 0
        episodes = 0
        best_reward = -1e9
        best_info = None

        while timesteps < total_timesteps:
            states, actions, log_probs, rewards, values, dones = [], [], [], [], [], []

            for _ in range(rollout_len):
                act, lp, val = self.policy.get_action(obs, deterministic=False)
                next_obs, r, done, info = env.step(act)

                states.append(obs)
                actions.append(act)
                log_probs.append(lp)
                rewards.append(r)
                values.append(val)
                dones.append(done)

                timesteps += 1
                obs = next_obs

                if r > best_reward:
                    best_reward = r
                    best_info = info

                if done:
                    obs = env.reset()
                    episodes += 1

            _, _, next_val = self.policy.get_action(obs, deterministic=True)
            advs, rets = self.compute_gae(rewards, values, dones, next_val)
            self.train_step(states, actions, log_probs, rets, advs)


        return best_info

    def optimize_design(self, env, max_steps=40):
        """
        Executes deterministic PPO policy to find the optimum mirror design.
        """
        obs = env.reset()
        best_design = None
        best_score = -1e9

        for step in range(max_steps):
            act, _, _ = self.policy.get_action(obs, deterministic=True)
            obs, r, done, info = env.step(act)
            if r > best_score:
                best_score = r
                best_design = info
            if done:
                break

        return best_design

    def refine_design(self, env, max_steps=35, initial_geom=None):
        """
        Local refinement from an NSGA-II seed: deterministic policy steps, keeping the best design
        under the SAME objective NSGA-II uses (env.score).  The seed is returned unchanged if the
        policy does not improve it, and 'improved' reports that honestly.
        """
        obs = env.reset(initial_geom=initial_geom)
        def snap(info_like):
            d = dict(info_like)
            for k, v in zip(["H_mm", "tf_mm", "tw_mm", "L_mm", "rf_mm"], env.geom):
                d[k] = float(v)
            return d
        seed_info = snap(env.last_preds)
        best, best_score = dict(seed_info), env.score(env.last_preds)
        initial = best_score
        steps = 0
        for _ in range(max_steps):
            act, _, _ = self.policy.get_action(obs, deterministic=True)
            obs, r, done, info = env.step(act)
            steps += 1
            if info["score"] < best_score - 1e-9:
                best_score, best = info["score"], dict(info)
            if done:
                break
        return {"seed_design": seed_info, "refined_design": best, "trajectory_steps": steps + 1,
                "improved": bool(best_score < initial - 1e-9),
                "initial_score": round(initial, 4), "final_score": round(best_score, 4)}


def evaluate_policy_vs_random(agent, n_episodes=20, steps=30, seed=0):
    """Honest check: mean improvement of the shared objective (env.score) achieved by the
    deterministic policy vs. uniformly random actions, from identical random start designs."""
    rng = np.random.default_rng(seed)
    res = {"ppo": [], "random": []}
    for ep in range(n_episodes):
        mat = ["zerodur", "sic", "ule", "beryllium"][ep % 4]
        target = float(rng.uniform(9, 16))
        for kind in ("ppo", "random"):
            env = OptoMechanicalMirrorEnv(material=mat, target_mass_kg=target, seed=1000 + ep, max_steps=steps)
            obs = env.reset()
            s0 = best = env.score(env.last_preds)
            for _ in range(steps):
                a = agent.policy.get_action(obs, deterministic=True)[0] if kind == "ppo" else rng.uniform(-1, 1, 5)
                obs, r, done, info = env.step(a)
                best = min(best, info["score"])
            res[kind].append(s0 - best)
    return {k: float(np.mean(v)) for k, v in res.items()}


def train_and_save_ppo_policies(models_dir="optimizer/models", total_timesteps=24000, rollout_len=240):
    os.makedirs(models_dir, exist_ok=True)
    agent = PPOAgent()
    before = evaluate_policy_vs_random(agent)
    rng = np.random.default_rng(0)
    steps = 0
    while steps < total_timesteps:
        mat = ["zerodur", "sic", "ule", "beryllium"][(steps // rollout_len) % 4]
        env = OptoMechanicalMirrorEnv(material=mat, target_mass_kg=float(rng.uniform(9, 16)),
                                      seed=int(rng.integers(1e9)), max_steps=30)
        agent.train_environment(env, total_timesteps=rollout_len, rollout_len=rollout_len)
        steps += rollout_len
    after = evaluate_policy_vs_random(agent)
    path = os.path.join(models_dir, "ppo_mirror_policy.pt")
    torch.save(agent.policy.state_dict(), path)
    report = {"timesteps": total_timesteps, "mean_objective_improvement_untrained_vs_random": before,
              "mean_objective_improvement_trained_vs_random": after,
              "trained_at": time.strftime("%Y-%m-%d %H:%M:%S"),
              "environment": "exact mass + FEA-trained GP sag surrogate"}
    with open(os.path.join(models_dir, "ppo_training_report.json"), "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    train_and_save_ppo_policies()
