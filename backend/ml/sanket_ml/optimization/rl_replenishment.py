from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gymnasium as gym
import numpy as np
import structlog
from gymnasium import spaces

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class InventoryEnvConfig:
    horizon: int = 26
    moq: int = 10
    lead_time: int = 2
    max_order_units: int = 500
    holding_cost: float = 0.05
    stockout_penalty: float = 5.0
    unit_cost: float = 10.0
    unit_price: float = 25.0
    initial_inventory: int = 100
    demand_mean: float = 30.0
    demand_std: float = 10.0
    seed: int = 0


class InventoryEnv(gym.Env):
    """Single-SKU stochastic inventory environment.

    Observation: (on_hand, in_transit_total, last_demand, week_index/H)
    Action:      integer in [0, max_order_units // moq] — multiples of MOQ to order
    Reward:      revenue from sales - holding - stockout - cogs
    """

    metadata = {"render_modes": []}

    def __init__(self, config: InventoryEnvConfig | None = None) -> None:
        super().__init__()
        self.cfg = config or InventoryEnvConfig()
        self.action_space = spaces.Discrete(self.cfg.max_order_units // self.cfg.moq + 1)
        self.observation_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([1e6, 1e6, 1e6, 1.0], dtype=np.float32),
            dtype=np.float32,
        )
        self._rng = np.random.default_rng(self.cfg.seed)
        self._step = 0
        self._on_hand = 0
        self._pipeline: list[int] = []
        self._last_demand = 0.0

    def reset(self, *, seed: int | None = None, options: dict | None = None) -> tuple[np.ndarray, dict]:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._step = 0
        self._on_hand = self.cfg.initial_inventory
        self._pipeline = [0] * self.cfg.lead_time
        self._last_demand = self.cfg.demand_mean
        return self._observe(), {}

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        order_units = int(action) * self.cfg.moq
        # Receive arriving order
        arrival = self._pipeline.pop(0)
        self._pipeline.append(order_units)
        self._on_hand += arrival

        # Realize demand
        demand = max(0.0, float(self._rng.normal(self.cfg.demand_mean, self.cfg.demand_std)))
        sold = min(self._on_hand, demand)
        shortage = max(0.0, demand - sold)
        self._on_hand -= int(round(sold))
        self._last_demand = demand

        revenue = sold * self.cfg.unit_price
        holding = self._on_hand * self.cfg.holding_cost
        stockout = shortage * self.cfg.stockout_penalty
        cogs = order_units * self.cfg.unit_cost
        reward = float(revenue - holding - stockout - cogs)

        self._step += 1
        terminated = self._step >= self.cfg.horizon
        truncated = False
        return self._observe(), reward, terminated, truncated, {
            "demand": demand, "sold": sold, "shortage": shortage,
        }

    def _observe(self) -> np.ndarray:
        return np.array(
            [
                self._on_hand,
                sum(self._pipeline),
                self._last_demand,
                self._step / self.cfg.horizon,
            ],
            dtype=np.float32,
        )


def train_rl_replenishment_policy(
    env_config: InventoryEnvConfig | None = None,
    *,
    iterations: int = 100,
    framework: str = "torch",
) -> Any:
    """Train PPO on InventoryEnv via Ray RLlib. Returns the trained Algorithm
    which exposes .compute_single_action(obs) for inference."""
    from ray.rllib.algorithms.ppo import PPOConfig

    gym.register(id="sanket/Inventory-v0", entry_point=lambda config=None: InventoryEnv(config))

    config = (
        PPOConfig()
        .environment(env="sanket/Inventory-v0", env_config=env_config or InventoryEnvConfig())
        .framework(framework)
        .resources(num_gpus=0)
        .rollouts(num_rollout_workers=2, rollout_fragment_length=200)
        .training(
            gamma=0.99,
            lr=3e-4,
            train_batch_size=2000,
            sgd_minibatch_size=128,
            num_sgd_iter=10,
        )
    )
    algo = config.build()
    for it in range(iterations):
        result = algo.train()
        if it % 10 == 0:
            log.info(
                "rl.replen.iter",
                iter=it,
                episode_reward_mean=result.get("episode_reward_mean"),
            )
    return algo
