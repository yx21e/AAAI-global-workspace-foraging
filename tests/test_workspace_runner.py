from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gwt_agent.core.action import ActionResolver
from gwt_agent.core.export import trace_step_to_envelope, write_action_stream
from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.router import InputRouter
from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.core.types import EnvironmentState, ModuleProposal, WorkspaceBroadcast
from gwt_agent.core.workspace import CentralWorkspace
from gwt_agent.envs.foraging_adapter import ForagingEnvAdapter
from gwt_agent.envs.mock_env import MockGridAdapter
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.motor import MotorModule, extract_positions_from_broadcast
from gwt_agent.modules.perception import PerceptionModule


def make_modules():
    return [
        PerceptionModule(),
        MotorModule(),
        LanguageReportModule(),
    ]


class WorkspaceRunnerTest(unittest.TestCase):
    def test_runner_produces_trace_and_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            trace_path = Path(temp_dir) / "trace.jsonl"
            runner = WorkspaceRunner(
                env_adapter=MockGridAdapter(),
                modules=make_modules(),
                logger=TraceLogger(str(trace_path)),
            )

            traces = runner.run(num_steps=3)

            self.assertEqual(len(traces), 3)
            self.assertIn(
                traces[0].broadcast.winner_module,
                {"perception", "motor", "language_report"},
            )
            self.assertIn(
                traces[0].env_action.command,
                {"UP", "DOWN", "LEFT", "RIGHT", "PICKUP", None},
            )
            lines = trace_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 3)
            record = json.loads(lines[0])
            self.assertIn("proposals", record)
            self.assertIn("broadcast", record)
            self.assertIn("selected_action", record)
            self.assertIn("env_action", record)
            self.assertIn("module_states", record)
            self.assertIn("importance_function", record["proposals"][0]["metadata"])

    def test_disabled_module_is_not_logged(self):
        runner = WorkspaceRunner(
            env_adapter=MockGridAdapter(),
            modules=make_modules(),
            experiment=ExperimentConfig(disabled_modules=["perception"]),
        )

        trace = runner.step()

        proposal_names = {proposal.module_name for proposal in trace.proposals}
        module_statuses = {state.module_name: state.status for state in trace.module_states}
        self.assertNotIn("perception", proposal_names)
        self.assertEqual(module_statuses["perception"], "disabled")

    def test_workspace_does_not_force_alternating_winners(self):
        workspace = CentralWorkspace(ignition_threshold=0.1)
        winners = []

        for timestamp in range(2):
            proposals = [
                ModuleProposal(
                    module_name="perception",
                    content={"summary": "visual update"},
                    importance_score=0.3,
                    uptake_score=0.3,
                ),
                ModuleProposal(
                    module_name="motor",
                    content={"summary": "motor update"},
                    importance_score=0.8,
                    uptake_score=0.8,
                    action_hint="RIGHT",
                ),
            ]
            winner = workspace.select_winner(proposals)
            broadcast = workspace.broadcast(timestamp, winner)
            winners.append(broadcast.winner_module)

        self.assertEqual(winners, ["motor", "motor"])

    def test_motor_broadcast_does_not_carry_spatial_targets_forward(self):
        workspace = CentralWorkspace(ignition_threshold=0.1)
        proposal = ModuleProposal(
            module_name="motor",
            content={
                "summary": "Motor proposes LEFT; target=(1, 9); cue_source=workspace_broadcast.",
                "goal": "collect_resource",
                "resource_position": (1, 9),
                "base_position": (1, 1),
                "target_position": (1, 9),
                "observations": [
                    "agent_position=(2, 4)",
                    "resource_position=(1, 9)",
                    "base_position=(1, 1)",
                    "target_position=(1, 9)",
                    "target_source=workspace_broadcast",
                    "blocked_directions={'LEFT': False}",
                ],
            },
            importance_score=0.8,
            uptake_score=0.8,
            action_hint="LEFT",
            rationale="Use target_position=(1, 9) from the prior broadcast.",
            reflection="I am using the broadcast target (1, 9) and base (1, 1).",
        )

        broadcast = workspace.broadcast(0, proposal)

        extracted = extract_positions_from_broadcast(broadcast)
        self.assertNotIn("resource_position", extracted)
        self.assertNotIn("base_position", extracted)
        self.assertNotIn("target_position", extracted)
        self.assertNotIn("resource_position", broadcast.content)
        self.assertNotIn("base_position", broadcast.content)
        self.assertNotIn("target_position", broadcast.content)
        self.assertNotIn("resource_position=", "\n".join(broadcast.content["observations"]))
        self.assertNotIn("base_position=", "\n".join(broadcast.content["observations"]))
        self.assertNotIn("target_position=", "\n".join(broadcast.content["observations"]))
        self.assertIn("spatial_target_redaction", broadcast.metadata)
        self.assertIn("<redacted>", broadcast.metadata["winner_reflection"])

    def test_motor_action_hint_is_transient_not_workspace_memory(self):
        workspace = CentralWorkspace(ignition_threshold=0.1)
        proposal = ModuleProposal(
            module_name="motor",
            content={
                "summary": "Motor proposes LEFT; target=(1, 9); cue_source=workspace_broadcast.",
                "planned_action": "LEFT",
                "target_position": (1, 9),
                "observations": [
                    "planned_action=LEFT",
                    "target_position=(1, 9)",
                    "blocked_directions={'LEFT': False}",
                ],
            },
            importance_score=0.8,
            uptake_score=0.8,
            action_hint="LEFT",
            rationale="Choose the proposed action LEFT.",
            reflection="I chose LEFT because the broadcast target is (1, 9).",
        )

        broadcast = workspace.broadcast(0, proposal)
        memory = workspace.state.active_content

        self.assertEqual(broadcast.action_hint, "LEFT")
        self.assertIsNotNone(memory)
        self.assertIsNone(memory.action_hint)
        self.assertNotIn("planned_action", memory.content)
        self.assertNotIn("target_position", memory.content)
        self.assertNotIn("Motor proposes LEFT", memory.content["summary"])
        self.assertNotIn("planned_action=LEFT", "\n".join(memory.content["observations"]))
        self.assertIn("transient_action_redaction", memory.metadata)

    def test_motor_noop_is_not_globally_uploadable(self):
        workspace = CentralWorkspace(ignition_threshold=0.1)
        proposals = [
            ModuleProposal(
                module_name="motor",
                content={"summary": "No target; motor holds position."},
                importance_score=0.9,
                uptake_score=0.9,
                action_hint="NOOP",
            ),
            ModuleProposal(
                module_name="perception",
                content={"summary": "Visual target refresh."},
                importance_score=0.2,
                uptake_score=0.2,
            ),
        ]

        winner = workspace.select_winner(proposals)

        self.assertIsNotNone(winner)
        self.assertEqual(winner.module_name, "perception")

    def test_idle_language_is_not_globally_uploadable(self):
        workspace = CentralWorkspace(ignition_threshold=0.1)
        proposals = [
            ModuleProposal(
                module_name="language",
                content={"summary": "No report requested."},
                importance_score=0.9,
                uptake_score=0.9,
            ),
            ModuleProposal(
                module_name="perception",
                content={"summary": "Visual target refresh."},
                importance_score=0.2,
                uptake_score=0.2,
            ),
        ]

        winner = workspace.select_winner(proposals)

        self.assertIsNotNone(winner)
        self.assertEqual(winner.module_name, "perception")

    def test_report_language_can_be_globally_uploadable(self):
        workspace = CentralWorkspace(ignition_threshold=0.1)
        proposals = [
            ModuleProposal(
                module_name="language",
                content={"summary": "Answering experimenter.", "report_requested": True},
                importance_score=0.9,
                uptake_score=0.9,
            ),
            ModuleProposal(
                module_name="perception",
                content={"summary": "Visual target refresh."},
                importance_score=0.2,
                uptake_score=0.2,
            ),
        ]

        winner = workspace.select_winner(proposals)

        self.assertIsNotNone(winner)
        self.assertEqual(winner.module_name, "language")

    def test_action_stream_export(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            action_path = Path(temp_dir) / "actions.jsonl"
            runner = WorkspaceRunner(
                env_adapter=MockGridAdapter(),
                modules=make_modules(),
                run_id="test-run",
            )
            traces = runner.run(num_steps=2)
            envelopes = [
                trace_step_to_envelope(trace, run_id=runner.run_id)
                for trace in traces
            ]

            write_action_stream(str(action_path), envelopes)

            records = [
                json.loads(line)
                for line in action_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["run_id"], "test-run")
            self.assertIn("should_step", records[0])
            self.assertIn("action", records[0])
            self.assertEqual(records[0]["action"], envelopes[0].env_action.command)
            self.assertEqual(records[0]["should_step"], envelopes[0].env_action.should_step)

    def test_motor_threshold_route_does_not_execute_noop_without_target(self):
        resolver = ActionResolver(
            ExperimentConfig(
                allow_non_workspace_motor_action=True,
                motor_execution_threshold=0.02,
            )
        )
        broadcast = WorkspaceBroadcast(
            timestamp=0,
            winner_module="perception",
            content={"summary": "Visual content won, but it gives no action."},
            importance_score=0.5,
            action_hint=None,
        )
        proposals = [
            ModuleProposal(
                module_name="perception",
                content={"summary": "Visual content won, but it gives no action."},
                importance_score=0.5,
                action_hint=None,
            ),
            ModuleProposal(
                module_name="motor",
                content={"summary": "No target; motor holds position."},
                importance_score=0.9,
                uptake_score=0.9,
                confidence=0.7,
                action_hint="NOOP",
            ),
        ]

        action = resolver.resolve(broadcast, proposals)

        self.assertFalse(action.should_step)
        self.assertIsNone(action.command)
        self.assertEqual(action.metadata.get("action_route"), "no_action_threshold_not_met")

    def test_motor_threshold_route_can_execute_real_motor_action(self):
        resolver = ActionResolver(
            ExperimentConfig(
                allow_non_workspace_motor_action=True,
                motor_execution_threshold=0.02,
            )
        )
        broadcast = WorkspaceBroadcast(
            timestamp=0,
            winner_module="language",
            content={"summary": "Language won; no simulator action."},
            importance_score=0.5,
            action_hint=None,
        )
        proposals = [
            ModuleProposal(
                module_name="language",
                content={"summary": "Language won; no simulator action."},
                importance_score=0.5,
                action_hint=None,
            ),
            ModuleProposal(
                module_name="motor",
                content={"summary": "Local reflex proposes RIGHT."},
                importance_score=0.4,
                uptake_score=0.4,
                confidence=0.7,
                action_hint="RIGHT",
            ),
        ]

        action = resolver.resolve(broadcast, proposals)

        self.assertTrue(action.should_step)
        self.assertEqual(action.command, "RIGHT")
        self.assertEqual(
            action.metadata.get("action_route"),
            "non_workspace_motor_threshold",
        )

    def test_maintained_motor_broadcast_does_not_reexecute_old_action(self):
        resolver = ActionResolver(ExperimentConfig())
        maintained_broadcast = WorkspaceBroadcast(
            timestamp=5,
            winner_module="motor",
            content={"summary": "Old motor content is still maintained."},
            importance_score=0.4,
            action_hint="DOWN",
            metadata={
                "workspace": {
                    "ignited": False,
                    "maintained": True,
                    "strength": 0.85,
                }
            },
        )

        action = resolver.resolve(maintained_broadcast, proposals=[])

        self.assertFalse(action.should_step)
        self.assertIsNone(action.command)
        self.assertEqual(action.metadata.get("action_route"), "no_workspace_action")

    def test_default_no_action_when_workspace_winner_has_no_action(self):
        runner = WorkspaceRunner(
            env_adapter=MockGridAdapter(),
            modules=make_modules(),
            experiment=ExperimentConfig(
                score_modifiers={"perception": 10.0},
            ),
        )

        trace = runner.step()

        self.assertEqual(trace.broadcast.winner_module, "perception")
        self.assertFalse(trace.env_action.should_step)
        self.assertIsNone(trace.env_action.command)
        self.assertEqual(
            trace.env_action.metadata.get("action_route"),
            "no_workspace_action",
        )

    def test_module_private_channels_stay_separate_from_broadcast(self):
        runner = WorkspaceRunner(
            env_adapter=MockGridAdapter(),
            modules=make_modules(),
        )

        trace = runner.step()
        module_inputs = {
            state.module_name: state.module_input
            for state in trace.module_states
        }

        self.assertNotIn(
            "local_view",
            module_inputs["perception"].private_observation,
        )
        self.assertNotIn(
            "last_broadcast",
            module_inputs["language_report"].private_observation,
        )
        self.assertNotIn(
            "resource_position",
            module_inputs["motor"].private_observation,
        )
        self.assertNotIn(
            "base_position",
            module_inputs["motor"].private_observation,
        )
        self.assertIsNone(module_inputs["language_report"].global_broadcast)

    def test_no_ignition_placeholder_is_not_rebroadcast(self):
        runner = WorkspaceRunner(
            env_adapter=MockGridAdapter(),
            modules=make_modules(),
            experiment=ExperimentConfig(ignition_threshold=2.0),
        )

        first = runner.step()
        self.assertFalse(first.broadcast.metadata["workspace"]["ignited"])
        self.assertFalse(first.broadcast.metadata["workspace"]["maintained"])
        self.assertIsNone(runner.last_broadcast)

        second = runner.step()
        module_inputs = {
            state.module_name: state.module_input
            for state in second.module_states
        }
        self.assertIsNone(module_inputs["perception"].global_broadcast)
        self.assertIsNone(module_inputs["motor"].global_broadcast)
        self.assertIsNone(module_inputs["language_report"].global_broadcast)

    def test_experimenter_instruction_becomes_task_goal(self):
        env_state = EnvironmentState(
            timestamp=0,
            observation={},
            symbolic_state={},
            info={"experimenter_instruction": "collect one resource and stop"},
        )
        router = InputRouter(task_goal="fallback")
        inputs = router.build_inputs(
            modules=make_modules(),
            env_state=env_state,
            cycle_t=0,
            workspace_state=runner_workspace_state(),
            last_broadcast=None,
            experiment=ExperimentConfig(),
        )

        self.assertEqual(
            inputs["motor"].task_goal,
            "collect one resource and stop",
        )

    def test_foraging_adapter_stops_at_target_resources(self):
        env = FakeQiyuanEnv()
        adapter = ForagingEnvAdapter(env=env, target_resources=1)

        state = adapter.reset()
        self.assertFalse(state.done)
        self.assertEqual(adapter.episode_grid, env.grid)
        self.assertEqual(state.info["qiyuan_episode_grid"], env.grid)
        self.assertTrue(state.info["qiyuan_playback_api"]["get_grid"])

        done_state = adapter.step("RIGHT")
        self.assertTrue(done_state.done)
        self.assertEqual(done_state.symbolic_state["resources_collected"], 1)


def runner_workspace_state():
    runner = WorkspaceRunner(env_adapter=MockGridAdapter(), modules=make_modules())
    return runner.workspace.state


class FakeQiyuanEnv:
    def __init__(self):
        self.grid_size = 3
        self.grid = [
            [1, 1, 1],
            [1, 0, 0],
            [1, 1, 1],
        ]
        self.base_pos = (1, 1)
        self.agent_pos = [1, 1]
        self.resource_pos = [2, 1]
        self.carrying = False
        self.step_count = 0
        self.resources_collected = 0

    def reset(self, difficulty=1):
        self.agent_pos = [1, 1]
        self.resource_pos = [2, 1]
        self.resources_collected = 0
        self.step_count = 0
        return self._state()

    def get_grid(self):
        return [row[:] for row in self.grid]

    def step(self, action):
        self.step_count += 1
        self.agent_pos = [2, 1]
        self.resources_collected = 1
        return self._state()

    def _state(self):
        return {
            "agent_pos": tuple(self.agent_pos),
            "resource_pos": tuple(self.resource_pos),
            "base_pos": self.base_pos,
            "carrying": self.carrying,
            "action_success": True,
            "step_count": self.step_count,
            "resources_collected": self.resources_collected,
        }


if __name__ == "__main__":
    unittest.main()
