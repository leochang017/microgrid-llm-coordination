"""Tests for scripts/run.py's reference-cell naming + overwrite guard (C6-4).

`--reference-cell` + `--set seed=X` (instead of the dedicated `--seed` flag)
used to mislabel the committed directory (no `__seedN` suffix even though the
engine ran at the overridden seed), and `JsonlLogger` opens state/events files
in "w" mode with no existence check, so a stale directory name could silently
truncate a previously-committed artifact.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.run import (
    _check_reference_cell_writable,
    _reference_cell_dirname,
    _seed_was_overridden,
)


def test_reference_cell_dirname_suffixes_only_when_seed_overridden() -> None:
    assert _reference_cell_dirname("clean", seed_overridden=False, seed=23) == "clean"
    assert _reference_cell_dirname("clean", seed_overridden=True, seed=99) == "clean__seed99"


def test_seed_was_overridden_detects_dedicated_flag() -> None:
    assert _seed_was_overridden(cli_seed=99, set_specs=[]) is True
    assert _seed_was_overridden(cli_seed=None, set_specs=[]) is False


def test_seed_was_overridden_detects_set_seed_override() -> None:
    # The bug: --set seed=... is an equally valid way to change the seed but
    # was invisible to the old args.seed-only check.
    assert _seed_was_overridden(cli_seed=None, set_specs=["seed=99"]) is True
    assert (
        _seed_was_overridden(cli_seed=None, set_specs=["failure_modes.defector_fraction=0.4"])
        is False
    )
    assert _seed_was_overridden(cli_seed=None, set_specs=[" seed = 99"]) is True


def test_check_reference_cell_writable_refuses_nonempty_dir_without_force(tmp_path: Path) -> None:
    run_dir = tmp_path / "cell"
    run_dir.mkdir()
    (run_dir / "state.jsonl").write_text("committed data")
    with pytest.raises(SystemExit):
        _check_reference_cell_writable(run_dir, force=False)
    # state.jsonl must survive the refusal (nothing was truncated).
    assert (run_dir / "state.jsonl").read_text() == "committed data"
    _check_reference_cell_writable(run_dir, force=True)  # explicit override is allowed


def test_check_reference_cell_writable_allows_empty_or_missing_dir(tmp_path: Path) -> None:
    _check_reference_cell_writable(tmp_path / "does_not_exist", force=False)
    empty = tmp_path / "empty"
    empty.mkdir()
    _check_reference_cell_writable(empty, force=False)
