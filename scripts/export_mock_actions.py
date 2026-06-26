#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.export import trace_step_to_envelope, write_action_stream, write_envelopes_jsonl
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.envs.mock_env import MockGridAdapter
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.motor import MotorModule
from gwt_agent.modules.outcome import OutcomeMonitorModule
from gwt_agent.modules.perception import PerceptionModule


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    runner = WorkspaceRunner(
        env_adapter=MockGridAdapter(),
        modules=[
            PerceptionModule(),
            MotorModule(),
            OutcomeMonitorModule(),
            LanguageReportModule(),
        ],
        experiment=ExperimentConfig(),
        logger=TraceLogger(),
        run_id="mock-export",
    )
    traces = runner.run(num_steps=20)
    envelopes = [
        trace_step_to_envelope(trace=trace, run_id=runner.run_id)
        for trace in traces
    ]

    full_path = root / "runs" / "mock_trace_envelopes.jsonl"
    actions_path = root / "runs" / "mock_action_stream.jsonl"
    write_envelopes_jsonl(str(full_path), envelopes)
    write_action_stream(str(actions_path), envelopes)

    print(f"wrote full standardized envelopes to {full_path}")
    print(f"wrote Qiyuan-readable action stream to {actions_path}")


if __name__ == "__main__":
    main()
