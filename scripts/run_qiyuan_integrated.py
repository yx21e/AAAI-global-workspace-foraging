#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path

from gwt_agent.core.export import (
    trace_step_to_envelope,
    write_action_stream,
    write_envelopes_jsonl,
)
from gwt_agent.core.experiment import ExperimentConfig
from gwt_agent.core.logger import TraceLogger
from gwt_agent.core.router import InputRouter
from gwt_agent.core.runner import WorkspaceRunner
from gwt_agent.envs.foraging_adapter import ForagingEnvAdapter
from gwt_agent.envs.qiyuan_loader import load_foraging_env_class
from gwt_agent.llm.client import build_llm_client
from gwt_agent.modules.language import LanguageReportModule
from gwt_agent.modules.llm_agents import LLMLanguageModule, LLMMotorModule, LLMPerceptionModule
from gwt_agent.modules.motor import MotorModule
from gwt_agent.modules.perception import PerceptionModule
from gwt_agent.ui.qiyuan_viewer import build_viewer


DEFAULT_INSTRUCTION = (
    "Collect exactly one resource, avoid walls, use PICKUP only when standing "
    "on the resource, return to base, and stop after the resource is delivered."
)
DEFAULT_HF_TEXT_MODEL = "Qwen/Qwen3-4B-Instruct-2507"
DEFAULT_HF_VISION_MODEL = "Qwen/Qwen3-VL-8B-Instruct"


def default_qiyuan_path(project_root: Path) -> Path:
    return (project_root.parent / "qiyuan_foraging_env").resolve()


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run the GWT scaffold with Qiyuan's ForagingEnv.",
    )
    parser.add_argument(
        "--qiyuan-path",
        default=str(default_qiyuan_path(project_root)),
        help="Path to a local Foraging-Environment-Design checkout.",
    )
    parser.add_argument("--difficulty", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target-resources", type=int, default=1)
    parser.add_argument("--max-cycles", type=int, default=200)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    parser.add_argument(
        "--agent-backend",
        choices=["auto", "openai", "huggingface", "hf", "mock-llm", "heuristic"],
        default="auto",
        help=(
            "Module backend. auto uses OpenAI when OPENAI_API_KEY and the openai "
            "package are available, otherwise mock-llm."
        ),
    )
    parser.add_argument(
        "--openai-model",
        default=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        help="OpenAI model for motor/language when --agent-backend openai or auto resolves to OpenAI.",
    )
    parser.add_argument(
        "--openai-vision-model",
        default=os.getenv("OPENAI_VISION_MODEL"),
        help="OpenAI model for multimodal perception. Defaults to --openai-model.",
    )
    parser.add_argument(
        "--hf-model",
        default=os.getenv("HF_TEXT_MODEL", DEFAULT_HF_TEXT_MODEL),
        help="HuggingFace text model for motor/language.",
    )
    parser.add_argument(
        "--hf-vision-model",
        default=os.getenv("HF_VISION_MODEL", DEFAULT_HF_VISION_MODEL),
        help="HuggingFace multimodal vision model for perception.",
    )
    parser.add_argument("--ignition-threshold", type=float, default=0.25)
    parser.add_argument("--salience-weight", type=float, default=0.55)
    parser.add_argument("--relevance-weight", type=float, default=0.45)
    parser.add_argument(
        "--score-modifier",
        action="append",
        default=[],
        metavar="MODULE=FACTOR",
        help="Optional module score multiplier, e.g. perception=1.1. Repeatable.",
    )
    parser.add_argument(
        "--workspace-recurrence-bonus",
        type=float,
        default=0.0,
        help="Optional bonus for the module that won the previous workspace cycle.",
    )
    parser.add_argument(
        "--report-query-every",
        type=int,
        default=0,
        help="Inject an experimenter report query every N cognitive cycles; 0 disables it.",
    )
    parser.add_argument(
        "--report-query",
        default="Please summarize the currently active workspace broadcast.",
    )
    parser.add_argument(
        "--pause-language-at",
        action="append",
        default=[],
        metavar="CYCLE=TEXT",
        help=(
            "Pause at a cognitive cycle and send TEXT to the language agent. "
            "Repeatable, e.g. --pause-language-at '8=What are you hearing?'"
        ),
    )
    parser.add_argument(
        "--out-dir",
        default=str(project_root / "runs" / "qiyuan_integrated"),
    )
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument(
        "--allow-non-workspace-motor",
        action="store_true",
        help="Allow the optional motor threshold route even when motor did not win workspace.",
    )
    return parser.parse_args()


def main() -> None:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    args = parse_args()
    random.seed(args.seed)
    language_pauses = parse_language_pauses(args.pause_language_at)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = args.run_id or f"qiyuan-d{args.difficulty}-seed{args.seed}"
    trace_path = out_dir / f"{run_id}_trace.jsonl"
    envelope_path = out_dir / f"{run_id}_envelopes.jsonl"
    action_path = out_dir / f"{run_id}_actions.jsonl"
    summary_path = out_dir / f"{run_id}_summary.json"
    frame_dir = out_dir / f"{run_id}_frames"
    perception_dir = out_dir / f"{run_id}_perception_inputs"

    ForagingEnv = load_foraging_env_class(args.qiyuan_path)
    env = ForagingEnv()
    adapter = ForagingEnvAdapter(
        env=env,
        difficulty=args.difficulty,
        experimenter_instruction=args.instruction,
        target_resources=args.target_resources,
    )
    modules, resolved_backend = build_modules(args)
    runner = WorkspaceRunner(
        env_adapter=adapter,
        modules=modules,
        experiment=ExperimentConfig(
            allow_non_workspace_motor_action=args.allow_non_workspace_motor,
            ignition_threshold=args.ignition_threshold,
            salience_weight=args.salience_weight,
            relevance_weight=args.relevance_weight,
            score_modifiers=parse_score_modifiers(args.score_modifier),
            workspace_recurrence_bonus=args.workspace_recurrence_bonus,
        ),
        logger=TraceLogger(str(trace_path)),
        run_id=run_id,
        input_router=InputRouter(task_goal=args.instruction),
    )

    initial_state = adapter.reset()
    runner._current_state = initial_state
    if not args.no_render:
        frame_dir.mkdir(parents=True, exist_ok=True)
        env.render(str(frame_dir / "frame_0000_initial.png"))
    attach_perception_screenshot(adapter, initial_state, perception_dir)

    traces = []
    for cycle_index in range(args.max_cycles):
        current_state = getattr(runner, "_current_state", None)
        if current_state is not None:
            apply_report_query(
                current_state,
                cycle_index=cycle_index,
                every=args.report_query_every,
                query=args.report_query,
                language_pauses=language_pauses,
            )
            attach_perception_screenshot(adapter, current_state, perception_dir)
        trace = runner.step()
        traces.append(trace)
        if not args.no_render:
            env.render(str(frame_dir / f"frame_{cycle_index + 1:04d}.png"))
        if trace.next_env_state and trace.next_env_state.done:
            break

    envelopes = [
        trace_step_to_envelope(trace=trace, run_id=runner.run_id)
        for trace in traces
    ]
    write_envelopes_jsonl(str(envelope_path), envelopes)
    write_action_stream(str(action_path), envelopes)

    final_state = traces[-1].next_env_state if traces else initial_state
    final_symbolic = final_state.symbolic_state if final_state else {}
    summary = {
        "run_id": run_id,
        "qiyuan_path": str(Path(args.qiyuan_path).resolve()),
        "difficulty": args.difficulty,
        "seed": args.seed,
        "target_resources": args.target_resources,
        "experimenter_instruction": args.instruction,
        "agent_backend": args.agent_backend,
        "resolved_agent_backend": resolved_backend,
        "openai_model": args.openai_model,
        "openai_vision_model": args.openai_vision_model or args.openai_model,
        "hf_model": args.hf_model,
        "hf_vision_model": args.hf_vision_model,
        "ignition_threshold": args.ignition_threshold,
        "salience_weight": args.salience_weight,
        "relevance_weight": args.relevance_weight,
        "score_modifiers": parse_score_modifiers(args.score_modifier),
        "allow_non_workspace_motor_action": args.allow_non_workspace_motor,
        "motor_execution_threshold": 0.02,
        "report_query_every": args.report_query_every,
        "language_pause_cycles": {str(key): value for key, value in language_pauses.items()},
        "cycle_count": len(traces),
        "env_step_count": final_state.timestamp if final_state else None,
        "done": bool(final_state.done) if final_state else False,
        "resources_collected": final_symbolic.get("resources_collected"),
        "agent_position": final_symbolic.get("agent_position"),
        "carrying_resource": final_symbolic.get("carrying_resource"),
        "trace_path": str(trace_path),
        "envelope_path": str(envelope_path),
        "action_stream_path": str(action_path),
        "frame_dir": None if args.no_render else str(frame_dir),
        "perception_screenshot_dir": str(perception_dir),
        "viewer_path": None,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    if not args.no_render and not args.no_viewer:
        viewer = build_viewer(run_dir=str(out_dir), run_id=run_id)
        summary["viewer_path"] = str(viewer)
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, ensure_ascii=True))


def build_modules(args: argparse.Namespace):
    if args.agent_backend == "heuristic":
        return [
            PerceptionModule(),
            MotorModule(),
            LanguageReportModule(),
        ], "heuristic"

    if args.agent_backend in {"huggingface", "hf"}:
        client = build_llm_client(args.agent_backend, default_model=args.hf_model)
        text_model = args.hf_model
        vision_model = args.hf_vision_model
    else:
        client = build_llm_client(args.agent_backend, default_model=args.openai_model)
        text_model = args.openai_model
        vision_model = args.openai_vision_model or args.openai_model
    resolved_backend = getattr(client, "provider_name", client.__class__.__name__)
    return [
        LLMPerceptionModule(client=client, model=vision_model),
        LLMMotorModule(client=client, model=text_model),
        LLMLanguageModule(client=client, model=text_model),
    ], resolved_backend


def parse_score_modifiers(values):
    modifiers = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid --score-modifier {value!r}; expected MODULE=FACTOR.")
        module, factor_text = value.split("=", 1)
        modifiers[module.strip()] = float(factor_text)
    return modifiers


def parse_language_pauses(values):
    pauses = {}
    for value in values:
        if "=" not in value:
            raise ValueError(
                f"Invalid --pause-language-at {value!r}; expected CYCLE=TEXT."
            )
        cycle_text, prompt = value.split("=", 1)
        cycle = int(cycle_text.strip())
        if cycle < 0:
            raise ValueError("--pause-language-at cycle must be non-negative.")
        pauses[cycle] = prompt.strip()
    return pauses


def attach_perception_screenshot(
    adapter: ForagingEnvAdapter,
    state,
    perception_dir: Path,
) -> None:
    perception_dir.mkdir(parents=True, exist_ok=True)
    env_t = int(getattr(state, "timestamp", 0) or 0)
    path = perception_dir / f"perception_env_{env_t:04d}.png"
    adapter.render_screenshot_to_state(state, str(path))


def apply_report_query(
    state,
    *,
    cycle_index: int,
    every: int,
    query: str,
    language_pauses,
) -> None:
    user_prompt = language_pauses.get(cycle_index)
    pause_requested = user_prompt is not None
    report_query = (
        None
        if pause_requested
        else query
        if every > 0 and cycle_index > 0 and cycle_index % every == 0
        else None
    )
    state.info["language_pause_requested"] = pause_requested
    state.info["language_user_prompt"] = user_prompt
    state.info["report_query"] = report_query
    if isinstance(state.observation, dict):
        state.observation["language_pause_requested"] = pause_requested
        state.observation["language_user_prompt"] = user_prompt
        state.observation["report_query"] = report_query


if __name__ == "__main__":
    main()
