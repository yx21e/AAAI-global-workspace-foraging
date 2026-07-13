from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.serve_qiyuan_viewer import ServerConfig, build_rerun_command
from gwt_agent.ui.qiyuan_viewer import build_viewer


class QiyuanViewerTest(unittest.TestCase):
    def test_build_viewer_from_run_artifacts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_id = "viewer-test"
            frame_dir = root / f"{run_id}_frames"
            frame_dir.mkdir()
            (frame_dir / "frame_0000_initial.png").write_bytes(b"")
            (frame_dir / "frame_0001.png").write_bytes(b"")
            (root / f"{run_id}_summary.json").write_text(
                json.dumps(
                    {
                        "run_id": run_id,
                        "done": True,
                        "cycle_count": 1,
                        "resources_collected": 1,
                        "difficulty": 1,
                    }
                ),
                encoding="utf-8",
            )
            envelope = {
                "env_t": 0,
                "cycle_t": 0,
                "env_state": {
                    "symbolic_state": {
                        "agent_position": [1, 1],
                        "resource_position": [2, 1],
                        "resources_collected": 0,
                        "carrying_resource": False,
                    }
                },
                "next_env_state": {
                    "symbolic_state": {
                        "agent_position": [2, 1],
                        "resource_position": None,
                        "resources_collected": 1,
                        "carrying_resource": False,
                    }
                },
                "env_action": {
                    "command": "PICKUP",
                    "action_type": "PICKUP",
                    "metadata": {"action_route": "workspace_broadcast"},
                },
                "workspace_broadcast": {
                    "winner_module": "motor",
                    "content": {
                        "summary": "Motor chose PICKUP after hearing the workspace.",
                    },
                    "metadata": {
                        "winner_rationale": "Workspace winner rationale appears here.",
                        "winner_reflection": "Workspace winner reflection appears here.",
                        "importance_function": {
                            "bottom_up_salience": 0.5,
                            "top_down_relevance": 0.8,
                            "salience_weight": 0.55,
                            "relevance_weight": 0.45,
                            "recurrence_bonus": 0.0,
                            "workspace_adjustment": 1.0,
                            "encoder": "HashingTextEncoder",
                        },
                        "workspace": {
                            "ignited": True,
                            "ignition_threshold": 0.25,
                            "strength": 1.0,
                        },
                    },
                },
                "module_states": [
                    {
                        "module_name": "motor",
                        "status": "proposed",
                        "proposal": {
                            "importance_score": 0.9,
                            "salience_score": 0.5,
                            "goal_relevance_score": 0.8,
                            "action_hint": "PICKUP",
                            "content": {
                                "summary": "Motor output language appears here.",
                            },
                            "rationale": "Module-level motor rationale appears here.",
                            "reflection": "Module-level motor reflection appears here.",
                            "metadata": {
                                "importance_function": {
                                    "bottom_up_salience": 0.5,
                                    "top_down_relevance": 0.8,
                                    "salience_weight": 0.55,
                                    "relevance_weight": 0.45,
                                    "recurrence_bonus": 0.0,
                                    "workspace_adjustment": 1.0,
                                    "encoder": "HashingTextEncoder",
                                }
                            },
                        },
                    }
                ],
            }
            (root / f"{run_id}_envelopes.jsonl").write_text(
                json.dumps(envelope) + "\n",
                encoding="utf-8",
            )
            (root / f"{run_id}_actions.jsonl").write_text(
                json.dumps({"action": "PICKUP", "should_step": True}) + "\n",
                encoding="utf-8",
            )

            viewer = build_viewer(run_dir=str(root), run_id=run_id)

            html = viewer.read_text(encoding="utf-8")
            self.assertIn(run_id, html)
            self.assertIn("frame_0000_initial.png", html)
            self.assertIn("PICKUP", html)
            self.assertIn("Motor chose PICKUP", html)
            self.assertIn("Motor output language appears here.", html)
            self.assertIn("Reasoning", html)
            self.assertIn("Module-level motor rationale appears here.", html)
            self.assertIn("Module-level motor reflection appears here.", html)
            self.assertIn("winner reflection", html)
            self.assertIn("score basis", html)
            self.assertIn("Experimenter", html)
            self.assertIn("sendPromptBtn", html)

    def test_prompt_rerun_command_preserves_run_settings(self):
        config = ServerConfig(
            run_id="viewer-test",
            run_dir=Path("/tmp/gwt-runs"),
            python_executable="python3",
            rerun_timeout=30,
            max_cycles=12,
        )
        summary = {
            "qiyuan_path": "/tmp/qiyuan",
            "difficulty": 2,
            "seed": 7,
            "target_resources": 1,
            "experimenter_instruction": "collect one resource",
            "agent_backend": "mock-llm",
            "ignition_threshold": 0.25,
            "salience_weight": 0.55,
            "relevance_weight": 0.45,
            "workspace_adjustment_policy": "anti_echo",
            "language_pause_cycles": {"2": "earlier prompt"},
            "allow_non_workspace_motor_action": True,
        }

        command = build_rerun_command(
            config=config,
            summary=summary,
            new_run_id="viewer-test-prompt-c4",
            cycle=4,
            prompt="What did you hear?",
        )

        self.assertIn("--out-dir", command)
        self.assertIn("/tmp/gwt-runs", command)
        self.assertIn("--pause-language-at", command)
        self.assertIn("2=earlier prompt", command)
        self.assertIn("4=What did you hear?", command)
        self.assertIn("--workspace-adjustment-policy", command)
        self.assertIn("anti_echo", command)
        self.assertIn("--allow-non-workspace-motor", command)


if __name__ == "__main__":
    unittest.main()
