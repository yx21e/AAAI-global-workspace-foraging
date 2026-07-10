from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gwt_agent.envs.qiyuan_replay import (
    episode_grid_from_trace,
    render_trace_replay,
    restore_initial_env_from_trace,
)


class QiyuanReplayTest(unittest.TestCase):
    def test_trace_replay_uses_qiyuan_load_state_when_grid_available(self):
        env = FakeReplayEnv()
        grid = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
        records = [
            {
                "env_state": {
                    "observation": make_state(agent_pos=(1, 1), step_count=0),
                    "symbolic_state": {"agent_position": [9, 9]},
                    "info": {"qiyuan_episode_grid": grid},
                },
                "next_env_state": {
                    "observation": make_state(agent_pos=(1, 1), step_count=1),
                    "symbolic_state": {"agent_position": [8, 8]},
                    "info": {"qiyuan_episode_grid": grid},
                },
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            frames = render_trace_replay(
                env=env,
                envelope_records=records,
                render_dir=temp_dir,
            )

        self.assertEqual(len(frames), 2)
        self.assertEqual(episode_grid_from_trace(records), grid)
        self.assertEqual(len(env.loaded), 2)
        self.assertEqual(env.loaded[0][0]["step_count"], 0)
        self.assertEqual(env.loaded[1][0]["step_count"], 1)
        self.assertEqual(env.loaded[0][1], grid)

    def test_restore_initial_env_uses_load_state(self):
        env = FakeReplayEnv()
        grid = [[1, 1, 1], [1, 0, 1], [1, 1, 1]]
        records = [
            {
                "env_state": {
                    "observation": make_state(agent_pos=(1, 1), step_count=0),
                    "symbolic_state": {},
                    "info": {"qiyuan_episode_grid": grid},
                }
            }
        ]

        restored = restore_initial_env_from_trace(env, records)

        self.assertTrue(restored)
        self.assertEqual(len(env.loaded), 1)
        self.assertEqual(env.loaded[0][1], grid)


def make_state(agent_pos, step_count):
    return {
        "agent_pos": tuple(agent_pos),
        "facing": "RIGHT",
        "resource_pos": None,
        "base_pos": (1, 1),
        "carrying": False,
        "action_success": True,
        "step_count": step_count,
        "resources_collected": 0,
    }


class FakeReplayEnv:
    def __init__(self):
        self.loaded = []

    def load_state(self, state, grid):
        self.loaded.append((state, grid))

    def render(self, filename):
        Path(filename).write_bytes(b"")
        return filename


if __name__ == "__main__":
    unittest.main()
