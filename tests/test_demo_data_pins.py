"""Golden-pin drift tests for the committed Phase 4b demo payload.

Cheap by construction: these read the committed JSON under ``web/static/data/``
and compare against ``scripts.figures.EXPECTED_LIVE``. Nothing is re-run, no
baseline is regenerated. The equality is EXACT float equality — the same
contract as ``python -m scripts.figures --check`` — so the demo can never
silently disagree with the paper's numbers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts import figures
from scripts.export_demo_data import DEMO_CELLS

DATA = Path(__file__).resolve().parents[1] / "web" / "static" / "data"

# The two cells with a committed ``explanations_eval.json`` (Stage 4 judging
# was only paid for on clean@23 and defectors@7).
CELLS_WITH_EXPLANATIONS = {"clean", "defectors"}

_KEY_RE = re.compile(r"sk-ant-")


def _meta(slug: str) -> dict[str, Any]:
    return json.loads((DATA / slug / "meta.json").read_text())  # type: ignore[no-any-return]


def test_all_cells_exported() -> None:
    for slug in sorted(DEMO_CELLS):
        for name in ("meta.json", "ticks.json", "messages.json"):
            assert (DATA / slug / name).is_file(), f"missing {slug}/{name}"
        expl = DATA / slug / "explanations.json"
        assert expl.is_file() == (slug in CELLS_WITH_EXPLANATIONS), (
            f"{slug}/explanations.json presence ({expl.is_file()}) disagrees with the "
            f"committed judging artifacts {sorted(CELLS_WITH_EXPLANATIONS)}"
        )


def test_live_numbers_match_golden_pins() -> None:
    for slug, (cell, seed) in sorted(DEMO_CELLS.items()):
        meta = _meta(slug)
        want = figures.EXPECTED_LIVE[(cell, seed)]
        for key in ("served_load_fraction", "gini_welfare"):
            got = meta["live"][key]
            assert got == want[key], f"{slug}: live {key} = {got!r}, pinned {want[key]!r}"


def test_clean_seed_spread_matches_pins() -> None:
    spread = _meta("clean")["cleanSeedSpread"]
    cell = DEMO_CELLS["clean"][0]
    assert sorted(spread) == ["1", "7"]
    for seed in (1, 7):
        want = figures.EXPECTED_LIVE[(cell, seed)]["served_load_fraction"]
        assert spread[str(seed)] == want, f"clean seed {seed}: {spread[str(seed)]!r} != {want!r}"


def test_lp_is_ceiling() -> None:
    for slug in sorted(DEMO_CELLS):
        meta = _meta(slug)
        lp = meta["baselines"]["lp_optimal"]["served_load_fraction"]
        live = meta["live"]["served_load_fraction"]
        assert lp >= live - 1e-9, f"{slug}: LP {lp!r} below live {live!r}"
        for method, m in meta["baselines"].items():
            if method == "lp_optimal":
                continue
            assert (
                lp >= m["served_load_fraction"] - 1e-9
            ), f"{slug}: LP {lp!r} below {method} {m['served_load_fraction']!r}"


def test_no_secrets_or_caches_in_data() -> None:
    files = [p for p in DATA.rglob("*") if p.is_file()]
    assert files, f"no files under {DATA}"
    for p in files:
        parts = set(p.relative_to(DATA).parts)
        assert not (parts & {"llm_cache", "judge_cache"}), f"cache material at {p}"
        assert not _KEY_RE.search(p.read_text(errors="replace")), f"key-shaped string in {p}"
