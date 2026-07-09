from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

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
                    "metadata": {"workspace": {"ignited": True}},
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


if __name__ == "__main__":
    unittest.main()
