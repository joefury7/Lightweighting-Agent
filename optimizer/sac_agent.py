"""
Soft Actor-Critic (SAC) Reinforcement Learning Agent for Continuous Mirror Optimization (Objective 3)
Off-policy maximum entropy actor-critic with twin Q-networks for robust multi-objective exploration.
"""

import os
import sys
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


class SACActor(nn.Module):
    def __init__(self, state_dim=15, action_dim=5, hidden_dim=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU()
        )
        self.mean = nn.Linear(hidden_dim, action_dim)
        self.log_std = nn.Linear(hidden_dim, action_dim)

    def forward(self, state):
        feat = self.net(state)
        mean = self.mean(feat)
        log_std = torch.clamp(self.log_std(feat), -20.0, 2.0)
        return mean, log_std

    def sample(self, state):
        mean, log_std = self(state)
        std = log_std.exp()
        normal = Normal(mean, std)
        x_t = normal.rsample()
        action = torch.tanh(x_t)
        log_prob = normal.log_prob(x_t) - torch.log(1.0 - action.pow(2) + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)
        return action, log_prob, torch.tanh(mean)


class SACCritic(nn.Module):
    def __init__(self, state_dim=15, action_dim=5, hidden_dim=128):
        super().__init__()
        # Q1 Architecture
        self.q1 = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, 1)
        )
        # Q2 Architecture (Twin Critic)
        self.q2 = nn.Sequential(
            nn.Linear(state_dim + action_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.SiLU(),
            nn.Linear(hidden_dim, 1)
        )

    def forward(self, state, action):
        sa = torch.cat([state, action], dim=-1)
        return self.q1(sa), self.q2(sa)


class SACAgent:
    def __init__(self, state_dim=15, action_dim=5, lr=3e-4, gamma=0.99, tau=0.005, alpha=0.2):
        self.gamma = gamma
        self.tau = tau
        self.alpha = alpha

        self.actor = SACActor(state_dim, action_dim)
        self.critic = SACCritic(state_dim, action_dim)
        self.critic_target = SACCritic(state_dim, action_dim)
        self.critic_target.load_state_dict(self.critic.state_dict())

        self.actor_opt = optim.Adam(self.actor.parameters(), lr=lr)
        self.critic_opt = optim.Adam(self.critic.parameters(), lr=lr)

    def get_action(self, state, evaluate=False):
        with torch.no_grad():
            s_t = torch.tensor(state, dtype=torch.float32).unsqueeze(0)
            if evaluate:
                _, _, action = self.actor.sample(s_t)
            else:
                action, _, _ = self.actor.sample(s_t)
            return action.squeeze(0).numpy()

    def optimize_design(self, env, steps=30):
        obs = env.reset()
        best_design = None
        best_r = -1e9
        for _ in range(steps):
            act = self.get_action(obs, evaluate=True)
            obs, r, done, info = env.step(act)
            if r > best_r:
                best_r = r
                best_design = info
            if done:
                break
        return best_design


if __name__ == "__main__":
    print("Testing SAC Agent Initialization...")
    sac = SACAgent()
    env = OptoMechanicalMirrorEnv(material="sic")
    best = sac.optimize_design(env, steps=10)
    print(f"SAC Quick Test (SiC) -> Mass: {best['mass_kg']} kg | Sag: {best['rms_sag_nm']} nm | f1: {best['frequency_hz']} Hz")
