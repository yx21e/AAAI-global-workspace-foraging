from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gwt_agent.core.types import EnvironmentState, ModuleInput, WorkspaceBroadcast
from gwt_agent.envs.foraging_adapter import ForagingEnvAdapter
from gwt_agent.llm.client import (
    MockLLMClient,
    parse_json_object,
    summarize_broadcast,
    summarize_history,
)
from gwt_agent.modules.llm_agents import LLMLanguageModule, LLMMotorModule, LLMPerceptionModule


class LLMAgentTest(unittest.TestCase):
    def test_parse_json_object_from_fenced_output(self):
        parsed = parse_json_object(
            '```json\n{"summary":"ok","observations":[],"confidence":0.5,"action_hint":null,"rationale":"done","reflection":"brief self-check"}\n```'
        )

        self.assertEqual(parsed["summary"], "ok")
        self.assertEqual(parsed["reflection"], "brief self-check")

    def test_mock_summary_helpers_do_not_truncate_view_text(self):
        long_summary = "full broadcast text " * 20
        broadcast_text = summarize_broadcast(
            {
                "winner_module": "perception",
                "content": {"summary": long_summary},
            }
        )
        history_text = summarize_history(
            [
                {
                    "mode": "broadcast_listening",
                    "heard_broadcast": long_summary,
                    "output_language": "full output text " * 20,
                }
            ]
        )

        self.assertIn(long_summary, broadcast_text)
        self.assertIn(long_summary, history_text)
        self.assertNotIn("...", broadcast_text)
        self.assertNotIn("...", history_text)

    def test_multimodal_perception_uses_screenshot_path(self):
        module = LLMPerceptionModule(client=MockLLMClient())
        module_input = ModuleInput(
            module_name="perception",
            env_t=0,
            cycle_t=0,
            private_observation={
                "global_screenshot": "/tmp/map.png",
                "global_map": [["BASE", "AGENT", "RESOURCE"]],
                "agent_position": (1, 0),
                "resource_position": (2, 0),
                "base_position": (0, 0),
                "wall_positions": [],
            },
            task_goal="collect one resource and return to base",
        )

        proposal = module.propose(module_input)

        self.assertEqual(proposal.module_name, "perception")
        self.assertIsNone(proposal.action_hint)
        self.assertIn("I see the agent", proposal.reflection)
        self.assertEqual(
            proposal.metadata["llm_agent"]["image_path"],
            "/tmp/map.png",
        )
        self.assertTrue(proposal.metadata["llm_agent"]["supports_images"])
        self.assertEqual(proposal.content["global_map"], [["BASE", "AGENT", "RESOURCE"]])
        self.assertEqual(proposal.content["base_position"], [0, 0])

    def test_perception_refreshes_targets_when_workspace_lacks_spatial_target(self):
        module = LLMPerceptionModule(client=MockLLMClient())
        module_input = ModuleInput(
            module_name="perception",
            env_t=0,
            cycle_t=1,
            private_observation={
                "global_screenshot": "/tmp/map.png",
                "global_map": [["BASE", "AGENT", "RESOURCE"]],
                "agent_position": (1, 0),
                "resource_position": (2, 0),
                "base_position": (0, 0),
                "wall_positions": [],
            },
            global_broadcast=WorkspaceBroadcast(
                timestamp=0,
                winner_module="motor",
                content={"summary": "Motor broadcast without global target coordinates."},
                importance_score=0.4,
                action_hint="RIGHT",
            ),
            task_goal="collect one resource and return to base",
        )

        proposal = module.propose(module_input)

        self.assertIn("Spatial target refresh", proposal.content["summary"])
        self.assertIn("spatial_target_refresh=needed", proposal.content["observations"])
        self.assertIsNone(proposal.action_hint)

    def test_motor_llm_can_emit_action_hint(self):
        module = LLMMotorModule(client=MockLLMClient())
        module_input = ModuleInput(
            module_name="motor",
            env_t=0,
            cycle_t=0,
            private_observation={
                "agent_position": (1, 1),
                "resource_position": (2, 1),
                "base_position": (1, 1),
                "carrying_resource": False,
                "nearby_obstacles": [],
                "blocked_directions": {
                    "UP": True,
                    "DOWN": False,
                    "LEFT": False,
                    "RIGHT": False,
                },
            },
            available_actions=["UP", "DOWN", "LEFT", "RIGHT", "PICKUP"],
            task_goal="collect one resource and return to base",
        )

        proposal = module.propose(module_input)

        self.assertEqual(proposal.module_name, "motor")
        self.assertIn(proposal.action_hint, {"RIGHT", "DOWN", "LEFT", "PICKUP", "NOOP"})
        self.assertIn("blocked directions", proposal.reflection)

    def test_motor_uses_broadcast_global_map_for_route_planning(self):
        module = LLMMotorModule(client=MockLLMClient())
        grid = [
            list("###############"),
            list("#.........B...#"),
            list("#..#..........#"),
            list("#..#.....##...#"),
            list("#.......#.....#"),
            list("#....#.....#..#"),
            list("#....#..#.....#"),
            list("#..#....#.....#"),
            list("#..##.........#"),
            list("#...........#.#"),
            list("#.....#.....#.#"),
            list("#.....#..#....#"),
            list("#.........##..#"),
            list("#.....#..A#...#"),
            list("###############"),
        ]
        global_map = [
            [
                {
                    "#": "WALL",
                    ".": "FLOOR",
                    "B": "BASE",
                    "A": "AGENT",
                }[cell]
                for cell in row
            ]
            for row in grid
        ]
        module_input = ModuleInput(
            module_name="motor",
            env_t=0,
            cycle_t=80,
            private_observation={
                "agent_position": (9, 13),
                "carrying_resource": True,
                "nearby_obstacles": [(10, 13), (9, 14)],
                "blocked_directions": {
                    "UP": False,
                    "DOWN": True,
                    "LEFT": False,
                    "RIGHT": True,
                },
            },
            global_broadcast=WorkspaceBroadcast(
                timestamp=79,
                winner_module="perception",
                content={
                    "summary": "Spatial target refresh.",
                    "global_map": global_map,
                    "agent_position": [9, 13],
                    "base_position": [10, 1],
                    "resource_position": None,
                },
                importance_score=0.4,
            ),
            available_actions=["UP", "DOWN", "LEFT", "RIGHT", "PICKUP"],
            task_goal="collect one resource and return to base",
        )

        proposal = module.propose(module_input)

        self.assertEqual(proposal.action_hint, "UP")
        self.assertIn("planning_source=broadcast_global_map", proposal.content["observations"])
        self.assertIn("broadcast global map", proposal.reflection)

    def test_language_llm_never_emits_simulator_action(self):
        module = LLMLanguageModule(client=MockLLMClient())
        module_input = ModuleInput(
            module_name="language",
            env_t=0,
            cycle_t=0,
            private_observation={
                "experimenter_instruction": "collect one resource",
                "report_query": "What is active now?",
            },
            available_actions=["UP", "DOWN", "LEFT", "RIGHT", "PICKUP"],
            task_goal="collect one resource",
        )

        proposal = module.propose(module_input)

        self.assertEqual(proposal.module_name, "language")
        self.assertIsNone(proposal.action_hint)
        self.assertIn("Experimenter query", proposal.content["summary"])
        self.assertIn("experimenter-facing", proposal.reflection)

    def test_language_pause_prompt_uses_history(self):
        module = LLMLanguageModule(client=MockLLMClient())
        first_input = ModuleInput(
            module_name="language",
            env_t=0,
            cycle_t=0,
            private_observation={
                "interaction_mode": "broadcast_listening",
                "pause_requested": False,
                "user_prompt": None,
                "report_query": None,
            },
            task_goal="collect one resource",
        )
        module.propose(first_input)
        pause_input = ModuleInput(
            module_name="language",
            env_t=0,
            cycle_t=1,
            private_observation={
                "interaction_mode": "user_pause",
                "pause_requested": True,
                "user_prompt": "What did you just hear?",
                "report_query": None,
            },
            task_goal="collect one resource",
        )

        proposal = module.propose(pause_input)

        self.assertIsNone(proposal.action_hint)
        self.assertIn("User pause prompt", proposal.content["summary"])
        self.assertIn("Recent language history", proposal.content["summary"])
        self.assertEqual(len(module.input_history), 2)


class ForagingScreenshotAttachTest(unittest.TestCase):
    def test_adapter_attaches_rendered_screenshot_to_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env = FakeRenderableEnv()
            adapter = ForagingEnvAdapter(env=env)
            state = EnvironmentState(
                timestamp=0,
                observation={},
                symbolic_state={},
                info={},
            )
            path = Path(temp_dir) / "frame.png"

            rendered = adapter.render_screenshot_to_state(state, str(path))

            self.assertEqual(rendered, str(path))
            self.assertEqual(state.symbolic_state["global_screenshot"], str(path))
            self.assertEqual(state.observation["global_screenshot"], str(path))
            self.assertTrue(path.exists())


class FakeRenderableEnv:
    def render(self, filename):
        Path(filename).write_bytes(b"png")
        return filename


if __name__ == "__main__":
    unittest.main()
