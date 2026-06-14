"""Append-only memory stream with top-K retrieval.

Adapted from Park et al., *Generative Agents* (arXiv:2304.03442) §A.1
(memory stream). The retrieval score is a weighted blend of recency,
importance, and (optionally) similarity. Similarity defaults to 1.0 when
no embedder is configured, so unit tests need no model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

MemoryKind = Literal["obs", "msg_sent", "msg_recv", "transfer_outcome", "reflection"]


@dataclass(frozen=True)
class MemoryEntry:
    t: datetime
    kind: MemoryKind
    content: dict[str, Any]
    nl: str
    importance: float


@dataclass
class MemoryStream:
    _entries: list[MemoryEntry] = field(default_factory=list)
    alpha_recency: float = 0.4
    beta_importance: float = 0.4
    gamma_similarity: float = 0.2

    @property
    def entries(self) -> tuple[MemoryEntry, ...]:
        """Read-only view; tests assert append-only by trying to .append() this."""
        return tuple(self._entries)

    def append(self, e: MemoryEntry) -> None:
        self._entries.append(e)

    def top_k(
        self,
        now: datetime,
        k: int,
        query_nl: str | None = None,
        recency_half_life_hours: float = 4.0,
    ) -> list[MemoryEntry]:
        if not self._entries:
            return []

        def score(e: MemoryEntry) -> float:
            age_hours = max(0.0, (now - e.t).total_seconds() / 3600.0)
            recency: float = 0.5 ** (age_hours / recency_half_life_hours)
            importance = e.importance / 10.0
            similarity = _cosine_or_one(query_nl, e.nl)
            return float(
                self.alpha_recency * recency
                + self.beta_importance * importance
                + self.gamma_similarity * similarity
            )

        ranked = sorted(self._entries, key=score, reverse=True)
        return ranked[: max(0, k)]

    def write_jsonl(self, path: Path) -> None:
        path = Path(path)
        with path.open("w", encoding="utf-8") as f:
            for e in self._entries:
                f.write(
                    json.dumps(
                        {
                            "t": e.t.isoformat(),
                            "kind": e.kind,
                            "content": e.content,
                            "nl": e.nl,
                            "importance": e.importance,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    @staticmethod
    def from_jsonl(path: Path) -> MemoryStream:
        s = MemoryStream()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            s.append(
                MemoryEntry(
                    t=datetime.fromisoformat(d["t"]),
                    kind=d["kind"],
                    content=d["content"],
                    nl=d["nl"],
                    importance=float(d["importance"]),
                )
            )
        return s


def _cosine_or_one(query: str | None, text: str) -> float:
    """No embedder in v0; similarity is identity (1.0). Hook for Phase 3 to swap in."""
    del query, text
    return 1.0
