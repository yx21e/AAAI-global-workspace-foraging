#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from gwt_agent.ui.qiyuan_viewer import build_viewer, build_viewer_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_DIR = PROJECT_ROOT / "runs" / "qiyuan_integrated"


@dataclass
class ServerConfig:
    run_id: str
    run_dir: Path
    python_executable: str
    rerun_timeout: int
    max_cycles: Optional[int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a Qiyuan/GWT viewer with experimenter prompt reruns.",
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", default=str(DEFAULT_RUN_DIR))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--python",
        dest="python_executable",
        default=sys.executable,
        help="Python executable used for reruns. Use the HF venv Python for HuggingFace runs.",
    )
    parser.add_argument(
        "--rerun-timeout",
        type=int,
        default=900,
        help="Seconds before a prompt-triggered rerun is stopped.",
    )
    parser.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="Override max cycles for prompt-triggered reruns.",
    )
    parser.add_argument("--open", action="store_true")
    return parser.parse_args()


def load_summary(run_dir: Path, run_id: str) -> Dict[str, Any]:
    path = run_dir / f"{run_id}_summary.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing summary file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def safe_run_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned or "run"


def make_prompt_run_id(source_run_id: str, cycle: int) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return safe_run_id(f"{source_run_id}-prompt-c{cycle}-{stamp}")


def make_map_run_id(source_run_id: str, map_preset: str, map_variant: Optional[Any]) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if map_preset == "qiyuan-default":
        map_label = "qiyuan-default"
    else:
        map_label = f"{map_preset}-v{map_variant}"
    return safe_run_id(f"{source_run_id}-map-{map_label}-{stamp}")


def add_arg(command: list[str], flag: str, value: Any) -> None:
    if value is None or value == "":
        return
    command.extend([flag, str(value)])


def rerun_map_preset(summary: Dict[str, Any]) -> Optional[str]:
    if summary.get("resolved_map_preset"):
        return str(summary["resolved_map_preset"])
    if "map_preset" in summary:
        value = summary.get("map_preset")
        return str(value) if value else None
    return "qiyuan-default"


def rerun_map_variant(summary: Dict[str, Any]) -> Optional[Any]:
    resolved_variant = summary.get("resolved_map_variant")
    if resolved_variant is not None:
        return resolved_variant
    return summary.get("map_variant")


def build_run_command(
    *,
    config: ServerConfig,
    summary: Dict[str, Any],
    new_run_id: str,
    map_preset: Optional[str] = None,
    map_variant: Optional[Any] = None,
    language_pauses: Optional[Dict[str, str]] = None,
) -> list[str]:
    max_cycles = config.max_cycles or summary.get("max_cycles") or max(summary.get("cycle_count", 1), 1)
    command = [
        config.python_executable,
        str(PROJECT_ROOT / "scripts" / "run_qiyuan_integrated.py"),
    ]
    add_arg(command, "--qiyuan-path", summary.get("qiyuan_path"))
    add_arg(command, "--difficulty", summary.get("difficulty", 1))
    add_arg(command, "--seed", summary.get("seed", 7))
    selected_preset = map_preset or rerun_map_preset(summary)
    selected_variant = rerun_map_variant(summary) if map_variant is None else map_variant
    add_arg(command, "--map-preset", selected_preset)
    if selected_preset != "qiyuan-default":
        add_arg(command, "--map-variant", selected_variant)
    add_arg(command, "--target-resources", summary.get("target_resources", 1))
    add_arg(command, "--max-cycles", max_cycles)
    add_arg(command, "--run-id", new_run_id)
    add_arg(command, "--out-dir", config.run_dir)
    add_arg(command, "--instruction", summary.get("experimenter_instruction"))
    add_arg(
        command,
        "--agent-backend",
        summary.get("agent_backend") or summary.get("resolved_agent_backend") or "mock-llm",
    )
    add_arg(command, "--openai-model", summary.get("openai_model"))
    add_arg(command, "--openai-vision-model", summary.get("openai_vision_model"))
    add_arg(command, "--hf-model", summary.get("hf_model"))
    add_arg(command, "--hf-vision-model", summary.get("hf_vision_model"))
    add_arg(command, "--ignition-threshold", summary.get("ignition_threshold"))
    add_arg(command, "--salience-weight", summary.get("salience_weight"))
    add_arg(command, "--relevance-weight", summary.get("relevance_weight"))
    add_arg(command, "--workspace-recurrence-bonus", summary.get("workspace_recurrence_bonus"))
    add_arg(command, "--workspace-adjustment-policy", summary.get("workspace_adjustment_policy"))
    add_arg(command, "--report-query-every", summary.get("report_query_every", 0))
    add_arg(command, "--report-query", summary.get("report_query"))
    for module, factor in sorted((summary.get("score_modifiers") or {}).items()):
        add_arg(command, "--score-modifier", f"{module}={factor}")
    for pause_cycle in sorted(language_pauses or {}, key=lambda value: int(value)):
        add_arg(command, "--pause-language-at", f"{pause_cycle}={language_pauses[pause_cycle]}")
    if summary.get("allow_non_workspace_motor_action"):
        command.append("--allow-non-workspace-motor")
    return command


def build_rerun_command(
    *,
    config: ServerConfig,
    summary: Dict[str, Any],
    new_run_id: str,
    cycle: int,
    prompt: str,
) -> list[str]:
    pauses = {
        str(key): str(value)
        for key, value in (summary.get("language_pause_cycles") or {}).items()
    }
    pauses[str(cycle)] = prompt
    return build_run_command(
        config=config,
        summary=summary,
        new_run_id=new_run_id,
        language_pauses=pauses,
    )


def build_map_command(
    *,
    config: ServerConfig,
    summary: Dict[str, Any],
    new_run_id: str,
    map_preset: str,
    map_variant: Optional[Any],
) -> list[str]:
    return build_run_command(
        config=config,
        summary=summary,
        new_run_id=new_run_id,
        map_preset=map_preset,
        map_variant=map_variant,
        language_pauses={},
    )


def run_command_and_payload(
    *,
    config: ServerConfig,
    command: list[str],
    new_run_id: str,
) -> Dict[str, Any]:
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = "src" if not existing_path else f"src{os.pathsep}{existing_path}"
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=config.rerun_timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Rerun failed with exit code "
            f"{completed.returncode}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    viewer_path = config.run_dir / f"{new_run_id}_viewer.html"
    if not viewer_path.exists():
        raise FileNotFoundError(f"Rerun finished but viewer was not created: {viewer_path}")
    payload = build_viewer_payload(
        run_dir=str(config.run_dir),
        run_id=new_run_id,
        viewer_dir=str(config.run_dir),
    )
    return {
        "ok": True,
        "run_id": new_run_id,
        "viewer_url": f"/{viewer_path.name}",
        "summary_url": f"/{new_run_id}_summary.json",
        "payload": payload,
        "stdout": completed.stdout,
    }


def run_prompt_rerun(
    *,
    config: ServerConfig,
    source_run_id: str,
    cycle: int,
    prompt: str,
) -> Dict[str, Any]:
    summary = load_summary(config.run_dir, source_run_id)
    new_run_id = make_prompt_run_id(source_run_id, cycle)
    command = build_rerun_command(
        config=config,
        summary=summary,
        new_run_id=new_run_id,
        cycle=cycle,
        prompt=prompt,
    )
    return run_command_and_payload(
        config=config,
        command=command,
        new_run_id=new_run_id,
    )


def run_map_rerun(
    *,
    config: ServerConfig,
    source_run_id: str,
    map_preset: str,
    map_variant: Optional[Any],
) -> Dict[str, Any]:
    summary = load_summary(config.run_dir, source_run_id)
    new_run_id = make_map_run_id(source_run_id, map_preset, map_variant)
    command = build_map_command(
        config=config,
        summary=summary,
        new_run_id=new_run_id,
        map_preset=map_preset,
        map_variant=map_variant,
    )
    return run_command_and_payload(
        config=config,
        command=command,
        new_run_id=new_run_id,
    )


def parse_map_request(payload: Dict[str, Any]) -> tuple[str, Optional[str]]:
    map_preset = str(payload.get("map_preset") or "difficulty2-five").strip()
    if map_preset not in {"qiyuan-default", "difficulty2-five"}:
        raise ValueError("map_preset must be qiyuan-default or difficulty2-five.")
    if map_preset == "qiyuan-default":
        return map_preset, None
    raw_variant = str(payload.get("map_variant", "0")).strip()
    try:
        variant_id = int(raw_variant)
    except ValueError as exc:
        raise ValueError("map_variant must be an integer between 0 and 4.") from exc
    if variant_id < 0 or variant_id > 4:
        raise ValueError("map_variant must be between 0 and 4.")
    return map_preset, str(variant_id)


def make_handler(config: ServerConfig):
    class ExperimenterViewerHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(config.run_dir), **kwargs)

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self.send_response(302)
                self.send_header("Location", f"/{config.run_id}_viewer.html")
                self.end_headers()
                return
            if path.startswith("/api/"):
                self.write_json({"ok": False, "error": "Unknown API endpoint."}, status=404)
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/rerun":
                self.handle_prompt_rerun()
                return
            if path == "/api/map":
                self.handle_map_rerun()
                return
            if path.startswith("/api/"):
                self.write_json({"ok": False, "error": "Unknown API endpoint."}, status=404)
                return

            self.write_json({"ok": False, "error": "Unknown POST target."}, status=404)

        def handle_prompt_rerun(self) -> None:
            try:
                payload = self.read_json()
                source_run_id = safe_run_id(str(payload.get("run_id") or config.run_id))
                cycle = int(payload.get("cycle", 0))
                prompt = str(payload.get("prompt") or "").strip()
                if cycle < 0:
                    raise ValueError("cycle must be non-negative.")
                if not prompt:
                    raise ValueError("prompt must not be empty.")
                result = run_prompt_rerun(
                    config=config,
                    source_run_id=source_run_id,
                    cycle=cycle,
                    prompt=prompt,
                )
                self.write_json(result)
            except Exception as exc:  # pragma: no cover - exercised by browser/demo use.
                self.write_json({"ok": False, "error": str(exc)}, status=500)

        def handle_map_rerun(self) -> None:
            try:
                payload = self.read_json()
                source_run_id = safe_run_id(str(payload.get("run_id") or config.run_id))
                map_preset, map_variant = parse_map_request(payload)
                result = run_map_rerun(
                    config=config,
                    source_run_id=source_run_id,
                    map_preset=map_preset,
                    map_variant=map_variant,
                )
                self.write_json(result)
            except Exception as exc:  # pragma: no cover - exercised by browser/demo use.
                self.write_json({"ok": False, "error": str(exc)}, status=500)

        def read_json(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            if length > 1_000_000:
                raise ValueError("JSON body is too large.")
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def write_json(self, payload: Dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return ExperimenterViewerHandler


def main() -> None:
    args = parse_args()
    run_dir = Path(args.run_dir).expanduser().resolve()
    load_summary(run_dir, args.run_id)
    build_viewer(run_dir=str(run_dir), run_id=args.run_id)
    config = ServerConfig(
        run_id=args.run_id,
        run_dir=run_dir,
        python_executable=args.python_executable,
        rerun_timeout=args.rerun_timeout,
        max_cycles=args.max_cycles,
    )
    server = ThreadingHTTPServer((args.host, args.port), make_handler(config))
    url = f"http://{args.host}:{args.port}/"
    print(f"serving {args.run_id} from {run_dir}")
    print(url)
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
