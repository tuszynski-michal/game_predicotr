"""Close a task in the rolling-window documentation format (TASK-1030).

Two subcommands automate the manual steps of ``AGENTS.md`` "Po kodowaniu" 3 and 5.
The script never commits and never stages anything except the ``git mv`` of the
task file.

``close TASK-NNNN --title T --version vX.Y.N --done-file F``
    1. resolves the task file as the unique ``ai_docs/tasks/NNNN-*.md`` (active
       directory only; zero or several matches are an error);
    2. sets status ``done`` in the ``## Status`` section and in the YAML front
       matter (``status:`` and, when present, ``last_updated:``);
    3. inserts the full done section from F at the top of the newest
       ``ai_docs/archive/CURRENT_STATE_<year>Q<n>.md``, right under its ``# `` title;
    4. inserts ``- **TASK-NNNN** — T — vX.Y.N — tasks/completed/<file>.md`` as the
       first item of "Ostatnie 10 ukończonych tasków" and deletes items beyond 10;
    5. removes the ``### TASK-NNNN`` pointer (heading and body up to the next
       heading of the same or a higher level) from "Aktywne taski";
    6. ``git mv`` of the task file to ``ai_docs/tasks/completed/``.

``record-hash TASK-NNNN --commit <40-hex hash> [--version vX.Y.N]``
    Run in the commit after the closing one. Matching rules (all must find
    exactly the described target, otherwise nothing is written):

    * window: the single item ``- **TASK-NNNN** — … — vX.Y.N — tasks/completed/F.md``
      whose version has no hash yet (items with ``vX.Y.N / hash`` are ignored, so
      colliding task numbers with recorded hashes do not interfere); ``--version``
      narrows the candidates. It becomes ``vX.Y.N / `<first 8 hex>` — …``;
    * archive: in the newest archive file, the first ``### …TASK-NNNN…`` section
      (from the top, i.e. the newest) that has a line mentioning ``vX.Y.N`` not yet
      followed by `` / ` ``; the first such mention becomes ``vX.Y.N / `<full hash>` ``;
    * task file ``tasks/completed/F.md`` (path taken from the window item): the
      single occurrence of ``Commit: vX.Y.N (hash dopisuje kolejny commit).`` is
      replaced with ``Commit: vX.Y.N / `<full hash>`.`` (a file that already
      carries this exact hash is left alone);
    * the commit must exist in the repository.

After writing, ``check_current_state_window`` and ``check_startup_read_budget`` run
in-process. When one fails, every write and the ``git mv`` are rolled back and the
exit code is 1. ``--dry-run`` (a global option placed before the subcommand)
computes the same change, validates it with both checks on a temporary copy and
prints the plan without touching the repository.

Exit code 0 on success, 1 on any error.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime
import importlib.util
import io
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPTS.parent

STATE_REL = "ai_docs/process/CURRENT_STATE.md"
TASKS_REL = "ai_docs/tasks"
COMPLETED_REL = "ai_docs/tasks/completed"
ARCHIVE_REL = "ai_docs/archive"
BUDGET_COPY = (
    "AGENTS.md",
    "CLAUDE.md",
    "ai_docs/README.md",
    "ai_docs/process/DECISION_LOG.md",
)

ACTIVE_HEADING = "## Aktywne taski"
DONE_HEADING = "## Ostatnie 10 ukończonych tasków"
MAX_DONE = 10
HASH_SHORT = 8

TASK_ID_RE = re.compile(r"^(?:TASK-)?(\d{4})$")
VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+$")
HASH_RE = re.compile(r"^[0-9a-f]{40}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ARCHIVE_NAME_RE = re.compile(r"^CURRENT_STATE_(\d{4})Q([1-4])\.md$")
HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")
STATUS_TOKEN_RE = re.compile(r"^(\s*)`([a-z_]+)`(.*)$", re.DOTALL)
# Older task files write the status without backticks, e.g. "blocked — reason".
BARE_STATUS_RE = re.compile(r"^(\s*)(todo|in_progress|blocked|done)\b(.*)$", re.DOTALL)


class CloseError(Exception):
    """A problem that stops the command before (or while rolling back) any write."""


@dataclass(frozen=True)
class FileChange:
    path: Path
    old: bytes
    new: bytes


@dataclass
class Plan:
    changes: list[FileChange]
    move: tuple[Path, Path] | None
    summary: list[str]
    state_new: bytes
    active_names: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- text


def split_lines(text: str) -> list[str]:
    """Split on ``\\n`` only, keeping endings (``str.splitlines`` also splits on U+2028 etc.)."""
    return LINE_RE.findall(text)


def detect_eol(raw: bytes) -> str:
    return "\r\n" if raw.count(b"\r\n") * 2 > raw.count(b"\n") else "\n"


def bare(line: str) -> str:
    return line.rstrip("\r\n")


def headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """``(index, level, text)`` of every heading outside code fences."""
    found: list[tuple[int, int, str]] = []
    fenced = False
    for number, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = HEADING_RE.match(bare(line))
        if match:
            found.append((number, len(match.group(1)), match.group(2)))
    return found


def block_end(lines: list[str], start: int, level: int) -> int:
    """Index after the block that starts at heading ``start`` of the given level."""
    for number, other_level, _ in headings(lines):
        if number > start and other_level <= level:
            return number
    return len(lines)


def find_section(lines: list[str], heading: str) -> tuple[int, int]:
    """``(start, end)`` of the unique ``##`` section with this exact heading line."""
    level = len(heading) - len(heading.lstrip("#"))
    starts = [
        number
        for number, found_level, text in headings(lines)
        if found_level == level and f"{'#' * level} {text}" == heading
    ]
    if len(starts) != 1:
        raise CloseError(f'expected exactly one section "{heading}", found {len(starts)}')
    return starts[0], block_end(lines, starts[0], level)


def normalise_block(text: str, eol: str) -> str:
    """Strip, unify to ``eol`` and end with exactly one line ending."""
    body = text.lstrip("﻿").replace("\r\n", "\n").strip("\n \t\r")
    if eol != "\n":
        body = body.replace("\n", eol)
    return body + eol


def encode(lines: list[str]) -> bytes:
    return "".join(lines).encode("utf-8")


def decode(raw: bytes) -> list[str]:
    return split_lines(raw.decode("utf-8"))


# ------------------------------------------------------------------------- lookup


def parse_task_id(value: str) -> str:
    match = TASK_ID_RE.match(value.strip())
    if not match:
        raise CloseError(f"task id must look like TASK-1030 or 1030, got: {value!r}")
    return match.group(1)


def check_version(version: str) -> str:
    if not VERSION_RE.match(version):
        raise CloseError(f"version must look like v1.7.378, got: {version!r}")
    return version


def active_task_file(root: Path, number: str) -> Path:
    matches = sorted(path for path in (root / TASKS_REL).glob(f"{number}-*.md") if path.is_file())
    if not matches:
        raise CloseError(f"no active task file {TASKS_REL}/{number}-*.md")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise CloseError(f"several active task files for {number} (resolve the collision): {names}")
    return matches[0]


def active_names(root: Path) -> list[str]:
    return sorted(
        path.name for path in (root / TASKS_REL).glob("[0-9][0-9][0-9][0-9]-*.md") if path.is_file()
    )


def archives_newest_first(root: Path) -> list[Path]:
    candidates: list[tuple[int, int, Path]] = []
    for path in (root / ARCHIVE_REL).glob("CURRENT_STATE_*.md"):
        match = ARCHIVE_NAME_RE.match(path.name)
        if match and path.is_file():
            candidates.append((int(match.group(1)), int(match.group(2)), path))
    if not candidates:
        raise CloseError(f"no archive file {ARCHIVE_REL}/CURRENT_STATE_<year>Q<n>.md")
    return [path for _, _, path in sorted(candidates, reverse=True)]


def newest_archive(root: Path) -> Path:
    return archives_newest_first(root)[0]


def read_state(root: Path) -> tuple[bytes, list[str]]:
    path = root / STATE_REL
    if not path.is_file():
        raise CloseError(f"missing {STATE_REL}")
    raw = path.read_bytes()
    return raw, decode(raw)


# ---------------------------------------------------------------------- task file


def set_task_status_done(raw: bytes, date: str, name: str) -> bytes:
    """Status ``done`` in ``## Status`` and in the front matter; nothing else changes."""
    lines = decode(raw)
    if lines and bare(lines[0]) == "---":
        for number in range(1, len(lines)):
            if bare(lines[number]) == "---":
                for index in range(1, number):
                    text = bare(lines[index])
                    ending = lines[index][len(text) :]
                    if text.startswith("status:"):
                        lines[index] = "status: done" + ending
                    elif text.startswith("last_updated:"):
                        lines[index] = f"last_updated: {date}" + ending
                break
    section = [n for n, level, text in headings(lines) if level == 2 and text == "Status"]
    if len(section) != 1:
        raise CloseError(f'{name}: expected exactly one "## Status" section')
    end = block_end(lines, section[0], 2)
    for index in range(section[0] + 1, end):
        if not bare(lines[index]).strip():
            continue
        match = STATUS_TOKEN_RE.match(lines[index]) or BARE_STATUS_RE.match(lines[index])
        if not match:
            raise CloseError(f"{name}: first line of ## Status is not a status word")
        lines[index] = f"{match.group(1)}`done`{match.group(3)}"
        return encode(lines)
    raise CloseError(f"{name}: ## Status section has no status line")


# ----------------------------------------------------------------------- planning


def move_destination(root: Path, source: Path) -> Path:
    destination = root / COMPLETED_REL / source.name
    if destination.exists():
        raise CloseError(f"{COMPLETED_REL}/{source.name} already exists")
    return destination


def plan_close(
    root: Path, number: str, title: str, version: str, done_text: str, date: str
) -> Plan:
    if not title.strip() or "\n" in title:
        raise CloseError("--title must be a non-empty single line")
    if not DATE_RE.match(date):
        raise CloseError(f"--date must be YYYY-MM-DD, got: {date!r}")
    task_path = active_task_file(root, number)
    destination = move_destination(root, task_path)
    task_old = task_path.read_bytes()
    task_new = set_task_status_done(task_old, date, task_path.name)

    done_lines = [bare(line) for line in split_lines(done_text.lstrip("﻿")) if line.strip()]
    if not done_lines or not re.match(rf"^### TASK-{number}\b.*\(done\)\s*$", done_lines[0]):
        raise CloseError(f"--done-file must start with a heading '### TASK-{number} — … (done)'")
    if not re.search(rf"(?<![\w.]){re.escape(version)}(?!\w)(?!\.\d)", done_text):
        raise CloseError(f"--done-file never mentions {version}; record-hash needs it")

    notes: list[str] = []
    outcome_line = f"Commit: {version} (hash dopisuje kolejny commit)."
    if outcome_line not in task_new.decode("utf-8"):
        notes.append(f'warning: task Outcome has no line "{outcome_line}"; record-hash will fail')

    state_raw, state = read_state(root)
    eol = detect_eol(state_raw)

    # pointer removal
    a_start, a_end = find_section(state, ACTIVE_HEADING)
    pointers = [
        (n, level)
        for n, level, text in headings(state)
        if a_start < n < a_end and level in (3, 4) and re.match(rf"TASK-{number}\b", text)
    ]
    if len(pointers) != 1:
        raise CloseError(
            f"expected exactly one TASK-{number} pointer in Aktywne taski, found {len(pointers)}"
        )
    p_start, p_level = pointers[0]
    p_end = min(block_end(state, p_start, p_level), a_end)
    removed_pointer = bare(state[p_start])
    del state[p_start:p_end]

    # window item
    item = f"- **TASK-{number}** — {title.strip()} — {version} — tasks/completed/{task_path.name}"
    d_start, d_end = find_section(state, DONE_HEADING)
    bullets = [n for n in range(d_start + 1, d_end) if state[n].startswith("- ")]
    if bullets:
        state.insert(bullets[0], item + eol)
        bullets = [bullets[0]] + [n + 1 for n in bullets]
    else:
        # empty list: the item goes after the heading and one blank line
        at = d_start + 1
        if at < len(state) and not state[at].strip():
            at += 1
        else:
            state.insert(at, eol)
            at += 1
        state.insert(at, item + eol)
        if at + 1 < len(state) and state[at + 1].strip():
            state.insert(at + 1, eol)
        bullets = [at]
    dropped = [bare(state[n]) for n in bullets[MAX_DONE:]]
    for n in reversed(bullets[MAX_DONE:]):
        del state[n]
    while len(state) > 1 and not state[-1].strip():
        state.pop()  # the file ends with exactly one line ending
    if not state[-1].endswith("\n"):
        state[-1] += eol
    state_new = encode(state)

    # archive
    archive_path = newest_archive(root)
    archive_raw = archive_path.read_bytes()
    archive = decode(archive_raw)
    titles = [n for n, level, _ in headings(archive) if level == 1]
    if not titles:
        raise CloseError(f"{archive_path.name} has no '# ' title line")
    block = split_lines(normalise_block(done_text, eol))
    position = titles[0] + 1
    if position < len(archive) and not archive[position].strip():
        position += 1
        archive[position:position] = [*block, eol]
    else:
        archive[position:position] = [eol, *block, eol]
    archive_new = encode(archive)

    summary = [
        f"task file: {TASKS_REL}/{task_path.name} -> {COMPLETED_REL}/ (status done)",
        f"archive:   {ARCHIVE_REL}/{archive_path.name}: insert {len(block)} lines under the title",
        f"window:    add {item}",
        *[f"window:    drop {line[:90]}" for line in dropped],
        f"window:    remove pointer {removed_pointer}",
        *notes,
    ]
    changes = [
        FileChange(root / STATE_REL, state_raw, state_new),
        FileChange(archive_path, archive_raw, archive_new),
        FileChange(task_path, task_old, task_new),
    ]
    names = [name for name in active_names(root) if name != task_path.name]
    return Plan(changes, (task_path, destination), summary, state_new, names)


def plan_record_hash(root: Path, number: str, commit: str, version: str | None) -> Plan:
    if not HASH_RE.match(commit):
        raise CloseError("--commit must be a full 40-character lowercase hex hash")
    if version is not None:
        check_version(version)
    verify_commit(root, commit)
    short = commit[:HASH_SHORT]

    state_raw, state = read_state(root)
    d_start, d_end = find_section(state, DONE_HEADING)
    item_re = re.compile(
        rf"^(- \*\*TASK-{number}\*\* — .+ — )(v\d+\.\d+\.\d+)"
        r"( — tasks/completed/(\S+\.md))(\r?\n)?$"
    )
    candidates: list[tuple[int, re.Match[str]]] = []
    for index in range(d_start + 1, d_end):
        match = item_re.match(state[index])
        if match and (version is None or match.group(2) == version):
            candidates.append((index, match))
    if len(candidates) != 1:
        raise CloseError(
            f"expected exactly one TASK-{number} window item without a hash"
            f"{' for ' + version if version else ''}, found {len(candidates)}"
        )
    index, match = candidates[0]
    found_version = match.group(2)
    relative = match.group(3).removeprefix(" — ")
    state[index] = (
        f"{match.group(1)}{found_version} / `{short}`{match.group(3)}{match.group(5) or ''}"
    )
    state_new = encode(state)

    # The section may sit in an older quarter file when a new archive was started
    # between closing and recording, so search every archive, newest first.
    token = re.compile(rf"(?<![\w.]){re.escape(found_version)}(?!\w)(?!\.\d)(?! / `)")
    replaced = False
    for archive_path in archives_newest_first(root):
        archive_raw = archive_path.read_bytes()
        archive = decode(archive_raw)
        for start, level, text in headings(archive):
            if level != 3 or not re.match(rf"TASK-{number}\b", text):
                continue
            for n in range(start + 1, block_end(archive, start, 3)):
                if token.search(archive[n]):
                    archive[n] = token.sub(f"{found_version} / `{commit}`", archive[n], count=1)
                    replaced = True
                    break
            if replaced:
                break
        if replaced:
            break
    if not replaced:
        raise CloseError(
            f"no archive has a TASK-{number} section with a mention of {found_version} "
            "without a hash"
        )
    archive_new = encode(archive)

    task_path = root / "ai_docs" / relative
    if not task_path.is_file():
        raise CloseError(f"task file ai_docs/{relative} from the window item does not exist")
    task_old = task_path.read_bytes()
    task_text = task_old.decode("utf-8")
    placeholder = f"Commit: {found_version} (hash dopisuje kolejny commit)."
    recorded = f"Commit: {found_version} / `{commit}`."
    count = task_text.count(placeholder)
    if count == 1:
        task_new = task_text.replace(placeholder, recorded).encode("utf-8")
    elif count == 0 and recorded in task_text:
        task_new = task_old
    else:
        raise CloseError(
            f'ai_docs/{relative}: expected exactly one line "{placeholder}", found {count}'
        )

    summary = [
        f"window:  TASK-{number} {found_version} -> {found_version} / `{short}`",
        f"archive: {archive_path.name}: {found_version} -> {found_version} / `{commit}`",
        f"task:    ai_docs/{relative}: Outcome Commit line",
    ]
    changes = [
        FileChange(root / STATE_REL, state_raw, state_new),
        FileChange(archive_path, archive_raw, archive_new),
        FileChange(task_path, task_old, task_new),
    ]
    return Plan(changes, None, summary, state_new, active_names(root))


# -------------------------------------------------------------------------- git


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )


def verify_commit(root: Path, commit: str) -> None:
    result = git(root, "cat-file", "-e", f"{commit}^{{commit}}")
    if result.returncode != 0:
        raise CloseError(f"commit {commit} does not exist in the repository at {root}")


def is_tracked(root: Path, path: Path) -> bool:
    return git(root, "ls-files", "--error-unmatch", "--", str(path)).returncode == 0


def move_task(root: Path, source: Path, destination: Path) -> bool:
    """Move with ``git mv`` when tracked; return whether git performed it."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if is_tracked(root, source):
        result = git(root, "mv", "--", str(source), str(destination))
        if result.returncode != 0:
            raise CloseError(f"git mv failed: {result.stderr.strip()}")
        return True
    shutil.move(str(source), str(destination))
    return False


def move_back(root: Path, source: Path, destination: Path, via_git: bool) -> None:
    if via_git:
        git(root, "mv", "--", str(destination), str(source))
    if destination.exists() and not source.exists():
        shutil.move(str(destination), str(source))


# ----------------------------------------------------------------------- checks


def load_script(name: str) -> ModuleType:
    module_name = f"close_task_loaded_{name}"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise CloseError(f"cannot load scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def run_checks(root: Path) -> list[str]:
    """Window consistency and startup-read budgets for ``root``; one string per problem."""
    problems: list[str] = []
    window = load_script("check_current_state_window")
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        code = window.main(root)
    if code != 0:
        problems.append(captured.getvalue().strip())
    budget = load_script("check_startup_read_budget")
    problems.extend(budget.check(root))
    return problems


def sandbox_checks(root: Path, plan: Plan) -> list[str]:
    """Run both checks on a temporary tree that carries the planned CURRENT_STATE.md."""
    with tempfile.TemporaryDirectory(prefix="close_task_dry_") as temporary:
        sandbox = Path(temporary)
        for relative in BUDGET_COPY:
            source = root / relative
            if source.is_file():
                (sandbox / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, sandbox / relative)
        (sandbox / STATE_REL).parent.mkdir(parents=True, exist_ok=True)
        (sandbox / STATE_REL).write_bytes(plan.state_new)
        (sandbox / TASKS_REL).mkdir(parents=True, exist_ok=True)
        for name in plan.active_names:
            (sandbox / TASKS_REL / name).write_bytes(b"")
        return run_checks(sandbox)


# ------------------------------------------------------------------------ apply


def apply_plan(root: Path, plan: Plan) -> None:
    """Write all changes, move the task file, run the checks; roll back on any failure."""
    written: list[FileChange] = []
    moved: tuple[Path, Path, bool] | None = None
    try:
        for change in plan.changes:
            change.path.write_bytes(change.new)
            written.append(change)
        if plan.move is not None:
            source, destination = plan.move
            moved = (source, destination, move_task(root, source, destination))
        problems = run_checks(root)
        if problems:
            raise CloseError("checks failed after the change:\n  " + "\n  ".join(problems))
    except BaseException:
        if moved is not None:
            move_back(root, moved[0], moved[1], moved[2])
        for change in reversed(written):
            change.path.write_bytes(change.old)
        raise


def print_plan(plan: Plan, dry_run: bool) -> None:
    print("DRY RUN: no file written" if dry_run else "Applied:")
    for line in plan.summary:
        print(f"  {line}")


# --------------------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root")
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and print the plan, write nothing"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    close = sub.add_parser("close", help="close a finished task")
    close.add_argument("task", help="TASK-NNNN or NNNN")
    close.add_argument("--title", required=True)
    close.add_argument("--version", required=True, help="vX.Y.N of the closing commit")
    close.add_argument("--done-file", required=True, type=Path)
    close.add_argument("--date", default=None, help="YYYY-MM-DD for last_updated (default today)")
    record = sub.add_parser("record-hash", help="record the commit hash of a closed task")
    record.add_argument("task", help="TASK-NNNN or NNNN")
    record.add_argument("--commit", required=True, help="full 40-hex commit hash")
    record.add_argument("--version", default=None, help="vX.Y.N to disambiguate window items")
    return parser


def run(args: argparse.Namespace) -> Plan:
    root: Path = args.root.resolve()
    number = parse_task_id(args.task)
    if args.command == "close":
        version = check_version(args.version)
        if not args.done_file.is_file():
            raise CloseError(f"--done-file not found: {args.done_file}")
        done_text = args.done_file.read_text(encoding="utf-8-sig")
        date = args.date or datetime.date.today().isoformat()
        plan = plan_close(root, number, args.title, version, done_text, date)
    else:
        plan = plan_record_hash(root, number, args.commit, args.version)
    if args.dry_run:
        problems = sandbox_checks(root, plan)
        print_plan(plan, dry_run=True)
        if problems:
            raise CloseError("checks would fail after the change:\n  " + "\n  ".join(problems))
        print("  checks: window and budgets would pass")
        return plan
    apply_plan(root, plan)
    print_plan(plan, dry_run=False)
    print("  checks: window and budgets pass; nothing committed")
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except CloseError as error:
        print(f"close_task: ERROR {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
