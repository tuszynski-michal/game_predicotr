"""Collect and render token usage for the TASK-0939 tooling pilot.

Input source (verified on a real Claude Code install): the session transcript
``~/.claude/projects/<project-slug>/<session-id>.jsonl``. Every ``assistant``
line carries ``message.id`` and ``message.usage`` (``input_tokens``,
``output_tokens``, ``cache_creation_input_tokens``, ``cache_read_input_tokens``).
One API message can appear on several lines (streaming), so lines are
de-duplicated by ``message.id`` taking the maximum of each counter. Subagent
calls live in ``<project-slug>/<session-id>/subagents/agent-*.jsonl`` with the
same line format and are summed into the session total.

When no transcript is available (another client, or an exported usage report),
fill ``results.csv`` by hand with the columns listed in ``RESULT_COLUMNS`` and
use ``render`` only.

Subcommands::

    python scripts/token_pilot_collect.py usage --session-id <id>
    python scripts/token_pilot_collect.py collect --manifest sessions.csv --out results.csv
    python scripts/token_pilot_collect.py render --results results.csv [--out table.md]

``sessions.csv`` columns: variant,task,run,session_id,quality,notes
(``session_id`` may also be a path to a transcript ``.jsonl``; ``task`` equal to
``indexing`` records the one-off indexing cost of a variant).
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
RESULT_COLUMNS = (
    "variant",
    "task",
    "run",
    "input_tokens",
    "output_tokens",
    "cache_creation_tokens",
    "cache_read_tokens",
    "calls",
    "quality",
    "notes",
)
# Approximate price weights relative to one uncached input token (Anthropic list
# pricing ratios: 5-minute cache write 1.25x, cache read 0.1x, output 5x).
WEIGHT_INPUT = 1.0
WEIGHT_CACHE_WRITE = 1.25
WEIGHT_CACHE_READ = 0.1
WEIGHT_OUTPUT = 5.0
BASELINE_VARIANT = "baseline"
INDEXING_TASK = "indexing"


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    calls: int = 0
    models: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_tokens
            + self.cache_read_tokens
        )

    @property
    def weighted(self) -> float:
        return (
            self.input_tokens * WEIGHT_INPUT
            + self.cache_creation_tokens * WEIGHT_CACHE_WRITE
            + self.cache_read_tokens * WEIGHT_CACHE_READ
            + self.output_tokens * WEIGHT_OUTPUT
        )

    def add(self, other: Usage) -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_tokens += other.cache_creation_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.calls += other.calls
        for model, count in other.models.items():
            self.models[model] = self.models.get(model, 0) + count


def read_transcript(path: Path) -> Usage:
    """Sum de-duplicated assistant usage of one transcript file."""
    per_message: dict[str, dict[str, int]] = {}
    models: dict[str, str] = {}
    anonymous = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("type") != "assistant":
                continue
            message = row.get("message")
            if not isinstance(message, dict):
                continue
            usage = message.get("usage")
            if not isinstance(usage, dict):
                continue
            message_id = message.get("id")
            if not isinstance(message_id, str) or not message_id:
                anonymous += 1
                message_id = f"anonymous-{anonymous}"
            slot = per_message.setdefault(message_id, dict.fromkeys(TOKEN_FIELDS, 0))
            for key in TOKEN_FIELDS:
                value = usage.get(key)
                if isinstance(value, int) and value > slot[key]:
                    slot[key] = value
            model = message.get("model")
            if isinstance(model, str):
                models[message_id] = model
    result = Usage(calls=len(per_message))
    for message_id, slot in per_message.items():
        result.input_tokens += slot["input_tokens"]
        result.output_tokens += slot["output_tokens"]
        result.cache_creation_tokens += slot["cache_creation_input_tokens"]
        result.cache_read_tokens += slot["cache_read_input_tokens"]
        model = models.get(message_id, "unknown")
        result.models[model] = result.models.get(model, 0) + 1
    return result


def locate_session(session: str, projects_dir: Path) -> Path:
    """Resolve a session id (or an explicit .jsonl path) to its transcript."""
    candidate = Path(session)
    if candidate.suffix == ".jsonl" and candidate.is_file():
        return candidate
    matches = sorted(projects_dir.glob(f"*/{session}.jsonl"))
    if not matches:
        raise SystemExit(f"transcript not found for session {session!r} under {projects_dir}")
    return matches[0]


def session_usage(transcript: Path) -> Usage:
    """Main transcript plus every subagent transcript next to it."""
    total = read_transcript(transcript)
    subagents = transcript.with_suffix("") / "subagents"
    if subagents.is_dir():
        for sub in sorted(subagents.glob("agent-*.jsonl")):
            total.add(read_transcript(sub))
    return total


def usage_row(
    variant: str, task: str, run: str, usage: Usage, quality: str, notes: str
) -> dict[str, str]:
    return {
        "variant": variant,
        "task": task,
        "run": run,
        "input_tokens": str(usage.input_tokens),
        "output_tokens": str(usage.output_tokens),
        "cache_creation_tokens": str(usage.cache_creation_tokens),
        "cache_read_tokens": str(usage.cache_read_tokens),
        "calls": str(usage.calls),
        "quality": quality,
        "notes": notes,
    }


def cmd_usage(args: argparse.Namespace) -> int:
    transcript = locate_session(args.session_id, Path(args.projects_dir))
    usage = session_usage(transcript)
    print(f"transcript: {transcript}")
    print(f"calls: {usage.calls}  models: {json.dumps(usage.models, sort_keys=True)}")
    print(f"input: {usage.input_tokens}")
    print(f"output: {usage.output_tokens}")
    print(f"cache_creation: {usage.cache_creation_tokens}")
    print(f"cache_read: {usage.cache_read_tokens}")
    print(f"total: {usage.total}  weighted_input_equivalent: {usage.weighted:.0f}")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    rows: list[dict[str, str]] = []
    with Path(args.manifest).open(encoding="utf-8", newline="") as handle:
        for entry in csv.DictReader(handle):
            transcript = locate_session(entry["session_id"].strip(), Path(args.projects_dir))
            usage = session_usage(transcript)
            rows.append(
                usage_row(
                    entry["variant"].strip(),
                    entry["task"].strip(),
                    entry["run"].strip(),
                    usage,
                    entry.get("quality", "").strip(),
                    entry.get("notes", "").strip(),
                )
            )
    with Path(args.out).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {args.out} ({len(rows)} rows)")
    return 0


def to_int(value: str) -> int:
    text = value.strip().replace(" ", "").replace("_", "")
    return int(text) if text else 0


def row_usage(row: dict[str, str]) -> Usage:
    return Usage(
        input_tokens=to_int(row.get("input_tokens", "")),
        output_tokens=to_int(row.get("output_tokens", "")),
        cache_creation_tokens=to_int(row.get("cache_creation_tokens", "")),
        cache_read_tokens=to_int(row.get("cache_read_tokens", "")),
        calls=to_int(row.get("calls", "")),
    )


def fmt(number: float) -> str:
    return f"{number:,.0f}".replace(",", " ")


def render_table(rows: list[dict[str, str]]) -> str:
    runs: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    indexing: dict[str, Usage] = {}
    for row in rows:
        variant, task = row["variant"].strip(), row["task"].strip()
        if task == INDEXING_TASK:
            indexing.setdefault(variant, Usage()).add(row_usage(row))
            continue
        runs[(variant, task)].append(row)
    out = [
        "# Wyniki pilota narzędzi tokenowych",
        "",
        "Metryka: suma tokenów wszystkich wywołań sesji (agent główny + subagenci). "
        "`total` = wejście + wyjście + zapis cache + odczyt cache; `ekw.` = tokeny "
        f"ważone cenowo ({WEIGHT_INPUT:g} / {WEIGHT_CACHE_WRITE:g} / {WEIGHT_CACHE_READ:g} / "
        f"{WEIGHT_OUTPUT:g} dla wejście / zapis cache / odczyt cache / wyjście; przybliżenie).",
        "",
        "## Przebiegi",
        "",
        "| Wariant | Zadanie | Przebieg | Wejście | Wyjście | Zapis cache | Odczyt cache | "
        "Wywołania | total | ekw. | Jakość |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for (variant, task), group in sorted(runs.items()):
        for row in sorted(group, key=lambda item: item.get("run", "")):
            usage = row_usage(row)
            out.append(
                f"| {variant} | {task} | {row.get('run', '')} | {fmt(usage.input_tokens)} | "
                f"{fmt(usage.output_tokens)} | {fmt(usage.cache_creation_tokens)} | "
                f"{fmt(usage.cache_read_tokens)} | {usage.calls} | {fmt(usage.total)} | "
                f"{fmt(usage.weighted)} | {row.get('quality', '')} |"
            )
    means: dict[tuple[str, str], tuple[float, float, bool]] = {}
    for key, group in runs.items():
        totals = [row_usage(row).total for row in group]
        weighted = [row_usage(row).weighted for row in group]
        passed = all(row.get("quality", "").strip().upper() == "PASS" for row in group)
        means[key] = (statistics.fmean(totals), statistics.fmean(weighted), passed)
    out += [
        "",
        "## Średnie i różnica względem bazy",
        "",
        "Wariant z jakością inną niż PASS w którymkolwiek przebiegu jest odrzucany "
        "niezależnie od tokenów.",
        "",
        "| Wariant | Zadanie | Przebiegi | Średnie total | Δ total vs baza | Średnie ekw. | "
        "Δ ekw. vs baza | Jakość |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for (variant, task), (mean_total, mean_weighted, passed) in sorted(means.items()):
        base = means.get((BASELINE_VARIANT, task))
        if base is None or variant == BASELINE_VARIANT or base[0] == 0 or base[1] == 0:
            delta_total = delta_weighted = "-"
        else:
            delta_total = f"{(mean_total - base[0]) / base[0] * 100:+.1f}%"
            delta_weighted = f"{(mean_weighted - base[1]) / base[1] * 100:+.1f}%"
        verdict = "PASS" if passed else "DYSKWALIFIKACJA"
        out.append(
            f"| {variant} | {task} | {len(runs[(variant, task)])} | {fmt(mean_total)} | "
            f"{delta_total} | {fmt(mean_weighted)} | {delta_weighted} | {verdict} |"
        )
    if indexing:
        out += [
            "",
            "## Koszt jednorazowy indeksowania (osobno, nie wliczony powyżej)",
            "",
            "| Wariant | total | ekw. | Notatka |",
            "|---|---:|---:|---|",
        ]
        for variant, usage in sorted(indexing.items()):
            out.append(f"| {variant} | {fmt(usage.total)} | {fmt(usage.weighted)} | |")
    return "\n".join(out) + "\n"


def cmd_render(args: argparse.Namespace) -> int:
    with Path(args.results).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    missing = [column for column in ("variant", "task", "run") if rows and column not in rows[0]]
    if missing:
        raise SystemExit(f"results CSV lacks required columns: {', '.join(missing)}")
    text = render_table(rows)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    sub = parser.add_subparsers(dest="command", required=True)
    usage = sub.add_parser("usage", help="print the token totals of one session")
    usage.add_argument("--session-id", required=True, help="session id or path to a .jsonl")
    usage.add_argument("--projects-dir", default=str(PROJECTS_DIR))
    usage.set_defaults(handler=cmd_usage)
    collect = sub.add_parser("collect", help="build results.csv from a session manifest")
    collect.add_argument("--manifest", required=True)
    collect.add_argument("--out", required=True)
    collect.add_argument("--projects-dir", default=str(PROJECTS_DIR))
    collect.set_defaults(handler=cmd_collect)
    render = sub.add_parser("render", help="render the Markdown results table from results.csv")
    render.add_argument("--results", required=True)
    render.add_argument("--out")
    render.set_defaults(handler=cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
