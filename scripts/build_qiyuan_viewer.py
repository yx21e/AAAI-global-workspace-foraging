#!/usr/bin/env python3
from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from gwt_agent.ui.qiyuan_viewer import build_viewer


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Build a clickable HTML viewer for a Qiyuan/GWT run.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--run-dir",
        default=str(project_root / "runs" / "qiyuan_integrated"),
    )
    parser.add_argument("--frames-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--open", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    viewer = build_viewer(
        run_dir=args.run_dir,
        run_id=args.run_id,
        output_path=args.output,
        frames_dir=args.frames_dir,
    )
    print(f"wrote viewer to {viewer}")
    if args.open:
        webbrowser.open(viewer.as_uri())


if __name__ == "__main__":
    main()
