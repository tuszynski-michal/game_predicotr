from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "integration_preflight_test_module", REPOSITORY_ROOT / "scripts" / "integration_preflight.py"
)
assert _SPEC is not None and _SPEC.loader is not None
preflight: ModuleType = importlib.util.module_from_spec(_SPEC)
# dataclasses resolve annotations through sys.modules, so register before executing.
sys.modules[_SPEC.name] = preflight
_SPEC.loader.exec_module(preflight)

DECISIONS = "ai_docs/process/decisions/DECISION_LOG_2026.md"
MIGRATION_DIR = "services/api/alembic/versions"


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            *args,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=True,
    )
    return result.stdout.strip()


def commit(root: Path, message: str, files: dict[str, str | None] | None = None) -> str:
    """Write (or delete, for ``None``) files and commit; returns the commit hash."""
    for relative, text in (files or {}).items():
        path = root / relative
        if text is None:
            run_git(root, "rm", "-q", "--", relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "--allow-empty", "-m", message)
    return run_git(root, "rev-parse", "HEAD")


def switch(root: Path, branch: str, create_from: str | None = None) -> None:
    if create_from is None:
        run_git(root, "checkout", "-q", branch)
    else:
        run_git(root, "checkout", "-q", "-b", branch, create_from)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """``main`` with one base commit, checked out on ``main``."""
    run_git(tmp_path, "init", "-q", "-b", "main")
    commit(
        tmp_path,
        "v1.0.1 - base",
        {
            "ai_docs/tasks/0050-old.md": "# old\n",
            DECISIONS: "# Decisions\n\n## D-001 — Old\n\nTekst.\n",
            f"{MIGRATION_DIR}/0001_init.py": "# init\n",
        },
    )
    return tmp_path


def report(root: Path, branch: str | None = None) -> dict[str, object]:
    args = ["--root", str(root), "--json"] + ([branch] if branch else [])
    process = subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts" / "integration_preflight.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    parsed = json.loads(process.stdout)
    assert isinstance(parsed, dict)
    return parsed


def collision_keys(data: dict[str, object]) -> set[tuple[str, str, str]]:
    collisions = data["collisions"]
    assert isinstance(collisions, list)
    return {(item["kind"], item["key"], item["against"]) for item in collisions}


# ------------------------------------------------------------------ fast-forward


def test_fast_forward_possible(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work", {"notes.txt": "a\n"})
    data = report(repo)
    history = data["history"]
    assert isinstance(history, dict)
    assert history["ahead"] == 1
    assert history["behind"] == 0
    assert history["fast_forward"] is True
    assert data["branch"] == "feat/work"
    assert data["collisions"] == []
    assert data["warnings"] == []


def test_fast_forward_impossible_when_main_moved(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work", {"notes.txt": "a\n"})
    switch(repo, "main")
    commit(repo, "v1.0.3 - main moved", {"other.txt": "b\n"})
    data = report(repo, "feat/work")
    history = data["history"]
    assert isinstance(history, dict)
    assert (history["ahead"], history["behind"]) == (1, 1)
    assert history["fast_forward"] is False
    warnings = data["warnings"]
    assert isinstance(warnings, list)
    assert any("fast-forward impossible" in item and "git merge main" in item for item in warnings)


def test_branch_without_commits_has_nothing_to_merge(repo: Path) -> None:
    switch(repo, "feat/empty", "main")
    data = report(repo)
    history = data["history"]
    assert isinstance(history, dict)
    assert history["nothing_to_merge"] is True
    warnings = data["warnings"]
    assert isinstance(warnings, list)
    assert any("nothing to merge" in item for item in warnings)


# --------------------------------------------------------------------- collisions


def test_task_collision_with_main(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - task", {"ai_docs/tasks/0100-mine.md": "# mine\n"})
    switch(repo, "main")
    commit(repo, "v1.0.3 - task on main", {"ai_docs/tasks/completed/0100-theirs.md": "# theirs\n"})
    data = report(repo, "feat/work")
    assert ("TASK", "0100", "main") in collision_keys(data)
    collisions = data["collisions"]
    assert isinstance(collisions, list)
    item = next(entry for entry in collisions if entry["kind"] == "TASK")
    assert item["owner_items"] == ["ai_docs/tasks/0100-mine.md"]
    assert item["against_items"] == ["ai_docs/tasks/completed/0100-theirs.md"]


def test_moved_or_shared_task_is_not_a_collision(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(
        repo,
        "v1.0.2 - move task to completed",
        {"ai_docs/tasks/0050-old.md": None, "ai_docs/tasks/completed/0050-old.md": "# old\n"},
    )
    switch(repo, "main")
    commit(repo, "v1.0.3 - main touches it", {"ai_docs/tasks/0050-old.md": "# old v2\n"})
    data = report(repo, "feat/work")
    assert collision_keys(data) == set()
    added = data["added"]
    assert isinstance(added, dict)
    assert added["TASK"] == {}


def test_task_collision_with_other_unmerged_branch(repo: Path) -> None:
    switch(repo, "feat/other", "main")
    commit(repo, "v1.0.2 - other task", {"ai_docs/tasks/0200-other.md": "# other\n"})
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.3 - my task", {"ai_docs/tasks/0200-mine.md": "# mine\n"})
    data = report(repo, "feat/work")
    assert ("TASK", "0200", "feat/other") in collision_keys(data)
    others = data["other_branches"]
    assert isinstance(others, list)
    assert [entry["branch"] for entry in others] == ["feat/other"]


def test_decision_collision(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(
        repo,
        "v1.0.2 - decision",
        {DECISIONS: "# Decisions\n\n## D-002 — Moja\n\nA.\n\n## D-001 — Old\n\nTekst.\n"},
    )
    switch(repo, "main")
    commit(
        repo,
        "v1.0.3 - decision on main",
        {DECISIONS: "# Decisions\n\n## D-002 — Cudza\n\nB.\n\n## D-001 — Old\n\nTekst.\n"},
    )
    data = report(repo, "feat/work")
    assert collision_keys(data) == {("D", "D-002", "main")}
    collisions = data["collisions"]
    assert isinstance(collisions, list)
    assert "Moja" in collisions[0]["owner_items"][0]
    assert "Cudza" in collisions[0]["against_items"][0]


def test_level_three_decision_heading_collision(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - decision", {DECISIONS: "# Decisions\n\n### D-003 — Moja\n\nA.\n"})
    switch(repo, "main")
    commit(repo, "v1.0.3 - decision", {DECISIONS: "# Decisions\n\n## D-003 — Cudza\n\nB.\n"})
    assert ("D", "D-003", "main") in collision_keys(report(repo, "feat/work"))


def test_decision_without_collision(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(
        repo,
        "v1.0.2 - decision",
        {DECISIONS: "# Decisions\n\n## D-002 — Moja\n\n## D-001 — Old\n\nTekst.\n"},
    )
    data = report(repo, "feat/work")
    assert data["collisions"] == []
    added = data["added"]
    assert isinstance(added, dict)
    assert list(added["D"]) == ["D-002"]


def test_version_collision_with_main(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - mine")
    commit(repo, "v1.0.3 - mine too")
    switch(repo, "main")
    commit(repo, "v1.0.2 - theirs", {"x.txt": "x\n"})
    data = report(repo, "feat/work")
    assert collision_keys(data) == {("version", "v1.0.2", "main")}
    added = data["added"]
    assert isinstance(added, dict)
    assert sorted(added["version"]) == ["v1.0.2", "v1.0.3"]


def test_version_collision_with_other_branch_and_shared_commit_is_ignored(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    shared = commit(repo, "v1.0.2 - shared")
    switch(repo, "feat/other", shared)
    commit(repo, "v1.0.3 - other only", {"o.txt": "o\n"})
    switch(repo, "feat/work")
    commit(repo, "v1.0.3 - mine", {"m.txt": "m\n"})
    data = report(repo, "feat/work")
    # v1.0.2 is the same commit on both branches (no collision), v1.0.3 differs.
    assert collision_keys(data) == {("version", "v1.0.3", "feat/other")}


def test_branch_contained_in_work_branch_is_not_a_collision(repo: Path) -> None:
    switch(repo, "feat/base", "main")
    commit(repo, "v1.0.2 - base work", {"ai_docs/tasks/0300-a.md": "# a\n"})
    switch(repo, "feat/work", "feat/base")
    commit(repo, "v1.0.3 - more work")
    data = report(repo, "feat/work")
    assert data["collisions"] == []
    others = data["other_branches"]
    assert isinstance(others, list)
    assert others == [{"branch": "feat/base", "ahead": 1, "contained_in_branch": True}]


def test_merged_branches_are_not_listed(repo: Path) -> None:
    switch(repo, "feat/done", "main")
    commit(repo, "v1.0.2 - done", {"d.txt": "d\n"})
    switch(repo, "main")
    run_git(repo, "merge", "-q", "--ff-only", "feat/done")
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.3 - work")
    data = report(repo, "feat/work")
    assert data["other_branches"] == []


def test_informational_collisions_of_other_branches_with_main(repo: Path) -> None:
    switch(repo, "feat/other", "main")
    commit(repo, "v1.0.2 - other", {"ai_docs/tasks/0400-other.md": "# o\n"})
    switch(repo, "main")
    commit(repo, "v1.0.3 - main", {"ai_docs/tasks/0400-main.md": "# m\n"})
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.4 - work")
    data = report(repo, "feat/work")
    assert data["collisions"] == []
    informational = data["other_branch_collisions_with_base"]
    assert isinstance(informational, list)
    assert [(item["kind"], item["key"], item["owner"]) for item in informational] == [
        ("TASK", "0400", "feat/other")
    ]


# --------------------------------------------------------------------- migrations


def test_added_migration_needs_operator_migration(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - migration", {f"{MIGRATION_DIR}/0002_add_table.py": "# m\n"})
    data = report(repo)
    migrations = data["migrations"]
    assert isinstance(migrations, dict)
    assert migrations["needs_operator_migration_before_merge"] is True
    assert migrations["added"] == [f"{MIGRATION_DIR}/0002_add_table.py"]
    assert data["collisions"] == []
    warnings = data["warnings"]
    assert isinstance(warnings, list)
    assert any("needs operator migration before merge" in item for item in warnings)


def test_no_migration_means_no_reminder(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - docs", {"README.md": "x\n"})
    data = report(repo)
    migrations = data["migrations"]
    assert isinstance(migrations, dict)
    assert migrations["needs_operator_migration_before_merge"] is False


def test_migration_number_collision(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - my migration", {f"{MIGRATION_DIR}/0002_mine.py": "# m\n"})
    switch(repo, "main")
    commit(repo, "v1.0.3 - their migration", {f"{MIGRATION_DIR}/0002_theirs.py": "# t\n"})
    data = report(repo, "feat/work")
    assert collision_keys(data) == {("migration", "0002", "main")}


# ------------------------------------------------------------------------- origin


def test_main_ahead_of_origin(repo: Path) -> None:
    base = run_git(repo, "rev-parse", "main")
    run_git(repo, "update-ref", "refs/remotes/origin/main", base)
    commit(repo, "v1.0.2 - local main commit", {"a.txt": "a\n"})
    commit(repo, "v1.0.3 - local main commit 2", {"b.txt": "b\n"})
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.4 - work")
    data = report(repo)
    origin = data["origin"]
    assert isinstance(origin, dict)
    assert origin["present"] is True
    assert (origin["base_ahead"], origin["base_behind"]) == (2, 0)
    assert "stale" in str(origin["note"])
    warnings = data["warnings"]
    assert isinstance(warnings, list)
    assert any("2 commit(s) ahead of origin/main" in item for item in warnings)


def test_main_behind_origin(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work")
    remote_tip = commit(repo, "v1.0.3 - work 2")
    run_git(repo, "update-ref", "refs/remotes/origin/main", remote_tip)
    switch(repo, "main")
    data = report(repo, "feat/work")
    origin = data["origin"]
    assert isinstance(origin, dict)
    assert (origin["base_ahead"], origin["base_behind"]) == (0, 2)


def test_missing_origin_ref_is_reported(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work")
    data = report(repo)
    origin = data["origin"]
    assert isinstance(origin, dict)
    assert origin["present"] is False
    assert "stale" in str(origin["note"])


# ------------------------------------------------------------------------ worktree


def test_dirty_branch_worktree_is_reported(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work", {"tracked.txt": "t\n"})
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repo / "scratch.txt").write_text("new\n", encoding="utf-8")
    data = report(repo)
    worktrees = data["worktrees"]
    assert isinstance(worktrees, dict)
    state = worktrees["branch"]
    assert state["dirty"] is True
    assert (state["tracked_count"], state["untracked_count"]) == (1, 1)
    assert worktrees["base"]["checked_out"] is False


def test_clean_worktrees_and_main_checkout_in_other_worktree(repo: Path, tmp_path: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work")
    main_checkout = tmp_path.parent / f"{tmp_path.name}_main_checkout"
    # main cannot be checked out twice: move the work branch away from the primary checkout
    run_git(repo, "checkout", "-q", "--detach")
    run_git(repo, "worktree", "add", "-q", str(main_checkout), "main")
    (main_checkout / "stray.txt").write_text("x\n", encoding="utf-8")
    data = report(repo, "feat/work")
    worktrees = data["worktrees"]
    assert isinstance(worktrees, dict)
    assert worktrees["branch"]["checked_out"] is False
    base_state = worktrees["base"]
    assert Path(base_state["path"]).resolve() == main_checkout.resolve()
    assert base_state["dirty"] is True
    assert base_state["untracked_count"] == 1


def test_clean_worktree(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work")
    data = report(repo)
    worktrees = data["worktrees"]
    assert isinstance(worktrees, dict)
    assert worktrees["branch"]["dirty"] is False
    assert worktrees["branch"]["entries"] == []


# ------------------------------------------------------------------------------ CLI


def test_text_output_and_exit_code_with_collisions(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - mine", {f"{MIGRATION_DIR}/0002_mine.py": "# m\n"})
    switch(repo, "main")
    commit(repo, "v1.0.2 - theirs", {f"{MIGRATION_DIR}/0002_theirs.py": "# t\n"})
    switch(repo, "feat/work")
    assert preflight.main(["--root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "integration_preflight: feat/work -> main" in out
    assert "fast-forward into main: NOT possible" in out
    assert "version v1.0.2: feat/work vs main" in out
    assert "migration 0002: feat/work vs main" in out
    assert "needs operator migration before merge" in out
    assert "no fetch" in out


def test_json_output_is_valid(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work")
    assert preflight.main(["--root", str(repo), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["branch"] == "feat/work"
    assert set(parsed) >= {"history", "origin", "worktrees", "collisions", "migrations", "warnings"}


def test_default_branch_is_the_current_one(repo: Path) -> None:
    switch(repo, "feat/one", "main")
    commit(repo, "v1.0.2 - one")
    switch(repo, "feat/two", "main")
    commit(repo, "v1.0.3 - two")
    assert report(repo)["branch"] == "feat/two"
    assert report(repo, "feat/one")["branch"] == "feat/one"


def test_git_errors_exit_one(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert preflight.main(["--root", str(repo), "no/such-branch"]) == 1
    assert "no local branch" in capsys.readouterr().err
    assert preflight.main(["--root", str(repo), "main"]) == 1
    assert "is the base branch" in capsys.readouterr().err
    run_git(repo, "checkout", "-q", "--detach")
    assert preflight.main(["--root", str(repo)]) == 1
    assert "detached" in capsys.readouterr().err


def test_outside_a_repository_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert preflight.main(["--root", str(tmp_path), "feat/x"]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_is_read_only(repo: Path) -> None:
    switch(repo, "feat/work", "main")
    commit(repo, "v1.0.2 - work", {"ai_docs/tasks/0100-mine.md": "# m\n"})
    (repo / "dirty.txt").write_text("d\n", encoding="utf-8")

    def state() -> tuple[str, str, str, list[str]]:
        files = sorted(
            path.relative_to(repo).as_posix()
            for path in repo.rglob("*")
            if ".git" not in path.relative_to(repo).parts and path.is_file()
        )
        return (
            run_git(repo, "for-each-ref"),
            run_git(repo, "status", "--porcelain"),
            run_git(repo, "rev-parse", "HEAD"),
            files,
        )

    before = state()
    report(repo)
    assert preflight.main(["--root", str(repo)]) == 0
    assert state() == before
