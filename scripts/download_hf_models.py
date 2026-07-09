#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


DEFAULT_MODELS = [
    "Qwen/Qwen3-VL-8B-Instruct",
    "Qwen/Qwen3-4B-Instruct-2507",
]

ALLOW_PATTERNS = [
    "*.json",
    "*.safetensors",
    "*.txt",
    "*.model",
    "*.py",
    "*.jinja",
    "tokenizer*",
    "vocab*",
    "merges.txt",
    "README.md",
]

IGNORE_PATTERNS = [
    "*.msgpack",
    "*.h5",
    "*.ot",
    "*.onnx",
    "*.tflite",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download the default HuggingFace models for local GWT agents.",
    )
    parser.add_argument(
        "--cache-dir",
        default="/tmp/hf_home",
        help="HuggingFace cache directory. Use the same value as HF_HOME at runtime.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Model repo id to download. Repeatable. Defaults to the project HF model set.",
    )
    parser.add_argument(
        "--local-dir-root",
        default=None,
        help="Optional root for materialized local snapshots in addition to the cache.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    models = args.model or DEFAULT_MODELS
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_root = Path(args.local_dir_root).expanduser().resolve() if args.local_dir_root else None
    if local_root:
        local_root.mkdir(parents=True, exist_ok=True)

    for model_id in models:
        local_dir = None
        if local_root:
            local_dir = local_root / model_id.replace("/", "__")
        print(f"Downloading {model_id} into cache {cache_dir}")
        path = snapshot_download(
            repo_id=model_id,
            cache_dir=str(cache_dir),
            local_dir=str(local_dir) if local_dir else None,
            allow_patterns=ALLOW_PATTERNS,
            ignore_patterns=IGNORE_PATTERNS,
        )
        print(f"ready: {model_id} -> {path}")

    print(f"Set HF_HOME={cache_dir} before running --agent-backend huggingface.")


if __name__ == "__main__":
    main()
