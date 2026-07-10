#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from gwt_agent.envs.qiyuan_loader import load_foraging_env_class
from gwt_agent.envs.qiyuan_replay import (
    episode_grid_from_trace,
    load_grid,
    load_jsonl,
    render_action_replay,
    render_trace_replay,
    restore_initial_env_from_trace,
    write_replay_summary,
)


def default_qiyuan_path(project_root: Path) -> Path:
    return (project_root.parent / "qiyuan_foraging_env").resolve()


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Replay a recorded GWT/Qiyuan run.",
    )
    parser.add_argument(
        "--qiyuan-path",
        default=str(default_qiyuan_path(project_root)),
        help="Path to a local Foraging-Environment-Design checkout.",
    )
    parser.add_argument(
        "--mode",
        choices=["trace", "action"],
        default="trace",
        help=(
            "trace restores every historical recorded state exactly; action "
            "replays the minimal action stream through env.step()."
        ),
    )
    parser.add_argument("--trace", required=True, help="Full envelope JSONL.")
    parser.add_argument(
        "--actions",
        help="Minimal action-stream JSONL. Required for --mode action.",
    )
    parser.add_argument(
        "--grid",
        default=None,
        help=(
            "Optional episode grid JSON from run_qiyuan_integrated.py. If omitted, "
            "the replay code tries to read qiyuan_episode_grid from the trace."
        ),
    )
    parser.add_argument(
        "--render-dir",
        default=str(project_root / "runs" / "qiyuan_replay_frames"),
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Optional replay summary JSON path.",
    )
    return parser.parse_args()


def main() -> None:
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    args = parse_args()
    ForagingEnv = load_foraging_env_class(args.qiyuan_path)
    env = ForagingEnv()
    trace_records = load_jsonl(args.trace)
    episode_grid = load_grid(args.grid) if args.grid else episode_grid_from_trace(trace_records)

    if args.mode == "trace":
        frames = render_trace_replay(
            env=env,
            envelope_records=trace_records,
            render_dir=args.render_dir,
            prefix="trace_replay",
            episode_grid=episode_grid,
        )
    else:
        if not args.actions:
            raise ValueError("--actions is required when --mode action")
        action_records = load_jsonl(args.actions)
        if not restore_initial_env_from_trace(env, trace_records, episode_grid=episode_grid):
            raise ValueError("Trace file is empty; cannot restore initial env.")
        frames = render_action_replay(
            env=env,
            action_records=action_records,
            render_dir=args.render_dir,
            prefix="action_replay",
        )

    summary_path = args.summary or str(Path(args.render_dir) / "replay_summary.json")
    write_replay_summary(
        summary_path,
        mode=args.mode,
        frames=frames,
        source_trace=args.trace,
        source_actions=args.actions,
        source_grid=args.grid,
        used_load_state=bool(episode_grid is not None and hasattr(env, "load_state")),
    )
    print(f"rendered {len(frames)} replay frames to {args.render_dir}")
    print(f"wrote replay summary to {summary_path}")


if __name__ == "__main__":
    main()
