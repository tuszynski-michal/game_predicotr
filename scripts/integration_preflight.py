"""Read-only preflight before merging a work branch into ``main`` (TASK-1031).

Reports, without changing anything (no fetch, no checkout, no worktree writes):

* ahead/behind of the branch against ``main`` and whether a fast-forward is possible;
* ``main`` against ``origin/main`` (ahead/behind, no fetch: the remote ref may be stale);
* whether the worktree of the branch and the checkout of ``main`` have uncommitted changes;
* what the branch adds: ``ai_docs/tasks/**/NNNN-*.md`` task files, ``D-NNN`` headings in
  ``ai_docs/process/decisions/DECISION_LOG_*.md``, ``vX.Y.N`` commit subject prefixes and
  ``services/api/alembic/versions/NNNN_*.py`` migrations;
* number collisions of those additions with ``main`` (tip tree and history) and with the
  additions of other local branches that are not merged into ``main``;
* an informational list of collisions that other unmerged branches have with ``main``
  (not caused by the checked branch, but they will surface when those branches merge);
* a reminder when the branch adds a migration: merge only after the operator migrated.

A task, decision or migration is "added" when its file name (or ``D-NNN`` number) is absent
from the merge-base tree. A collision is the same number with a different file name,
heading or commit. Identical items (the same file name, heading or commit hash) are the
same item and never collide.

Usage: ``integration_preflight.py [BRANCH] [--base main] [--remote origin] [--json]``.
BRANCH defaults to the currently checked-out branch. Exit code 0 always, except 1 on a git
error (unknown branch, detached HEAD without a branch argument, unrelated histories, ...).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]

TASKS_PREFIX = "ai_docs/tasks"
DECISIONS_PREFIX = "ai_docs/process/decisions"
MIGRATIONS_PREFIX = "services/api/alembic/versions"

TASK_RE = re.compile(r"^ai_docs/tasks/(?:.+/)?(\d{4})-[^/]+\.md$")
DECISION_FILE_RE = re.compile(r"^ai_docs/process/decisions/DECISION_LOG_[^/]+\.md$")
DECISION_HEADING_RE = re.compile(r"^##[ \t]+(D-\d+)\b.*$", re.MULTILINE)
MIGRATION_RE = re.compile(r"^services/api/alembic/versions/(\d{4})_[^/]+\.py$")
VERSION_RE = re.compile(r"^(v\d+\.\d+\.\d+)\b")

MAX_DIRTY_LISTED = 20

# kind -> identity/display items per number: identity decides "same item", display is reported
Item = tuple[str, str]
Claims = dict[str, list[Item]]


class GitError(Exception):
    """A git command failed or the repository state cannot be analysed."""


@dataclass
class Collision:
    kind: str
    key: str
    owner: str
    owner_items: list[str]
    against: str
    against_items: list[str]


@dataclass
class WorktreeState:
    checked_out: bool
    path: str | None = None
    dirty: bool | None = None
    entries: list[str] = field(default_factory=list)
    entry_count: int = 0
    tracked_count: int = 0
    untracked_count: int = 0


@dataclass
class KindClaims:
    tasks: Claims = field(default_factory=dict)
    decisions: Claims = field(default_factory=dict)
    versions: Claims = field(default_factory=dict)
    migrations: Claims = field(default_factory=dict)

    def by_kind(self) -> dict[str, Claims]:
        return {
            "TASK": self.tasks,
            "D": self.decisions,
            "version": self.versions,
            "migration": self.migrations,
        }


# ------------------------------------------------------------------------------ git


def git(root: Path, *args: str, allow_failure: bool = False) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if result.returncode != 0 and not allow_failure:
        detail = (result.stderr or result.stdout).strip()
        raise GitError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout if result.returncode == 0 else ""


def git_ok(root: Path, *args: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    return result.returncode == 0


def local_branches(root: Path) -> list[str]:
    out = git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads")
    return [line for line in out.splitlines() if line]


def current_branch(root: Path) -> str:
    out = git(root, "symbolic-ref", "--short", "-q", "HEAD", allow_failure=True).strip()
    if not out:
        raise GitError("HEAD is detached; pass the branch name explicitly")
    return out


def require_branch(root: Path, name: str) -> str:
    if not git_ok(root, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}^{{commit}}"):
        raise GitError(f"no local branch {name!r}")
    return git(root, "rev-parse", f"refs/heads/{name}").strip()


def left_right(root: Path, left: str, right: str) -> tuple[int, int]:
    """``(commits only in left, commits only in right)``."""
    out = git(root, "rev-list", "--left-right", "--count", f"{left}...{right}").split()
    return int(out[0]), int(out[1])


def tree_paths(root: Path, ref: str, prefix: str) -> list[str]:
    out = git(root, "ls-tree", "-r", "--name-only", "-z", ref, "--", prefix)
    return [path for path in out.split("\0") if path]


# --------------------------------------------------------------------------- claims


def numbered_files(paths: Sequence[str], pattern: re.Pattern[str]) -> Claims:
    """Group ``paths`` by the number captured by ``pattern``; identity is the file name."""
    claims: Claims = {}
    for path in paths:
        match = pattern.match(path)
        if match:
            claims.setdefault(match.group(1), []).append((path.rsplit("/", 1)[-1], path))
    return claims


def decision_headings(root: Path, ref: str) -> Claims:
    claims: Claims = {}
    for path in tree_paths(root, ref, DECISIONS_PREFIX):
        if not DECISION_FILE_RE.match(path):
            continue
        text = git(root, "show", f"{ref}:{path}")
        for match in DECISION_HEADING_RE.finditer(text):
            heading = match.group(0).strip()
            claims.setdefault(match.group(1), []).append((heading, f"{path}: {heading}"))
    return claims


def tree_claims(root: Path, ref: str) -> KindClaims:
    """Tasks, decisions and migrations present in the tree of ``ref``."""
    return KindClaims(
        tasks=numbered_files(tree_paths(root, ref, TASKS_PREFIX), TASK_RE),
        decisions=decision_headings(root, ref),
        migrations=numbered_files(tree_paths(root, ref, MIGRATIONS_PREFIX), MIGRATION_RE),
    )


def version_claims(root: Path, revision: str) -> Claims:
    """``vX.Y.N`` subject prefixes of the commits in ``revision`` (a rev or a range)."""
    claims: Claims = {}
    out = git(root, "log", "--format=%H %s", revision)
    for line in out.splitlines():
        commit, _, subject = line.partition(" ")
        match = VERSION_RE.match(subject)
        if match:
            claims.setdefault(match.group(1), []).append((commit, f"{commit[:8]} {subject}"))
    return claims


def subtract(claims: Claims, known: Claims) -> Claims:
    """Items of ``claims`` whose identity is not in ``known`` for the same number."""
    result: Claims = {}
    for key, items in claims.items():
        seen = {identity for identity, _ in known.get(key, [])}
        kept = [item for item in items if item[0] not in seen]
        if kept:
            result[key] = kept
    return result


def added_by(root: Path, ref: str, base: str, merge_base: str) -> KindClaims:
    """What ``ref`` adds on top of ``merge_base``; versions come from ``base..ref``."""
    tip = tree_claims(root, ref)
    old = tree_claims(root, merge_base)
    return KindClaims(
        tasks=subtract(tip.tasks, old.tasks),
        decisions=subtract(tip.decisions, old.decisions),
        versions=version_claims(root, f"{base}..{ref}"),
        migrations=subtract(tip.migrations, old.migrations),
    )


def occupied_on(root: Path, ref: str) -> KindClaims:
    """Everything taken on ``ref``: tree contents and the full commit history."""
    claims = tree_claims(root, ref)
    claims.versions = version_claims(root, ref)
    return claims


def find_collisions(
    owner: str, added: KindClaims, against: str, taken: KindClaims
) -> list[Collision]:
    found: list[Collision] = []
    taken_by_kind = taken.by_kind()
    for kind, claims in added.by_kind().items():
        for key in sorted(claims):
            own_ids = {identity for identity, _ in claims[key]}
            others = [item for item in taken_by_kind[kind].get(key, []) if item[0] not in own_ids]
            if others:
                found.append(
                    Collision(
                        kind=kind,
                        key=key,
                        owner=owner,
                        owner_items=[display for _, display in claims[key]],
                        against=against,
                        against_items=[display for _, display in others],
                    )
                )
    return found


# ------------------------------------------------------------------------ worktrees


def worktree_paths(root: Path) -> dict[str, Path]:
    """Branch name -> path of the worktree where it is checked out."""
    out = git(root, "worktree", "list", "--porcelain")
    found: dict[str, Path] = {}
    for block in out.split("\n\n"):
        path: str | None = None
        branch: str | None = None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = line.removeprefix("worktree ")
            elif line.startswith("branch refs/heads/"):
                branch = line.removeprefix("branch refs/heads/")
        if path is not None and branch is not None:
            found[branch] = Path(path)
    return found


def worktree_state(paths: dict[str, Path], branch: str) -> WorktreeState:
    path = paths.get(branch)
    if path is None:
        return WorktreeState(checked_out=False)
    if not path.is_dir():
        return WorktreeState(checked_out=True, path=str(path))
    out = git(path, "status", "--porcelain", "--untracked-files=normal")
    entries = [line for line in out.splitlines() if line.strip()]
    return WorktreeState(
        checked_out=True,
        path=str(path),
        dirty=bool(entries),
        entries=entries[:MAX_DIRTY_LISTED],
        entry_count=len(entries),
        tracked_count=sum(1 for line in entries if not line.startswith("??")),
        untracked_count=sum(1 for line in entries if line.startswith("??")),
    )


# ------------------------------------------------------------------------ analysis


def analyse(root: Path, branch: str, base: str, remote: str) -> dict[str, object]:
    base_tip = require_branch(root, base)
    branch_tip = require_branch(root, branch)
    if branch == base:
        raise GitError(f"branch {branch!r} is the base branch; nothing to merge")
    merge_base_out = git(root, "merge-base", base, branch, allow_failure=True).strip()
    if not merge_base_out:
        raise GitError(f"no merge base between {base!r} and {branch!r} (unrelated histories)")
    behind, ahead = left_right(root, base, branch)

    remote_ref = f"{remote}/{base}"
    origin: dict[str, object] = {"ref": remote_ref, "present": False}
    if git_ok(root, "rev-parse", "--verify", "--quiet", f"refs/remotes/{remote_ref}^{{commit}}"):
        remote_only, base_only = left_right(root, f"refs/remotes/{remote_ref}", base_tip)
        origin = {
            "ref": remote_ref,
            "present": True,
            "base_ahead": base_only,
            "base_behind": remote_only,
        }
    origin["note"] = "no fetch was performed; the remote ref may be stale"

    paths = worktree_paths(root)
    worktrees = {
        "branch": asdict(worktree_state(paths, branch)),
        "base": asdict(worktree_state(paths, base)),
    }

    added = added_by(root, branch, base, merge_base_out)
    collisions = find_collisions(branch, added, base, occupied_on(root, base))

    others: list[dict[str, object]] = []
    informational: list[Collision] = []
    base_taken = occupied_on(root, base)
    for other in local_branches(root):
        if other in (branch, base):
            continue
        other_ahead = left_right(root, base, other)[1]
        if other_ahead == 0:
            continue  # already merged into main
        contained = git_ok(root, "merge-base", "--is-ancestor", other, branch)
        record: dict[str, object] = {"branch": other, "ahead": other_ahead}
        record["contained_in_branch"] = contained
        if not contained:
            other_mb = git(root, "merge-base", base, other, allow_failure=True).strip()
            if other_mb:
                other_added = added_by(root, other, base, other_mb)
                collisions.extend(find_collisions(branch, added, other, other_added))
                informational.extend(find_collisions(other, other_added, base, base_taken))
        others.append(record)

    migrations_added = sorted(
        display for items in added.migrations.values() for _, display in items
    )
    result: dict[str, object] = {
        "branch": branch,
        "base": base,
        "branch_tip": branch_tip,
        "base_tip": base_tip,
        "merge_base": merge_base_out,
        "history": {
            "ahead": ahead,
            "behind": behind,
            "fast_forward": behind == 0,
            "nothing_to_merge": ahead == 0,
        },
        "origin": origin,
        "worktrees": worktrees,
        "added": {
            kind: {key: [display for _, display in items] for key, items in claims.items()}
            for kind, claims in added.by_kind().items()
        },
        "migrations": {
            "added": migrations_added,
            "needs_operator_migration_before_merge": bool(migrations_added),
        },
        "collisions": [asdict(item) for item in collisions],
        "other_branches": others,
        "other_branch_collisions_with_base": [asdict(item) for item in informational],
    }
    result["warnings"] = build_warnings(result)
    return result


def build_warnings(report: dict[str, object]) -> list[str]:
    history = _dict(report["history"])
    origin = _dict(report["origin"])
    worktrees = _dict(report["worktrees"])
    migrations = _dict(report["migrations"])
    branch = str(report["branch"])
    base = str(report["base"])
    warnings: list[str] = []
    if history["nothing_to_merge"]:
        warnings.append(f"{branch} has no commits beyond {base}: nothing to merge")
    if not history["fast_forward"]:
        warnings.append(
            f"fast-forward impossible: {branch} is {history['behind']} commit(s) behind {base}; "
            f"run `git merge {base}` in the {branch} worktree first"
        )
    collisions = report["collisions"]
    if isinstance(collisions, list) and collisions:
        warnings.append(f"{len(collisions)} number collision(s) with {base} or other branches")
    if migrations["needs_operator_migration_before_merge"]:
        warnings.append(
            "branch adds a migration: needs operator migration before merge "
            "(do not merge code that needs an unapplied migration into the running checkout)"
        )
    for label in ("branch", "base"):
        state = _dict(worktrees[label])
        name = branch if label == "branch" else base
        if state["tracked_count"]:
            warnings.append(
                f"worktree of {name} has {state['tracked_count']} uncommitted tracked change(s): "
                "do not overwrite or commit foreign changes"
            )
        if label == "branch" and state["untracked_count"]:
            warnings.append(
                f"worktree of {name} has {state['untracked_count']} untracked path(s): "
                "commit them with the task or leave them out knowingly"
            )
    if origin["present"] and origin["base_ahead"]:
        warnings.append(
            f"{base} is {origin['base_ahead']} commit(s) ahead of {origin['ref']} (unpushed)"
        )
    if origin["present"] and origin["base_behind"]:
        warnings.append(
            f"{base} is {origin['base_behind']} commit(s) behind {origin['ref']} "
            "(remote moved; consider the operator fetching)"
        )
    return warnings


def _dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return {str(key): item for key, item in value.items()}


# --------------------------------------------------------------------------- output


def render_text(report: dict[str, object]) -> str:
    history = _dict(report["history"])
    origin = _dict(report["origin"])
    worktrees = _dict(report["worktrees"])
    migrations = _dict(report["migrations"])
    branch = str(report["branch"])
    base = str(report["base"])
    lines = [
        f"integration_preflight: {branch} -> {base} (read-only, no fetch)",
        f"  merge base: {str(report['merge_base'])[:8]}; "
        f"{branch} tip {str(report['branch_tip'])[:8]}; {base} tip {str(report['base_tip'])[:8]}",
        "",
        "History",
        f"  {branch} is ahead of {base} by {history['ahead']}, behind by {history['behind']}",
        f"  fast-forward into {base}: "
        + ("possible" if history["fast_forward"] else "NOT possible (merge main first)"),
    ]
    if origin["present"]:
        lines.append(
            f"  {base} vs {origin['ref']}: ahead {origin['base_ahead']}, "
            f"behind {origin['base_behind']} ({origin['note']})"
        )
    else:
        lines.append(f"  {origin['ref']} not found locally ({origin['note']})")
    lines += ["", "Worktrees"]
    for label, name in (("branch", branch), ("base", base)):
        state = _dict(worktrees[label])
        if not state["checked_out"]:
            lines.append(f"  {name}: not checked out in any worktree")
        elif state["dirty"] is None:
            lines.append(f"  {name}: {state['path']} (directory missing)")
        elif state["dirty"]:
            lines.append(
                f"  {name}: {state['path']} DIRTY ({state['tracked_count']} tracked, "
                f"{state['untracked_count']} untracked)"
            )
            entries = state["entries"]
            if isinstance(entries, list):
                lines.extend(f"    {entry}" for entry in entries)
        else:
            lines.append(f"  {name}: {state['path']} clean")
    lines += ["", f"Added by {branch}"]
    added = _dict(report["added"])
    for kind in ("TASK", "D", "version", "migration"):
        claims = _dict(added[kind])
        shown = ", ".join(sorted(claims)) or "none"
        lines.append(f"  {kind}: {shown}")
    lines += ["", "Migrations"]
    migration_files = migrations["added"]
    if isinstance(migration_files, list) and migration_files:
        lines += [f"  adds {item}" for item in migration_files]
        lines.append("  needs operator migration before merge")
    else:
        lines.append("  no migration added")
    collisions = report["collisions"]
    lines += ["", "Number collisions"]
    if isinstance(collisions, list) and collisions:
        for item in collisions:
            lines.extend(_collision_lines(item))
    else:
        lines.append("  none")
    others = report["other_branches"]
    lines += ["", "Other unmerged local branches"]
    if isinstance(others, list) and others:
        for other in others:
            note = " (contained in the branch)" if other["contained_in_branch"] else ""
            lines.append(f"  {other['branch']}: {other['ahead']} commit(s) ahead of {base}{note}")
    else:
        lines.append("  none")
    informational = report["other_branch_collisions_with_base"]
    if isinstance(informational, list) and informational:
        lines += ["", f"Informational: collisions of other branches with {base}"]
        for item in informational:
            lines.append(f"  {item['kind']} {item['key']}: {item['owner']} vs {item['against']}")
        lines.append("  (details: --json, key other_branch_collisions_with_base)")
    lines += ["", "Summary"]
    warnings = report["warnings"]
    if isinstance(warnings, list) and warnings:
        lines += [f"  WARN {warning}" for warning in warnings]
    else:
        lines.append("  no warnings: fast-forward possible, no collisions, no migration")
    lines.append("  the operator still has to accept the result and consent to the merge")
    return "\n".join(lines)


def _collision_lines(item: dict[str, object]) -> list[str]:
    owner_items = item["owner_items"]
    against_items = item["against_items"]
    assert isinstance(owner_items, list) and isinstance(against_items, list)
    lines = [f"  {item['kind']} {item['key']}: {item['owner']} vs {item['against']}"]
    lines += [f"    {item['owner']}: {text}" for text in owner_items]
    lines += [f"    {item['against']}: {text}" for text in against_items]
    return lines


# ----------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("branch", nargs="?", default=None, help="work branch (default: current)")
    parser.add_argument("--base", default="main", help="integration branch (default: main)")
    parser.add_argument("--remote", default="origin", help="remote name (default: origin)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    root = Path(os.path.abspath(args.root))
    try:
        branch = args.branch or current_branch(root)
        report = analyse(root, branch, args.base, args.remote)
    except GitError as error:
        print(f"integration_preflight: ERROR {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
