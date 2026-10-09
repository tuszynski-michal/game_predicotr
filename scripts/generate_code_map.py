"""Generate the deterministic code map of the repository (TASK-0939).

Outputs (both committed, both checked by ``--check``):

* ``ai_docs/architecture/CODE_MAP.md`` - short overview: functional area ->
  directories, entry modules with their top-level symbols, tests, commands.
* ``ai_docs/architecture/CODE_MAP_SYMBOLS.md`` - grep-friendly index: one line
  per module with its public top-level classes/functions (Python from the AST,
  TypeScript from ``export`` declarations).

The map is built from the file tree and the AST only; nothing is read into
prose. Output is byte-stable: sorted paths, LF newlines, no timestamps.

Usage::

    python scripts/generate_code_map.py            # (re)write both files
    python scripts/generate_code_map.py --check    # exit 1 when a file is stale
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "ai_docs" / "architecture" / "CODE_MAP.md"
SYMBOLS_PATH = ROOT / "ai_docs" / "architecture" / "CODE_MAP_SYMBOLS.md"

SKIP_DIRS = frozenset(
    {
        "__pycache__",
        "node_modules",
        ".next",
        "dist",
        "coverage",
        ".venv",
        "generated",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)
TS_SUFFIXES = (".ts", ".tsx")
TS_TEST_MARKERS = (".test.", ".spec.")
MAX_SYMBOLS_PER_MODULE = 8
EXPORT_RE = re.compile(
    r"^export\s+(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:function\*?|class|const|let|type|interface|enum)\s+([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)

API_SRC = "services/api/src/game_predictor_api"
WORKER_SRC = "services/worker/src/game_predictor_worker"


@dataclass(frozen=True)
class Unit:
    """A directory or single file belonging to an area."""

    path: str
    note: str = ""


@dataclass(frozen=True)
class Area:
    key: str
    title: str
    summary: str
    units: tuple[Unit, ...]
    entry_points: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    commands: tuple[str, ...] = ()


AREAS: tuple[Area, ...] = (
    Area(
        key="api",
        title="API (services/api, FastAPI Admin API)",
        summary=(
            "Warstwy: `api/` (routery HTTP) -> `application/` (use case'y) -> "
            "`domain/` (czysta logika), obok `storage/` (SQLAlchemy/PostgreSQL) i "
            "`schemas/` (Pydantic). Migracje Alembic w `services/api/alembic/versions/`."
        ),
        units=(
            Unit(f"{API_SRC}/api", "routery HTTP; rejestr w `router.py`"),
            Unit(f"{API_SRC}/application", "use case'y (orkiestracja, transakcje)"),
            Unit(f"{API_SRC}/domain", "czysta logika domenowa bez I/O"),
            Unit(f"{API_SRC}/schemas", "modele Pydantic (kontrakt OpenAPI)"),
            Unit(f"{API_SRC}/storage", "repozytoria SQLAlchemy, modele tabel"),
            Unit(f"{API_SRC}/security", "autoryzacja i polityki dostępu"),
            Unit(f"{API_SRC}/main.py", "fabryka aplikacji FastAPI"),
            Unit(f"{API_SRC}/config.py", "konfiguracja (tylko loopback)"),
            Unit("services/api/alembic/versions", "migracje `NNNN_*.py`"),
            Unit("services/test_support", "wspólne helpery testowe API/workera"),
        ),
        entry_points=(
            f"{API_SRC}/main.py",
            f"{API_SRC}/api/router.py",
            f"{API_SRC}/api/super_game_series.py",
            f"{API_SRC}/api/board_search.py",
            f"{API_SRC}/api/rules.py",
        ),
        tests=("services/api/tests", "services/api/tests/integration"),
        commands=(
            "`npm run api:dev`",
            "`npm run python:test` (`-Suite Api`)",
            "`npm run openapi:generate` po zmianie kontraktu; `npm run openapi:check`",
            "`npm run db:migrate`",
        ),
    ),
    Area(
        key="worker",
        title="Worker (services/worker, durable jobs)",
        summary=(
            "Osobny proces pobierający joby z PostgreSQL po lane (`general`, "
            "`image-selection`). Zapisuje artefakty na dysk i wyniki do bazy."
        ),
        units=(
            Unit(f"{WORKER_SRC}/images", "ingestia, geometria, preflight, crop komórek, siatka"),
            Unit(f"{WORKER_SRC}/symbols", "klasyfikacja symboli, biblioteka referencyjna, RGB v2"),
            Unit(f"{WORKER_SRC}/payouts", "wypłaty: kontrakty, handler, gotowość, audyt"),
            Unit(f"{WORKER_SRC}/domain/super_games", "supergry: definicje, rejestr, Wild"),
            Unit(f"{WORKER_SRC}/super_game_series.py", "wyprowadzanie serii supergry"),
            Unit(f"{WORKER_SRC}/imports", "import danych: parsowanie, walidacja, handler"),
            Unit(f"{WORKER_SRC}/jobs", "runtime jobów, lane, store"),
            Unit(f"{WORKER_SRC}/snapshots", "generowanie snapshotu SQLite dla aplikacji mobilnej"),
            Unit(f"{WORKER_SRC}/domain", "kontrakty, sygnatury, wypłaty (czysta domena)"),
            Unit(f"{WORKER_SRC}/semi_automatic_selection", "półautomatyczna selekcja obrazów"),
            Unit(f"{WORKER_SRC}/geometry_core", "wspólny rdzeń geometrii"),
            Unit(f"{WORKER_SRC}/training_core", "wspólny rdzeń treningu modeli"),
            Unit(f"{WORKER_SRC}/vision_lab", "laboratorium wizji (izolowane)"),
            Unit(f"{WORKER_SRC}/releases", "wydania modeli/aplikacji"),
            Unit(f"{WORKER_SRC}/benchmarks", "benchmarki (nie uruchamiać bez polecenia)"),
            Unit(f"{WORKER_SRC}/cli.py", "wejście CLI workera"),
        ),
        entry_points=(
            f"{WORKER_SRC}/cli.py",
            f"{WORKER_SRC}/jobs/runtime.py",
            f"{WORKER_SRC}/jobs/lane_runtime.py",
            f"{WORKER_SRC}/super_game_series.py",
            f"{WORKER_SRC}/domain/super_games/registry.py",
            f"{WORKER_SRC}/payouts/handler.py",
            f"{WORKER_SRC}/imports/handler.py",
        ),
        tests=("services/worker/tests",),
        commands=(
            "`npm run worker:once` / `npm run worker:poll`",
            "`npm run python:test` (`-Suite Worker`)",
            "pojedynczy test: `pytest services/worker/tests/<plik> -k <nazwa>` (`.venv`)",
        ),
    ),
    Area(
        key="admin",
        title="Admin (apps/admin, Next.js, port 3000)",
        summary="Panel administracyjny; funkcje w `src/features/<nazwa>/`, trasy w `src/app/`.",
        units=(
            Unit("apps/admin/src/features", "funkcje panelu (podkatalogi poniżej)"),
            Unit("apps/admin/src/app", "trasy Next.js"),
            Unit("apps/admin/src/api", "wrappery klienta API"),
            Unit("apps/admin/src/components", "wspólne komponenty"),
            Unit("apps/admin/src/lib", "narzędzia pomocnicze"),
            Unit("apps/admin/src/config", "konfiguracja"),
        ),
        entry_points=(
            "apps/admin/src/features/super-games/super-game-series-workspace.tsx",
            "apps/admin/src/features/super-games/super-game-series-state.ts",
        ),
        tests=("apps/admin/test", "apps/admin/test-interactions", "apps/admin/test-browser"),
        commands=(
            "`npm run admin:dev`",
            "`npm run typecheck --workspace @game-predictor/admin`",
            "`npm run lint --workspace @game-predictor/admin`",
        ),
    ),
    Area(
        key="reviewer",
        title="Reviewer (apps/reviewer, Next.js, port 3001)",
        summary=(
            "Zdalny/lokalny UI przeglądu i selekcji; proxy allowlisty do API z "
            "cookie sesji (`src/security/`)."
        ),
        units=(
            Unit("apps/reviewer/src/features", "funkcje (podkatalogi poniżej)"),
            Unit("apps/reviewer/src/app", "trasy i route handlery"),
            Unit("apps/reviewer/src/security", "proxy i polityka allowlisty"),
            Unit("apps/reviewer/src/api", "wrapper klienta API"),
            Unit("apps/reviewer/src/config", "konfiguracja"),
        ),
        entry_points=("apps/reviewer/src/security/reviewer-proxy-policy.ts",),
        tests=("apps/reviewer/test", "apps/reviewer/test-interactions"),
        commands=(
            "`npm run reviewer:dev`",
            "`npm run test --workspace @game-predictor/reviewer`",
            "`npm run test:geometry --workspace @game-predictor/reviewer`",
        ),
    ),
    Area(
        key="packages",
        title="Packages (packages/*)",
        summary=(
            "Wspólny kod TS. Klient API jest generowany z OpenAPI "
            "(`admin-api-client/src/generated`, nie edytować ręcznie)."
        ),
        units=(
            Unit("packages/board-search-ui/src", "wspólny UI wyszukiwarki plansz"),
            Unit("packages/shared-ts/src", "kontrakty domenowe i kodek sygnatur (też mobile)"),
            Unit("packages/admin-api-client/src", "wrappery klienta wygenerowanego z OpenAPI"),
            Unit("packages/manual-image-selection-core/src", "wspólna logika ręcznej selekcji"),
            Unit("packages/ui/src", "wspólne elementy UI"),
            Unit("packages/vision-lab-api-client/src", "klient API laboratorium wizji"),
            Unit("packages/domain-fixtures", "złote przypadki JSON (TS i Python)"),
        ),
        tests=(
            "packages/board-search-ui/test",
            "packages/shared-ts/test",
            "packages/admin-api-client/test",
            "packages/manual-image-selection-core/test",
            "packages/vision-lab-api-client/test",
        ),
        commands=(
            "`npm run test --workspace @game-predictor/<pakiet>`",
            "`npm run fixture:validate`",
        ),
    ),
    Area(
        key="mobile",
        title="Mobile (apps/mobile, Expo, offline)",
        summary="Aplikacja Android tylko ze snapshotem SQLite; bez uprawnienia INTERNET.",
        units=(Unit("apps/mobile/src", "kod aplikacji"),),
        tests=("apps/mobile/__tests__",),
        commands=("`npm run snapshot:generate`", "`npm run snapshot:validate`"),
    ),
    Area(
        key="scripts",
        title="Scripts (scripts/)",
        summary="Skrypty pipeline'u, akceptacji i benchmarków; grupy wg prefiksu nazwy pliku.",
        units=(Unit("scripts", "grupy poniżej; npm scripts wg prefiksu w `package.json`"),),
        commands=(
            "`npm run docs:check`",
            "`npm run code-map:check` (aktualność mapy kodu; poza `quality`)",
            "`npm run python:lint` / `npm run python:typecheck`",
            "`npm run quality` (pełna bramka)",
        ),
    ),
    Area(
        key="docs",
        title="Docs (ai_docs/)",
        summary="Dokumentacja procesu; kolejność czytania w `AGENTS.md` i `ai_docs/README.md`.",
        units=(
            Unit("ai_docs/process", "stan, decyzje, standardy planów i zadań"),
            Unit("ai_docs/requirements", "wymagania produktu"),
            Unit("ai_docs/architecture", "architektura (ten plik: `CODE_MAP.md`)"),
            Unit("ai_docs/delivery", "plany wykonania"),
            Unit("ai_docs/tasks", "aktywne zadania (ukończone w `completed/`)"),
            Unit("ai_docs/quality", "raporty jakości i audytów"),
            Unit("ai_docs/guides", "instrukcje operatorskie"),
        ),
        commands=("`npm run docs:check`", "`npm run code-map:check`"),
    ),
)


@dataclass
class Module:
    path: str
    symbols: list[str] = field(default_factory=list)
    doc: str = ""


def walk_files(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Return files under ``base`` with ``suffixes``, sorted, skipping tool dirs."""
    if base.is_file():
        return [base] if base.suffix in suffixes else []
    found: list[Path] = []
    stack = [base]
    while stack:
        current = stack.pop()
        for child in current.iterdir():
            if child.is_dir():
                if child.name in SKIP_DIRS or child.name.startswith("."):
                    continue
                stack.append(child)
            elif child.suffix in suffixes:
                found.append(child)
    return sorted(found, key=lambda item: item.relative_to(ROOT).as_posix())


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def python_module(path: Path) -> Module:
    source = path.read_text(encoding="utf-8")
    module = Module(path=rel(path))
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        module.symbols = ["<syntax error>"]
        return module
    doc = ast.get_docstring(tree) or ""
    module.doc = doc.strip().splitlines()[0][:100] if doc.strip() else ""
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            name = node.name
            prefix = "class "
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = node.name
            prefix = ""
        else:
            continue
        if name.startswith("_"):
            continue
        module.symbols.append(f"{prefix}{name}")
    return module


def ts_module(path: Path) -> Module:
    source = path.read_text(encoding="utf-8")
    names: list[str] = []
    for match in EXPORT_RE.finditer(source):
        name = match.group(1)
        if name not in names:
            names.append(name)
    return Module(path=rel(path), symbols=names)


def is_ts_test(path: Path) -> bool:
    name = path.name
    return any(marker in name for marker in TS_TEST_MARKERS)


def collect_modules(unit_path: str) -> list[Module]:
    base = ROOT / unit_path
    if not base.exists():
        raise SystemExit(f"code map: configured path does not exist: {unit_path}")
    modules: list[Module] = []
    for path in walk_files(base, (".py",)):
        modules.append(python_module(path))
    for path in walk_files(base, TS_SUFFIXES):
        if is_ts_test(path) or path.name.endswith(".d.ts"):
            continue
        modules.append(ts_module(path))
    return modules


def count_files(path_text: str, suffixes: tuple[str, ...]) -> int:
    base = ROOT / path_text
    if not base.exists():
        return 0
    return sum(1 for item in walk_files(base, suffixes) if not is_ts_test(item))


def format_symbols(symbols: list[str], limit: int | None = MAX_SYMBOLS_PER_MODULE) -> str:
    """Join symbols; ``limit=None`` lists all of them (used by the search index)."""
    shown = symbols if limit is None else symbols[:limit]
    extra = len(symbols) - len(shown)
    text = ", ".join(shown)
    if extra > 0:
        text += f" (+{extra})"
    return text


def package_doc(unit_path: str) -> str:
    init = ROOT / unit_path / "__init__.py"
    if init.is_file():
        try:
            doc = ast.get_docstring(ast.parse(init.read_text(encoding="utf-8")))
        except SyntaxError:
            doc = None
        if doc and doc.strip():
            return doc.strip().splitlines()[0][:100]
    return ""


def unit_line(unit: Unit) -> str:
    base = ROOT / unit.path
    if not base.exists():
        raise SystemExit(f"code map: configured path does not exist: {unit.path}")
    if base.is_file():
        label = f"`{unit.path}`"
        count_text = ""
    else:
        py = count_files(unit.path, (".py",))
        ts = count_files(unit.path, TS_SUFFIXES)
        parts = []
        if py:
            parts.append(f"{py} py")
        if ts:
            parts.append(f"{ts} ts/tsx")
        count_text = f" ({', '.join(parts)})" if parts else ""
        label = f"`{unit.path}/`"
    note = unit.note
    doc = package_doc(unit.path) if base.is_dir() else ""
    if doc and doc not in note:
        note = f"{note}; {doc}" if note else doc
    return f"- {label}{count_text}" + (f" - {note}" if note else "")


def subdirectories(unit_path: str) -> list[str]:
    base = ROOT / unit_path
    names = [
        child.name
        for child in base.iterdir()
        if child.is_dir() and child.name not in SKIP_DIRS and not child.name.startswith(".")
    ]
    return sorted(names)


def feature_lines(unit_path: str) -> list[str]:
    lines: list[str] = []
    for name in subdirectories(unit_path):
        sub = f"{unit_path}/{name}"
        modules = [m for m in collect_modules(sub) if m.symbols]
        count = count_files(sub, TS_SUFFIXES) + count_files(sub, (".py",))
        names: list[str] = []
        for module in modules:
            for symbol in module.symbols:
                if symbol not in names:
                    names.append(symbol)
        lines.append(f"  - `{name}/` ({count} plików): {format_symbols(names)}")
    return lines


def entry_point_lines(paths: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for path_text in paths:
        path = ROOT / path_text
        if not path.is_file():
            raise SystemExit(f"code map: entry point does not exist: {path_text}")
        module = python_module(path) if path.suffix == ".py" else ts_module(path)
        detail = format_symbols(module.symbols)
        lines.append(f"- `{path_text}`" + (f": {detail}" if detail else ""))
    return lines


NON_TEST_FILES = frozenset({"conftest.py", "__init__.py"})


def test_lines(paths: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for path_text in paths:
        base = ROOT / path_text
        if not base.exists():
            raise SystemExit(f"code map: test path does not exist: {path_text}")
        count = sum(
            1
            for item in walk_files(base, (".py", ".ts", ".tsx", ".mjs", ".js"))
            if item.name not in NON_TEST_FILES and not item.name.endswith(".d.ts")
        )
        lines.append(f"- `{path_text}/` ({count} plików w katalogu testów, rekurencyjnie)")
    return lines


def scripts_groups() -> list[str]:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted((ROOT / "scripts").iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        stem = path.stem
        token = stem.split("_", 1)[0]
        groups[token].append(path.name)
    lines = ["Pliki wg pierwszego członu nazwy (liczba; przykłady):", ""]
    singles: list[str] = []
    for token in sorted(groups):
        names = groups[token]
        if len(names) == 1:
            singles.append(f"`{names[0]}`")
            continue
        examples = ", ".join(f"`{name}`" for name in names[:3])
        more = f" (+{len(names) - 3})" if len(names) > 3 else ""
        lines.append(f"- `{token}_*` ({len(names)}): {examples}{more}")
    lines += ["", "Pojedyncze pliki: " + ", ".join(singles)]
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    npm: dict[str, int] = defaultdict(int)
    for name in package.get("scripts", {}):
        npm[name.split(":", 1)[0]] += 1
    lines += [
        "",
        "npm scripts wg prefiksu (liczba): "
        + ", ".join(f"`{key}:`{count}" for key, count in sorted(npm.items())),
    ]
    return lines


def docs_lines() -> list[str]:
    lines: list[str] = []
    process = ROOT / "ai_docs" / "process"
    names = sorted(item.name for item in process.glob("*.md"))
    lines.append("Pliki procesu: " + ", ".join(f"`{name}`" for name in names))
    return lines


def render_overview() -> str:
    out: list[str] = [
        "---",
        "title: Code map",
        "status: active",
        "generated_by: scripts/generate_code_map.py",
        "---",
        "",
        "# Mapa kodu",
        "",
        "Plik **generowany** (`python scripts/generate_code_map.py`); nie edytuj ręcznie.",
        "Kontrola świeżości: `python scripts/generate_code_map.py --check`.",
        "Pełny indeks symboli (jedna linia na moduł, do `rg`): "
        "[CODE_MAP_SYMBOLS.md](CODE_MAP_SYMBOLS.md).",
        "",
        "Użycie: najpierw znajdź obszar tutaj, potem `rg` po "
        "`CODE_MAP_SYMBOLS.md`, dopiero na końcu otwórz konkretny plik z zakresem "
        "linii. Zasady rozwiązywania sprzeczności: `AGENTS.md`.",
        "",
        "Obszary: " + ", ".join(f"[{area.key}](#{area.key})" for area in AREAS) + ".",
        "",
    ]
    for area in AREAS:
        out += [f'<a id="{area.key}"></a>', f"## {area.title}", "", area.summary, ""]
        out += ["### Katalogi", ""]
        for unit in area.units:
            out.append(unit_line(unit))
            if unit.path in (
                "apps/admin/src/features",
                "apps/reviewer/src/features",
            ):
                out += feature_lines(unit.path)
        out.append("")
        if area.key == "scripts":
            out += ["### Grupy", ""] + scripts_groups() + [""]
        if area.key == "docs":
            out += docs_lines() + [""]
        if area.entry_points:
            out += ["### Moduły wejściowe i symbole", ""]
            out += entry_point_lines(area.entry_points)
            out.append("")
        if area.tests:
            out += ["### Testy", ""] + test_lines(area.tests) + [""]
        if area.commands:
            out += ["### Komendy", ""] + [f"- {command}" for command in area.commands] + [""]
    return "\n".join(out).rstrip("\n") + "\n"


SYMBOL_ROOTS: tuple[str, ...] = (
    API_SRC,
    "services/test_support",
    WORKER_SRC,
    "apps/admin/src",
    "apps/reviewer/src",
    "apps/mobile/src",
    "packages/board-search-ui/src",
    "packages/shared-ts/src",
    "packages/admin-api-client/src",
    "packages/manual-image-selection-core/src",
    "packages/ui/src",
    "packages/vision-lab-api-client/src",
    "scripts",
)


def render_symbols() -> str:
    out: list[str] = [
        "---",
        "title: Code map symbol index",
        "status: active",
        "generated_by: scripts/generate_code_map.py",
        "---",
        "",
        "# Indeks symboli",
        "",
        "Plik **generowany**; nie czytaj w całości, przeszukuj `rg`. Format linii: "
        "`ścieżka: symbole` (Python: klasy i funkcje publiczne najwyższego poziomu; "
        "TS: nazwane `export`; wszystkie symbole modułu, bez limitu). "
        "Pomijane: testy, `generated/`, `node_modules`, symbole zaczynające się od `_`.",
        "",
    ]
    for root_text in SYMBOL_ROOTS:
        base = ROOT / root_text
        if not base.exists():
            continue
        modules = collect_modules(root_text)
        modules = [m for m in modules if m.symbols]
        out += [f"## {root_text}", ""]
        prefix = root_text + "/"
        out += [
            f"- {m.path.removeprefix(prefix)}: {format_symbols(m.symbols, None)}" for m in modules
        ]
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def write_lf(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def read_lf(path: Path) -> str | None:
    if not path.is_file():
        return None
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


def main_with_args(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; exit 1 when the committed map differs from a fresh render",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    targets = ((MAP_PATH, render_overview()), (SYMBOLS_PATH, render_symbols()))
    if args.check:
        stale = [rel(path) for path, text in targets if read_lf(path) != text]
        if stale:
            print("code map is stale: " + ", ".join(stale))
            print("run: .\\.venv\\Scripts\\python.exe scripts/generate_code_map.py")
            return 1
        print("code map is up to date")
        return 0
    for path, text in targets:
        write_lf(path, text)
        print(f"wrote {rel(path)} ({len(text.encode('utf-8'))} bytes)")
    return 0


def main() -> int:
    return main_with_args()


if __name__ == "__main__":
    raise SystemExit(main())
