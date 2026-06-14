"""Content-addressed prompt cache.

Cache key = sha256(json({model, system, user, temperature, max_tokens, tools_schema})).
Storage: ``<dir>/<model_name>/<key>.json`` with body {prompt, response, model, ...}.

Lookup order:
1. ``local_dir`` (run-local cache, populated by prior calls in this run/output dir)
2. ``reference_dir`` (in-repo reference_runs/ cache, shipped with the paper)
3. miss — caller hits the API and must call ``put(...)`` afterwards.

Writes are atomic (tmp file + os.replace).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def cache_key(req: dict[str, Any]) -> str:
    blob = json.dumps(
        {
            "model": req["model"],
            "system": req["system"],
            "user": req["user"],
            "temperature": req["temperature"],
            "max_tokens": req["max_tokens"],
            "tools_schema": req.get("tools_schema", []),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class PromptCache:
    local_dir: Path
    reference_dir: Path | None = None

    def get(self, req: dict[str, Any]) -> dict[str, Any] | None:
        key = cache_key(req)
        model = req["model"]
        for root in (self.local_dir, self.reference_dir):
            if root is None:
                continue
            path = Path(root) / model / f"{key}.json"
            if path.exists():
                blob = json.loads(path.read_text(encoding="utf-8"))
                return blob["response"]  # type: ignore[no-any-return]
        return None

    def put(self, req: dict[str, Any], response: dict[str, Any]) -> None:
        key = cache_key(req)
        model = req["model"]
        target_dir = Path(self.local_dir) / model
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{key}.json"
        blob = {
            "model": model,
            "system": req["system"],
            "user": req["user"],
            "temperature": req["temperature"],
            "max_tokens": req["max_tokens"],
            "tools_schema": req.get("tools_schema", []),
            "response": response,
            "t_iso": datetime.now(UTC).isoformat(),
        }
        fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=f".{key}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(blob, f, sort_keys=True, separators=(",", ":"))
            os.replace(tmp_path, target)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_path)
            raise
