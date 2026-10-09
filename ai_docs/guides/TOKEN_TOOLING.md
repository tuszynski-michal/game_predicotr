---
title: Narzędzia oszczędzania tokenów
status: active
last_updated: 2026-10-09
---

# Narzędzia oszczędzania tokenów (TASK-0939)

Zestaw narzędzi nawigacji po repozytorium. **Do stałego użytku wchodzi tylko to,
co potwierdził pomiar** (`ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md`).
Stan na dzień dostawy: mapa kodu i hook są gotowe do użycia; Serena i Graphify są
zainstalowane i sprawdzone dymnie, ale ich decyzja „zostaje / wypada” czeka na
pomiar operatora.

| Narzędzie | Stan | Włączenie |
|---|---|---|
| Mapa kodu `CODE_MAP.md` | gotowa, `npm run code-map:check` (poza `docs:check`) | pilot do czasu pomiaru |
| Hook `PreToolUse` (odczyt > 200 KB) | gotowy, wpis w `.claude/settings.json` | pilot do czasu pomiaru (wyłączenie niżej) |
| Serena MCP | zainstalowana, pilot | `claude mcp add` (niżej), decyzję podejmuje operator |
| Graphify | zainstalowany, pilot | tylko ręcznie, wynik poza gitem |

## 1. Mapa kodu

- `ai_docs/architecture/CODE_MAP.md` — obszary (API, worker, Admin, Reviewer,
  pakiety, mobile, skrypty, docs): katalogi, moduły wejściowe z symbolami, testy,
  komendy.
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md` — indeks do `rg`: jedna linia na
  moduł ze **wszystkimi** publicznymi symbolami najwyższego poziomu (bez limitu;
  limit 8 symboli dotyczy tylko przeglądu w `CODE_MAP.md`). **Nie czytaj w
  całości** (ok. 236 KB).
- Oba pliki generuje `scripts/generate_code_map.py` (AST dla Pythona, deklaracje
  `export` dla TS); wynik jest deterministyczny (posortowane ścieżki, LF).

```powershell
# katalog repozytorium, timeout 120 s
.\.venv\Scripts\python.exe scripts/generate_code_map.py          # regeneracja
.\.venv\Scripts\python.exe scripts/generate_code_map.py --check  # exit 1, gdy mapa jest nieaktualna
```

`npm run code-map:check` (to samo co `--check`, około 3 s) jest osobnym skryptem,
**poza** `npm run docs:check` i `quality`: równoległe gałęzie psułyby bramkę przy
niezwiązanych zmianach symboli. Zamykając task, który dodaje, usuwa lub zmienia
nazwę modułu albo publicznego symbolu, zregeneruj mapę i dołącz oba pliki do
commita taska (reguła w `AGENTS.md`). Status: pilot TASK-0939, obowiązuje do czasu
pomiaru; stałe włączenie zależy od wyniku.

## 2. Hook `PreToolUse`: blokada dużych odczytów

Wpis w `.claude/settings.json` uruchamia `scripts/hooks/block_large_read.py`
przed każdym wywołaniem `Read`. Hook odrzuca (exit 2, komunikat po polsku
wskazujący `CODE_MAP.md` i `rg`) odczyt pliku większego niż 200 KB, jeżeli
wywołanie nie ma `offset`, `limit` ani `pages`. Obrazy i PDF są wyłączone z
kontroli. Hook nie blokuje przy błędzie wejścia (fail-open). Status: pilot
TASK-0939, obowiązuje do czasu pomiaru; stałe włączenie zależy od wyniku.

Wyłączenie:

- jednorazowo, w terminalu, z którego startuje Claude Code:
  `$env:GAME_PREDICTOR_ALLOW_LARGE_READ = '1'` (przed uruchomieniem `claude`);
- zmiana progu: `$env:GAME_PREDICTOR_MAX_READ_BYTES = '500000'`;
- na stałe: usuń blok `hooks` z `.claude/settings.json` (plik zawiera wyłącznie
  ten hook) albo przełącz `"disableAllHooks": true` w
  `.claude/settings.local.json` (wyłącza wszystkie hooki użytkownika).

Test ręczny (kod wyjścia 2 = zablokowano, 0 = dozwolone):

```powershell
$p = (Resolve-Path ai_docs/process/decisions/DECISION_LOG_2026.md).Path | ConvertTo-Json
'{"tool_name":"Read","tool_input":{"file_path":' + $p + '}}' | .\.venv\Scripts\python.exe -I scripts/hooks/block_large_read.py; $LASTEXITCODE
```

Testy automatyczne: `services/api/tests/test_block_large_read_hook.py`.

## 3. Serena MCP (pilot)

Serena udostępnia agentowi narzędzia symbolowe (`find_symbol`,
`find_referencing_symbols`, `get_symbols_overview`, `find_declaration`,
`find_implementations`, `get_diagnostics_for_file`) na bazie serwerów LSP
(Pyright dla Pythona, `typescript-language-server` dla TS).

Konfiguracja projektu jest w repozytorium: `.serena/project.yml` (Python +
TypeScript, tryb `read_only`, wyłączone narzędzia edycji i pamięci, ignorowane
`ai_docs/`, `artifacts/`, wygenerowany klient API). Cache (`.serena/cache/`, ok.
160 MB) i `project.local.yml` są ignorowane przez git.

### Instalacja (izolowana, raz na checkout)

Nie dotyka `.venv` ani `package.json`. Wersje są przypięte (`serena-agent==1.7.0`,
`graphifyy==0.9.82`, `uv==0.12.24`); `-Index` wypisuje na początku logu
rzeczywiście zainstalowane wersje (`serena-agent`, `graphifyy`, `uv`, `mcp`), więc
log indeksu dokumentuje środowisko. Każdy checkout lub worktree, w którym działa
Serena albo Graphify, ma własny `.toolingenv-tokens` (powtórz poniższe kroki; brak
venv kończy skrypt kodem 2 z listą poleceń).

```powershell
# katalog głównego checkoutu (ten, w którym uruchamiasz Claude Code), timeout 600 s
python -m venv .tooling\venv-tokens
.\.tooling\venv-tokens\Scripts\python.exe -m pip install serena-agent==1.7.0 graphifyy==0.9.82 uv==0.12.24
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\start_serena_mcp.ps1 -Index   # indeks wstępny, ok. 50 s
```

`uv` jest wymagany, bo Serena uruchamia Pyright przez `uvx`. Skrypt
`scripts/start_serena_mcp.ps1` przekierowuje cały stan Serena i uv do `.tooling\`
(`SERENA_HOME`, `UV_CACHE_DIR`, `UV_PYTHON_INSTALL_DIR`, `UV_TOOL_DIR`) i dodaje
`.tooling\venv-tokens\Scripts` do `PATH` procesu. **Bez tych zmiennych `uvx`
próbuje pobrać Pythona 3.13 do `%APPDATA%\uv` i w tym środowisku kończy się
błędem** (patrz „Wynik testu dymnego”).

### Rejestracja w Claude Code (decyzja operatora)

Agent **nie** rejestruje MCP w `.claude/settings.json`. Operator włącza go sam,
dla siebie i dla tego projektu (zakres `local`, bez `.mcp.json` w repozytorium):

```powershell
# w katalogu głównego checkoutu; podstaw bezwzględną ścieżkę do repozytorium
claude mcp add serena --scope local -- powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Users\tuszy\Documents\game_predicotr\scripts\start_serena_mcp.ps1"
claude mcp list          # serena powinna być Connected
```

Wyłączenie: `claude mcp remove serena --scope local`. Koszt stały: 7 narzędzi,
około 10 KB definicji (około 2,6 tys. tokenów) w każdej sesji, w której MCP jest
włączony; bez wyłączenia narzędzi edycji i pamięci było to 21 narzędzi i około
5,8 tys. tokenów. Ten koszt jest wliczony w pomiar pilota (odczyt cache).

### Wynik testu dymnego (2026-10-09, Windows 11, Python 3.12)

- indeks wstępny (`serena project index`, zimny cache): 47 s, 2223 pliki
  (Python 1582, TypeScript 641); ponowny indeks z cache: 12 s;
- start serwera MCP przez stdio: 3–4 s;
- `find_symbol` klasy Pythona (`SuperGameSeriesDeriveHandler`): 10,7–11,5 s przy
  pierwszym wywołaniu (rozruch Pyright), kolejne 3–6 s; `find_symbol` komponentu
  TS: 5,7 s; `find_referencing_symbols`: 3,0–5,2 s; wyniki poprawne (plik, zakres
  linii, miejsca użycia w `cli.py`);
- awarie po drodze: (1) brak `uvx` w `PATH` — Pyright nie startuje; naprawa:
  `uv` w venv i `PATH` w skrypcie; (2) `uvx -p 3.13` pobierał Pythona do
  `%APPDATA%\uv\python` i kończył błędem „Missing expected target directory for
  Python minor version link”; naprawa: `UV_PYTHON_INSTALL_DIR` w `.tooling\`
  (po przekierowaniu Pyright 1.1.403 uruchamia się poprawnie).

Pierwsze wywołanie w sesji jest więc wolne (rozruch serwerów LSP); zysk dotyczy
tokenów, nie czasu.

## 4. Graphify (pilot)

Pakiet PyPI to `graphifyy` (dwa „y”), polecenie `graphify`. Instalacja jak wyżej
(ten sam venv). **Nie uruchamiaj `graphify install`** — kopiuje skill do profilu
użytkownika. Budowa grafu samego kodu, bez modelu i bez klucza API:

```powershell
# katalog repozytorium, timeout 600 s; wynik w katalogu ignorowanym
.\.tooling\venv-tokens\Scripts\graphify.exe extract services/api/src --code-only --out artifacts/graphify/api-src
.\.tooling\venv-tokens\Scripts\graphify.exe cluster-only artifacts/graphify/api-src --no-label --no-viz
.\.tooling\venv-tokens\Scripts\graphify.exe export obsidian --graph artifacts/graphify/api-src/graphify-out/graph.json --dir artifacts/graphify/api-src/obsidian
.\.tooling\venv-tokens\Scripts\graphify.exe query "SuperGameSeriesPage" --graph artifacts/graphify/api-src/graphify-out/graph.json --context call --budget 600
```

`--no-label` jest obowiązkowe: bez niego `cluster-only` może wywołać model do
nazywania społeczności. Wynik nie jest commitowany (`artifacts/` jest ignorowany).

Pomiar z 2026-10-09 (`services/api/src`, 358 plików):

- budowa grafu (`extract --code-only`): 45 s; `cluster-only`: 12 s; eksport
  Obsidian: 22 s; zero tokenów modelu;
- rozmiar: `graph.json` 20 MB, cache 21 MB, `GRAPH_REPORT.md` 56 KB, vault
  Obsidian 30 MB (9327 notatek), razem 70 MB; graf ma 9124 węzłów i 33 506
  krawędzi (203 społeczności);
- ocena użyteczności: bez modelu społeczności nie mają nazw (`Community N`), więc
  raport (56 KB) w większości jest listą numerów; węzły zawierają moduły
  biblioteki standardowej i zdania z docstringów, zapytania BFS bez filtra
  zwracają setki węzłów (261 przy budżecie 600 tokenów, wynik obcięty); z filtrem
  `--context call` zapytanie o `SuperGameSeriesPage` zwraca 6 trafnych węzłów i
  krawędzi wywołań. „God nodes” (`ApiModel`, `create_app()`, `Job`) są poprawne,
  ale już znane z architektury. Wstępna ocena: niższa wartość niż Serena przy
  większym koszcie (70 MB, ręczna regeneracja po zmianach); ostateczną decyzję
  podejmuje pomiar pilota.

## 5. Reguły pracy agentów

Reguły oszczędzania tokenów są w `AGENTS.md`, sekcja „Budżet tokenów i zgoda na
kosztowne prace” (podsekcja „Oszczędzanie kontekstu”).

## 6. Pomiar

Protokół, zadania pomiarowe, rubryka jakości i skrypt zbierający zużycie:
`ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md`,
`scripts/token_pilot_collect.py`. Raport wyników:
`ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md` (powstaje po przebiegach
operatora).
