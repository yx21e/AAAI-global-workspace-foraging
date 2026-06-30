#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.envs.mock_env import MockGridAdapter
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.motor import MotorModule
from gwt_agent.modules.perception import PerceptionModule


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    trace_path = project_root / "runs" / "mock_trace.jsonl"
    runner = WorkspaceRunner(
        env_adapter=MockGridAdapter(),
        modules=[
            PerceptionModule(),
            MotorModule(),
            LanguageReportModule(),
        ],
        experiment=ExperimentConfig(),
        logger=TraceLogger(str(trace_path)),
    )
    traces = runner.run(num_steps=20)
    print(f"wrote {len(traces)} trace steps to {trace_path}")
    if traces:
        last = traces[-1]
        print(
            "last step:",
            {
                "timestamp": last.timestamp,
                "winner": last.broadcast.winner_module,
                "action": last.selected_action,
                "reward": last.next_env_state.reward if last.next_env_state else None,
                "done": last.next_env_state.done if last.next_env_state else None,
            },
        )


if __name__ == "__main__":
    main()
