#!/usr/bin/env python3
from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from gwt_agent.ui.ablation_viewer import build_ablation_viewer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a static GWT ablation dashboard from a manifest JSON file.",
    )
    parser.add_argument("--manifest", required=True, help="Path to the ablation manifest JSON.")
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output HTML path. Defaults to <manifest_stem>_viewer.html next to the manifest.",
    )
    parser.add_argument("--open", action="store_true", help="Open the generated dashboard in a browser.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    viewer = build_ablation_viewer(
        manifest_path=args.manifest,
        output_path=args.output,
    )
    print(f"wrote ablation dashboard to {viewer}")
    if args.open:
        webbrowser.open(viewer.as_uri())


if __name__ == "__main__":
    main()
