import unittest

from gwt_agent.envs.foraging_adapter import ForagingEnvAdapter
from gwt_agent.envs.map_variants import (
    DIFFICULTY2_FIVE,
    difficulty2_variants,
    resolve_map_variant,
)


class MapVariantTest(unittest.TestCase):
    def test_difficulty2_has_five_connected_variants(self):
        variants = difficulty2_variants()

        self.assertEqual(len(variants), 5)
        self.assertGreaterEqual(len({variant.base_pos for variant in variants}), 3)
        self.assertGreaterEqual(len({variant.resource_pos for variant in variants}), 3)
        self.assertGreaterEqual(len({variant.obstacle_count for variant in variants}), 2)
        for variant in variants:
            self.assertEqual(len(variant.grid), 15)
            self.assertEqual({len(row) for row in variant.grid}, {15})
            self.assertGreaterEqual(variant.obstacle_count, 12)
            self.assertLessEqual(variant.obstacle_count, 28)

    def test_auto_resolves_difficulty2_by_seed_modulo_five(self):
        variant = resolve_map_variant(
            preset="auto",
            difficulty=2,
            variant="auto",
            seed=7,
        )

        self.assertIsNotNone(variant)
        self.assertEqual(variant.variant_id, 2)

    def test_auto_keeps_non_difficulty2_on_qiyuan_default(self):
        variant = resolve_map_variant(
            preset="auto",
            difficulty=1,
            variant="auto",
            seed=7,
        )

        self.assertIsNone(variant)

    def test_adapter_applies_selected_variant_to_env_state(self):
        env = FakeVariantEnv()
        adapter = ForagingEnvAdapter(
            env=env,
            difficulty=2,
            map_preset=DIFFICULTY2_FIVE,
            map_variant=3,
            map_variant_seed=7,
        )

        state = adapter.reset()
        variant = difficulty2_variants()[3]

        self.assertEqual(state.symbolic_state["base_position"], variant.base_pos)
        self.assertEqual(state.symbolic_state["resource_position"], tuple(variant.resource_pos))
        self.assertEqual(env.base_pos, variant.base_pos)
        self.assertEqual(env.resource_pos, list(variant.resource_pos))
        self.assertEqual(adapter.episode_grid, variant.grid)
        self.assertEqual(adapter.map_variant_metadata["variant"], 3)
        self.assertEqual(state.info["map_variant"]["name"], variant.name)


class FakeVariantEnv:
    def __init__(self):
        self.grid_size = 15
        self.grid = [[0] * self.grid_size for _ in range(self.grid_size)]
        self.base_pos = (1, 1)
        self.agent_pos = [1, 1]
        self.facing = "RIGHT"
        self.resource_pos = [2, 1]
        self.carrying = False
        self.step_count = 0
        self.resources_collected = 0
        self.local_view_radius = None

    def reset(self, difficulty=1, local_view_radius=None):
        self.local_view_radius = local_view_radius
        return self._state()

    def get_grid(self):
        return [row[:] for row in self.grid]

    def _state(self):
        return {
            "agent_pos": tuple(self.agent_pos),
            "facing": self.facing,
            "resource_pos": tuple(self.resource_pos) if self.resource_pos else None,
            "base_pos": self.base_pos,
            "carrying": self.carrying,
            "action_success": True,
            "step_count": self.step_count,
            "resources_collected": self.resources_collected,
        }


if __name__ == "__main__":
    unittest.main()
