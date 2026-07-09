from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from gwt_agent.core.types import EnvironmentState, ModuleInput
from gwt_agent.envs.foraging_adapter import ForagingEnvAdapter
from gwt_agent.llm.client import MockLLMClient
from gwt_agent.modules.llm_agents import LLMLanguageModule, LLMMotorModule, LLMPerceptionModule


class LLMAgentTest(unittest.TestCase):
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
        self.assertEqual(
            proposal.metadata["llm_agent"]["image_path"],
            "/tmp/map.png",
        )
        self.assertTrue(proposal.metadata["llm_agent"]["supports_images"])

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
