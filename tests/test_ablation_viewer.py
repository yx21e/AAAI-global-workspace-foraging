from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gwt_agent.ui.ablation_viewer import build_ablation_payload, build_ablation_viewer


class AblationViewerTest(unittest.TestCase):
    def test_build_ablation_viewer_from_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "runs"
            run_dir.mkdir()

            _write_run(
                run_dir,
                "baseline-a",
                {
                    "run_id": "baseline-a",
                    "done": True,
                    "cycle_count": 11,
                    "env_step_count": 9,
                    "resources_collected": 1,
                    "target_resources": 1,
                    "difficulty": 2,
                    "resolved_map_preset": "difficulty2-five",
                    "resolved_map_variant": 0,
                    "disabled_modules": [],
                    "score_modifiers": {},
                    "ignition_threshold": 0.25,
                    "salience_weight": 0.55,
                    "relevance_weight": 0.45,
                    "workspace_adjustment_policy": "none",
                    "allow_non_workspace_motor_action": True,
                    "motor_execution_threshold": 0.02,
                },
                [
                    _envelope(
                        cycle_t=0,
                        winner="perception",
                        route="no_action_threshold_not_met",
                        target_source="none",
                    ),
                    _envelope(
                        cycle_t=1,
                        winner="motor",
                        route="workspace_broadcast",
                        target_source="workspace_broadcast",
                    ),
                ],
            )
            _write_run(
                run_dir,
                "no-language-a",
                {
                    "run_id": "no-language-a",
                    "done": False,
                    "cycle_count": 20,
                    "env_step_count": 20,
                    "resources_collected": 0,
                    "target_resources": 1,
                    "difficulty": 2,
                    "resolved_map_preset": "difficulty2-five",
                    "resolved_map_variant": 1,
                    "disabled_modules": ["language"],
                    "score_modifiers": {"language": 0.0},
                    "ignition_threshold": 0.4,
                    "salience_weight": 0.8,
                    "relevance_weight": 0.2,
                    "workspace_adjustment_policy": "anti_echo",
                    "allow_non_workspace_motor_action": False,
                    "motor_execution_threshold": 0.02,
                },
                [
                    _envelope(
                        cycle_t=0,
                        winner="perception",
                        route="no_workspace_action",
                        target_source="none",
                    ),
                    _envelope(
                        cycle_t=1,
                        winner="motor",
                        route="no_action_threshold_not_met",
                        target_source="workspace_broadcast",
                    ),
                ],
            )
            _write_run(
                run_dir,
                "strict-workspace-a",
                {
                    "run_id": "strict-workspace-a",
                    "done": True,
                    "cycle_count": 15,
                    "env_step_count": 14,
                    "resources_collected": 1,
                    "target_resources": 1,
                    "difficulty": 2,
                    "resolved_map_preset": "difficulty2-five",
                    "resolved_map_variant": 2,
                    "disabled_modules": ["motor"],
                    "score_modifiers": {"motor": 0.5},
                    "ignition_threshold": 0.2,
                    "salience_weight": 0.6,
                    "relevance_weight": 0.4,
                    "workspace_adjustment_policy": "none",
                    "allow_non_workspace_motor_action": False,
                    "motor_execution_threshold": 0.02,
                },
                [
                    _envelope(
                        cycle_t=0,
                        winner="language",
                        route="workspace_broadcast",
                        target_source="language_instruction",
                    )
                ],
            )

            manifest = {
                "title": "GWT Ablation Dashboard",
                "description": "Static view for ablation conditions.",
                "run_dir": str(run_dir),
                "levels": [
                    {
                        "id": "agent-lesion",
                        "label": "Agent Lesion",
                        "description": "Disable a module and compare task completion.",
                        "conditions": [
                            {
                                "id": "baseline",
                                "label": "Full system",
                                "manipulation": "No modules disabled.",
                                "expected_effect": "Highest completion rate.",
                                "run_ids": ["baseline-a"],
                            },
                            {
                                "id": "no-language",
                                "label": "Disable language",
                                "manipulation": "disabled_modules=language",
                                "expected_effect": "Report channel is removed; movement may stay similar.",
                                "run_ids": ["no-language-a"],
                            },
                        ],
                    },
                    {
                        "id": "workspace",
                        "label": "Workspace Gating",
                        "description": "Test ignition and maintenance effects.",
                        "conditions": [
                            {
                                "id": "strict-workspace",
                                "label": "Strict workspace-only",
                                "manipulation": "disable non-workspace motor route.",
                                "expected_effect": "More no-action cycles, potentially lower throughput.",
                                "run_ids": ["strict-workspace-a"],
                            }
                        ],
                    },
                ],
            }
            manifest_path = root / "ablation_manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            viewer = build_ablation_viewer(manifest_path=str(manifest_path))
            payload = build_ablation_payload(manifest_path=str(manifest_path))

            html = viewer.read_text(encoding="utf-8")
            self.assertIn("GWT Ablation Dashboard", html)
            self.assertIn("levelSelect", html)
            self.assertIn("conditionSelect", html)
            self.assertIn("Fresh Ignition Winners", html)
            self.assertIn("Maintained Broadcast Sources", html)
            self.assertIn("Agent Lesion", html)
            self.assertIn("Workspace Gating", html)
            self.assertIn("Disable language", html)
            self.assertEqual(payload["total_conditions"], 3)
            self.assertEqual(payload["total_runs"], 3)
            self.assertEqual(payload["levels"][0]["conditions"][0]["metrics"]["success_rate"], 1.0)
            self.assertEqual(payload["levels"][0]["conditions"][1]["metrics"]["success_count"], 0)
            self.assertEqual(payload["levels"][1]["conditions"][0]["runs"][0]["winner_counts"]["language"], 1)


def _write_run(run_dir: Path, run_id: str, summary: dict, envelopes: list[dict]) -> None:
    (run_dir / f"{run_id}_summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    (run_dir / f"{run_id}_envelopes.jsonl").write_text(
        "\n".join(json.dumps(envelope) for envelope in envelopes) + "\n",
        encoding="utf-8",
    )
    (run_dir / f"{run_id}_actions.jsonl").write_text("[]\n", encoding="utf-8")


def _envelope(*, cycle_t: int, winner: str, route: str, target_source: str) -> dict:
    return {
        "cycle_t": cycle_t,
        "env_t": cycle_t,
        "env_state": {
            "symbolic_state": {
                "agent_position": [cycle_t + 1, 1],
                "resource_position": [2, 1],
                "resources_collected": cycle_t,
                "carrying_resource": False,
            }
        },
        "next_env_state": {
            "symbolic_state": {
                "agent_position": [cycle_t + 2, 1],
                "resource_position": None,
                "resources_collected": cycle_t + 1,
                "carrying_resource": False,
                "action_success": True,
            }
        },
        "env_action": {
            "command": "RIGHT",
            "action_type": "MOVE",
            "should_step": True,
            "metadata": {"action_route": route},
        },
        "workspace_broadcast": {
            "winner_module": winner,
            "content": {
                "summary": f"{winner} summary",
                "observations": [f"target_source={target_source}"],
            },
            "metadata": {
                "workspace": {
                    "ignited": True,
                    "ignition_threshold": 0.25,
                    "strength": 1.0,
                }
            },
        },
        "module_states": [
            {
                "module_name": "motor",
                "status": "proposed",
                "proposal": {
                    "importance_score": 0.4,
                    "salience_score": 0.3,
                    "goal_relevance_score": 0.8,
                    "action_hint": "RIGHT",
                    "content": {
                        "summary": "motor summary",
                        "observations": [f"target_source={target_source}"],
                    },
                    "metadata": {
                        "importance_function": {
                            "bottom_up_salience": 0.3,
                            "top_down_relevance": 0.8,
                            "salience_weight": 0.55,
                            "relevance_weight": 0.45,
                            "recurrence_bonus": 0.0,
                            "workspace_adjustment": 1.0,
                            "encoder": "HashingSentenceEncoder",
                        }
                    },
                },
            }
        ],
    }
