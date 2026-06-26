from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from gwt_agent.core.types import TraceEnvelope, TraceStep


class TraceLogger:
    """Append-only JSONL logger for timestamp-level workspace traces."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def log(self, step: TraceStep) -> None:
        if not self.path:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(step.to_dict(), ensure_ascii=True) + "\n")

    def log_envelope(self, envelope: TraceEnvelope) -> None:
        if not self.path:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope.to_dict(), ensure_ascii=True) + "\n")
