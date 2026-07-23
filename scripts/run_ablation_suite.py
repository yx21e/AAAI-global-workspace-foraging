#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from gwt_agent.envs.map_variants import DIFFICULTY2_FIVE
from gwt_agent.ui.ablation_viewer import build_ablation_viewer


DEFAULT_PROMPT = "move up for 5 steps, this is top priority"


@dataclass(frozen=True)
class ConditionSpec:
    id: str
    label: str
    level: str
    manipulation: str
    expected_effect: str
    extra_args: List[str] = field(default_factory=list)
    reuse: str | None = None


LEVELS = [
    {
        "id": "agent-lesion",
        "label": "Agent Lesion",
        "description": "Disable one module at a time while keeping map, task, scoring, and backend fixed.",
    },
    {
        "id": "workspace-gating",
        "label": "Workspace Gating",
        "description": "Compare workspace-only action against the optional non-workspace motor route.",
    },
    {
        "id": "attention-importance",
        "label": "Attention / Importance",
        "description": "Change only the deterministic importance score weights.",
    },
    {
        "id": "broadcast-bridge",
        "label": "Broadcast / Bridge",
        "description": "Test whether experimenter language instructions reach motor through workspace broadcast.",
    },
    {
        "id": "environment-perturbation",
        "label": "Environment Perturbation",
        "description": "Use the same full-system pipeline across the five difficulty-2 map variants.",
    },
]


CONDITIONS = [
    ConditionSpec(
        id="full-system",
        label="Full system",
        level="agent-lesion",
        manipulation="No modules disabled; non-workspace motor route enabled.",
        expected_effect="Reference autonomous foraging performance.",
        extra_args=["--allow-non-workspace-motor"],
    ),
    ConditionSpec(
        id="disable-perception",
        label="Disable perception",
        level="agent-lesion",
        manipulation="Disable only the perception module.",
        expected_effect="Motor should lose global map/target broadcasts and task success should drop.",
        extra_args=["--allow-non-workspace-motor", "--disable-module", "perception"],
    ),
    ConditionSpec(
        id="disable-motor",
        label="Disable motor",
        level="agent-lesion",
        manipulation="Disable only the motor module.",
        expected_effect="Workspace can still broadcast, but simulator movement should mostly disappear.",
        extra_args=["--allow-non-workspace-motor", "--disable-module", "motor"],
    ),
    ConditionSpec(
        id="disable-language",
        label="Disable language",
        level="agent-lesion",
        manipulation="Disable only the language module.",
        expected_effect="Autonomous foraging should remain close to baseline when no prompt intervention is used.",
        extra_args=["--allow-non-workspace-motor", "--disable-module", "language"],
    ),
    ConditionSpec(
        id="auto-motor-route",
        label="Non-workspace motor on",
        level="workspace-gating",
        manipulation="Allow current motor proposals above motor_execution_threshold to act without winning workspace.",
        expected_effect="Reference throughput for the automatic/local motor route.",
        reuse="full-system",
    ),
    ConditionSpec(
        id="strict-workspace",
        label="Strict workspace-only",
        level="workspace-gating",
        manipulation="Disable non-workspace motor execution.",
        expected_effect="Actions should occur only from fresh action-bearing workspace broadcasts.",
    ),
    ConditionSpec(
        id="default-importance",
        label="Default weights",
        level="attention-importance",
        manipulation="Use salience_weight=0.55 and relevance_weight=0.45.",
        expected_effect="Reference deterministic attention-gate behavior.",
        reuse="full-system",
    ),
    ConditionSpec(
        id="salience-only",
        label="Salience only",
        level="attention-importance",
        manipulation="Set salience_weight=1.0 and relevance_weight=0.0.",
        expected_effect="Winner selection should follow private-input change rather than task relevance.",
        extra_args=[
            "--allow-non-workspace-motor",
            "--salience-weight",
            "1.0",
            "--relevance-weight",
            "0.0",
        ],
    ),
    ConditionSpec(
        id="relevance-only",
        label="Relevance only",
        level="attention-importance",
        manipulation="Set salience_weight=0.0 and relevance_weight=1.0.",
        expected_effect="Winner selection should follow semantic relevance to task and prior broadcast.",
        extra_args=[
            "--allow-non-workspace-motor",
            "--salience-weight",
            "0.0",
            "--relevance-weight",
            "1.0",
        ],
    ),
    ConditionSpec(
        id="language-bridge-on",
        label="Language bridge on",
        level="broadcast-bridge",
        manipulation=(
            "Inject the same language pause prompt, fix score_modifier language=1.6, "
            "and allow instruction_* fields to reach motor."
        ),
        expected_effect="Motor may temporarily follow the language instruction if language wins workspace.",
        extra_args=[
            "--allow-non-workspace-motor",
            "--pause-language-at",
            f"8={DEFAULT_PROMPT}",
            "--score-modifier",
            "language=1.6",
        ],
    ),
    ConditionSpec(
        id="language-bridge-off",
        label="Language bridge off",
        level="broadcast-bridge",
        manipulation=(
            "Inject the same language pause prompt, fix score_modifier language=1.6, "
            "but strip instruction_* fields from broadcast."
        ),
        expected_effect="Prompt text can be reported, but motor should not receive structured instruction cues.",
        extra_args=[
            "--allow-non-workspace-motor",
            "--pause-language-at",
            f"8={DEFAULT_PROMPT}",
            "--score-modifier",
            "language=1.6",
            "--disable-language-bridge",
        ],
    ),
    ConditionSpec(
        id="five-map-sweep",
        label="Five-map sweep",
        level="environment-perturbation",
        manipulation="Run the full system on each difficulty-2 map variant.",
        expected_effect="Measure robustness to base/resource/obstacle layout variation.",
        reuse="full-system",
    ),
]


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run a standardized multi-map GWT ablation suite and build its dashboard.",
    )
    parser.add_argument(
        "--qiyuan-path",
        default=str((project_root.parent / "qiyuan_foraging_env").resolve()),
    )
    parser.add_argument(
        "--out-dir",
        default=str(project_root / "runs" / "qiyuan_integrated"),
    )
    parser.add_argument("--suite-id", default=None)
    parser.add_argument("--variants", default="0,1,2,3,4")
    parser.add_argument("--difficulty", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--target-resources", type=int, default=1)
    parser.add_argument("--max-cycles", type=int, default=500)
    parser.add_argument("--agent-backend", default="mock-llm")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--keep-screenshots", action="store_true")
    parser.add_argument("--no-viewer", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    suite_id = args.suite_id or f"ablation-suite-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    variants = parse_variants(args.variants)
    run_ids_by_condition: Dict[str, List[str]] = {}

    for condition in CONDITIONS:
        if condition.reuse:
            run_ids_by_condition[condition.id] = run_ids_by_condition[condition.reuse]
            continue
        run_ids = []
        for variant in variants:
            run_id = f"{suite_id}-{condition.id}-v{variant}"
            run_ids.append(run_id)
            if args.skip_existing and (out_dir / f"{run_id}_summary.json").exists():
                print(f"skip existing {run_id}")
                continue
            command = build_run_command(
                project_root=project_root,
                args=args,
                run_id=run_id,
                variant=variant,
                condition=condition,
            )
            print(f"run {run_id}")
            completed = subprocess.run(command, text=True, capture_output=True)
            if completed.returncode != 0:
                print(completed.stdout)
                print(completed.stderr, file=sys.stderr)
                completed.check_returncode()
            summary = parse_summary_stdout(completed.stdout)
            print(
                "  "
                f"done={summary.get('done')} "
                f"resources={summary.get('resources_collected')} "
                f"cycles={summary.get('cycle_count')} "
                f"steps={summary.get('env_step_count')}"
            )
        run_ids_by_condition[condition.id] = run_ids

    manifest_path = out_dir / f"{suite_id}_manifest.json"
    manifest_path.write_text(
        json.dumps(
            build_manifest(
                suite_id=suite_id,
                variants=variants,
                run_ids_by_condition=run_ids_by_condition,
            ),
            indent=2,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    print(f"wrote ablation manifest to {manifest_path}")
    if not args.no_viewer:
        viewer = build_ablation_viewer(manifest_path=str(manifest_path))
        print(f"wrote ablation dashboard to {viewer}")


def build_run_command(
    *,
    project_root: Path,
    args: argparse.Namespace,
    run_id: str,
    variant: int,
    condition: ConditionSpec,
) -> List[str]:
    command = [
        sys.executable,
        str(project_root / "scripts" / "run_qiyuan_integrated.py"),
        "--qiyuan-path",
        str(Path(args.qiyuan_path).expanduser().resolve()),
        "--difficulty",
        str(args.difficulty),
        "--seed",
        str(args.seed),
        "--map-preset",
        DIFFICULTY2_FIVE,
        "--map-variant",
        str(variant),
        "--target-resources",
        str(args.target_resources),
        "--max-cycles",
        str(args.max_cycles),
        "--run-id",
        run_id,
        "--agent-backend",
        args.agent_backend,
        "--out-dir",
        str(Path(args.out_dir).expanduser().resolve()),
        "--no-render",
        "--no-viewer",
        *condition.extra_args,
    ]
    if not args.keep_screenshots:
        command.append("--no-perception-screenshots")
    return command


def build_manifest(
    *,
    suite_id: str,
    variants: List[int],
    run_ids_by_condition: Dict[str, List[str]],
) -> dict:
    conditions_by_level = {level["id"]: [] for level in LEVELS}
    for condition in CONDITIONS:
        conditions_by_level[condition.level].append(
            {
                "id": condition.id,
                "label": condition.label,
                "manipulation": condition.manipulation,
                "expected_effect": condition.expected_effect,
                "run_ids": run_ids_by_condition[condition.id],
            }
        )
    return {
        "title": "GWT Ablation Dashboard",
        "description": (
            f"Suite {suite_id}; each condition is aggregated over difficulty2 map variants "
            f"{variants} unless explicitly reused from the full-system baseline."
        ),
        "run_dir": ".",
        "levels": [
            {**level, "conditions": conditions_by_level[level["id"]]}
            for level in LEVELS
        ],
    }


def parse_variants(value: str) -> List[int]:
    variants = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        variant = int(item)
        if variant < 0 or variant > 4:
            raise ValueError("--variants only supports difficulty2-five variants 0-4.")
        variants.append(variant)
    if not variants:
        raise ValueError("--variants must include at least one map variant.")
    return variants


def parse_summary_stdout(stdout: str) -> dict:
    start = stdout.find("{")
    if start < 0:
        return {}
    try:
        return json.loads(stdout[start:])
    except json.JSONDecodeError:
        return {}


if __name__ == "__main__":
    main()
