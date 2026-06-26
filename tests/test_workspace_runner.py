from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gwt_agent.core.export import trace_step_to_envelope, write_action_stream
from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.envs.mock_env import MockGridAdapter
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.motor import MotorModule
from gwt_agent.modules.outcome import OutcomeMonitorModule
from gwt_agent.modules.perception import PerceptionModule


def make_modules():
    return [
        PerceptionModule(),
        MotorModule(),
        OutcomeMonitorModule(),
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
                {"perception", "motor", "outcome_monitor", "language_report"},
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


if __name__ == "__main__":
    unittest.main()
