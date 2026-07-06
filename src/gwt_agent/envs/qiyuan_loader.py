from __future__ import annotations

import importlib.util
from pathlib import Path


def load_foraging_env_class(qiyuan_path: str):
    """Load Qiyuan's ForagingEnv class from a local repo checkout."""
    repo = Path(qiyuan_path).expanduser().resolve()
    module_path = repo / "foraging_env.py"
    if not module_path.exists():
        raise FileNotFoundError(
            f"Could not find foraging_env.py under {repo}. "
            "Pass --qiyuan-path pointing to Foraging-Environment-Design."
        )

    spec = importlib.util.spec_from_file_location(
        "qiyuan_foraging_env",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ForagingEnv
