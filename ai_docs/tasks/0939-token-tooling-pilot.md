# TASK-0939 — Narzędzia oszczędzania tokenów z pomiarem (mapa kodu, Serena, Graphify, hook)

## Status

`blocked` (narzędzia gotowe i zacommitowane w v1.7.284; pomiar 36 sesji wg `ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md` i raport z decyzjami „zostaje / wypada” wykonuje operator po zgodzie na koszt)

## Goal

Zestaw narzędzi nawigacji po repozytorium i reguł pracy, który mierzalnie
obniża tokeny wejścia typowych zadań bez spadku jakości wyniku; do stałego
użytku wchodzi tylko to, co pomiar potwierdził.

## Context

Operator chce oszczędzać tokeny, ale nie kosztem jakości. Dzisiejsze koszty:
pełne odczyty dużych plików, powtarzane wyszukiwania tego samego miejsca w
kodzie, briefy z całymi dokumentami procesu. Plan: etap T.

## Dependencies / entry conditions

- TASK-0938 niewymagany, ale zalecany wcześniej (największy koszt).
- Fakt: w repo nie ma skilli w `.claude/skills` ani `.codex/skills`; Serena
  i Graphify nie są zainstalowane. Instalacja w izolacji: osobny venv
  (`.tooling/venv-tokens`, ignorowany) i katalog wyników ignorowany.
- Założenie: dane producentów (Graphify „71,5×”, Serena „znacznie”) są
  nieweryfikowane; liczy się pomiar na tym repo.

## Recommended execution

claude-sonnet-5-5 / high. Konfiguracja narzędzi, hook, skrypt mapy kodu i
protokół pomiaru; brak logiki domenowej. Eskalacja do claude-opus-5-5 / high,
jeżeli hook lub MCP destabilizują sesję. Audyt: gpt-6.1-sol / high; do czasu CLI zamiennik claude-opus-5-5 / high.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

1. **Mapa kodu** `ai_docs/architecture/CODE_MAP.md` generowana skryptem
   `scripts/generate_code_map.py` (proponowany): obszar funkcjonalny →
   katalogi, kluczowe moduły i symbole, testy, komendy. Skrypt jest
   deterministyczny i uruchamiany po zmianach struktury; `AGENTS.md`
   wskazuje mapę jako pierwsze miejsce szukania.
2. **Serena MCP** (narzędzia symbolowe `find_symbol`,
   `find_referencing_symbols`): konfiguracja projektu dla Pythona i TS,
   indeks wstępny, wpis w ustawieniach projektu z instrukcją włączenia.
3. **Graphify**: instalacja w osobnym venv, graf repo do katalogu
   ignorowanego, eksport Obsidian; ocena użyteczności raportu grafu.
4. **Hook `PreToolUse`** w `.claude/settings.json`: odrzuca `Read` pliku
   > 200 KB bez `offset`/`limit` z komunikatem wskazującym mapę i grep.
5. **Reguły w `AGENTS.md`**: eksploracja subagentem na tańszym modelu z
   wynikiem w formie wniosków; briefy audytu tylko z taskiem, planem i
   diffem; zakaz wklejania całych dokumentów procesu do promptów.
6. **Pomiar**: trzy typowe zadania (lokalizacja miejsca zmiany w Adminie,
   zmiana domeny w API z testem, analiza błędu w workerze), każde na tym
   samym commicie repo, w niezależnych świeżych sesjach, na tym samym
   modelu i poziomie rozumowania, co najmniej 2 przebiegi na wariant.
   Warianty: baza (bez narzędzi) oraz osobno każde narzędzie 1–5; brak
   łączenia wariantów w pilocie. Metryka kosztu = **suma tokenów wszystkich
   wywołań** (agent główny + subagenci + wywołania narzędzi modelowych)
   z użycia sesji, osobno: tokeny wejścia, wyjścia, cache; koszt
   jednorazowy indeksowania (Serena, Graphify) raportowany oddzielnie i
   amortyzowany na założoną liczbę sesji. Jakość: stała rubryka na zadanie
   (kryteria akceptacji spełnione, testy zielone, audyt drugiej rodziny
   PASS); wynik gorszy od bazy dyskwalifikuje wariant niezależnie od
   tokenów. Raport `ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md` z
   tabelą wariant × zadanie × przebieg.

## Out of scope

- Zmiana stylu komunikacji (caveman) — pozostaje `lite`.
- Zmiany w kodzie produktu.

## Acceptance criteria

- [ ] Mapa kodu generuje się deterministycznie i jest zlinkowana w `AGENTS.md`.
- [ ] Hook blokuje duży odczyt bez zakresu i nie blokuje odczytu z zakresem.
- [ ] Raport pomiaru z liczbami dla każdego narzędzia i decyzją
      „zostaje / wypada”; narzędzie wchodzi do `AGENTS.md` tylko po „zostaje”.
- [ ] Instalacje nie dotykają `.venv` projektu ani `package.json`.

## Expected files

- Nowe: `scripts/generate_code_map.py`, `ai_docs/architecture/CODE_MAP.md`,
  `ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md`, wpisy w
  `.claude/settings.json` (hook), konfiguracja Serena w projekcie.
- Istniejące: `AGENTS.md`, `.gitignore` (katalogi narzędzi).

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/generate_code_map.py --check
```

## Risks / open questions

- MCP zwiększa stały koszt kontekstu (definicje narzędzi) — uwzględnić w
  pomiarze; jeśli przewyższa zysk, narzędzie wypada.
- Graphify przetwarza dokumenty przez model (koszt budowy grafu) — kod
  lokalnie; ograniczyć do kodu.

## Outcome

Stan: dostarczono całość poza przebiegami pomiaru (sekcja „Not completed”).
**Przebiegi pomiaru i raport z liczbami są zadaniem operatora i nie zostały
wykonane**; task pozostaje otwarty (lead ustawia status `blocked` na pomiar) do
czasu pomiaru i werdyktu „zostaje / wypada” dla każdego narzędzia. Narzędzia
obowiązują jako pilot do czasu pomiaru; stałe włączenie zależy od wyniku.
Commit dostarczający narzędzia ma wersję `v1.7.284` (hash dopisuje lead).

### Changed

- Commit v1.7.284 / 6f783932b05f0c11d0579086e9d464756304f046 (zapis dodany po commicie przez leada).

- **Mapa kodu:** `scripts/generate_code_map.py` generuje deterministycznie
  `ai_docs/architecture/CODE_MAP.md` (obszary: API, worker, Admin, Reviewer,
  pakiety, mobile, skrypty, docs; katalogi, moduły wejściowe z symbolami, testy,
  komendy; ok. 23 KB) oraz `CODE_MAP_SYMBOLS.md` (indeks do `rg`, jedna linia na
  moduł, ze wszystkimi publicznymi symbolami bez limitu, ok. 236 KB,
  nieprzeznaczony do czytania w całości; limit 8 symboli tylko w przeglądzie). Python z AST, TS z
  deklaracji `export`. `--check` kończy się kodem 1 dla nieaktualnej mapy (ok.
  3 s) i jest osobnym skryptem `npm run code-map:check` (`package.json`: jedyna
  zmiana tego pliku), poza `docs:check` i `quality`; zasada regeneracji przy
  zamykaniu tasku w `AGENTS.md`. Linki: `AGENTS.md` (akapit „Szukając kodu…” w kolejności czytania)
  i `ai_docs/README.md`.
- **Serena MCP:** zainstalowana w izolowanym venv `.tooling/venv-tokens` (ignorowany
  przez git; `serena-agent` 1.7.0, `uv` 0.12.24); konfiguracja projektu
  `.serena/project.yml` (Python + TypeScript, `read_only`, wyłączone narzędzia
  edycji i pamięci, ignorowane `ai_docs/`, `artifacts/`, wygenerowany klient);
  `scripts/start_serena_mcp.ps1` (start serwera lub `-Index`, stan Serena i uv
  przekierowany do `.tooling/`); wpisy `.serena/cache/`, `.serena/logs/`,
  `.serena/project.local.yml`, `.serena/memories/` w `.gitignore`. Rejestracja
  `claude mcp add` jest opisana w `ai_docs/guides/TOKEN_TOOLING.md`, bez zmian w
  ustawieniach.
- **Graphify:** `graphifyy` 0.9.82 w tym samym venv; graf `services/api/src` (tylko
  kod, bez modelu) w `artifacts/graphify/api-src` (ignorowany, niecommitowany).
- **Hook:** `.claude/settings.json` (nowy plik, wyłącznie wpis `PreToolUse` dla
  `Read`) uruchamia `scripts/hooks/block_large_read.py` (exit 2, gdy plik
  > 200 KB bez `offset`/`limit`/`pages`; obrazy i PDF wyłączone; fail-open;
  przełączniki `GAME_PREDICTOR_ALLOW_LARGE_READ`, `GAME_PREDICTOR_MAX_READ_BYTES`).
- **Reguły:** `AGENTS.md`, nowa podsekcja „Oszczędzanie kontekstu” (eksploracja
  subagentem na tańszym modelu zwracającym wnioski; brief audytu = task + plan +
  diff; zakaz wklejania całych dokumentów procesu; odczyt > 200 KB tylko z
  zakresem; narzędzia symbolowe, gdy MCP włączone).
- **Pomiar:** `ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md` (3 zadania z
  promptami i kluczami, 6 wariantów, metryka, rubryka, reguła decyzyjna, szablon
  tabeli) i `scripts/token_pilot_collect.py` (czyta transkrypty
  `~/.claude/projects/<slug>/<session-id>.jsonl` wraz z `subagents/agent-*.jsonl`,
  deduplikuje po `message.id`; `usage`, `collect`, `render`; przyjmuje także CSV
  wypełniony ręcznie).
- **Testy:** `services/api/tests/test_block_large_read_hook.py` (8 testów),
  `services/api/tests/test_token_tooling_scripts.py` (4 testy: stabilność i
  `--check` mapy, ekstrakcja symboli, deduplikacja zużycia, render tabeli).
- **Dokumentacja:** `ai_docs/guides/TOKEN_TOOLING.md`.

### Verification results

- `generate_code_map.py --check`: „up to date”, 2,8–3,0 s; `npm run code-map:check`
  i `npm run docs:check`: OK.
- pytest: `test_block_large_read_hook.py` + `test_token_tooling_scripts.py`:
  12 passed.
- Hook (komenda z `.claude/settings.json` uruchomiona przez Git Bash): plik 769 KB
  bez zakresu → exit 2 i komunikat; ten sam plik z `limit` → exit 0; mały plik →
  exit 0; syntetyczny plik 300 KB: blok, z `offset`/`limit` dozwolone; obraz/PDF,
  zły JSON, brak pliku, inne narzędzie → exit 0.
- `python -m json.tool .claude/settings.json`: poprawny JSON; `package.json`
  parsuje się.
- `ruff check` + `ruff format --check` + `mypy --strict` na nowych plikach
  Python: czyste; `npm run python:lint`: zielone; `npm run python:typecheck` (857
  plików): bez błędów; `npm run format:check`: zielone; `npm run powershell:check`: zielone.
- `powershell -File scripts/check_powershell_syntax.ps1`: poprawne (46 skryptów).
- `npx prettier --check AGENTS.md package.json`: zgodne.
- Serena, test dymny (2026-10-09): indeks zimny 47 s (2223 pliki: Python 1582, TS
  641; cache 157 MB), odświeżenie 12 s; start MCP 3–4 s; `find_symbol` (Python)
  10,7–11,5 s przy pierwszym wywołaniu, TS 5,7 s, `find_referencing_symbols`
  3,0–5,2 s; wyniki poprawne; koszt stały: 7 narzędzi, ok. 10 KB definicji (ok.
  2,6 tys. tokenów; 21 narzędzi i ok. 5,8 tys. przed wyłączeniem edycji/pamięci).
  Awarie po drodze i naprawy: brak `uvx` w PATH (uv w venv + PATH w skrypcie);
  `uvx -p 3.13` pobierający Pythona do `%APPDATA%\uv` kończył błędem (przekierowanie (usunięte przez leada 2026-10-09; katalogi nie istnieją).
  `UV_PYTHON_INSTALL_DIR` do `.tooling/`).
- Graphify: `extract --code-only` 45 s, `cluster-only --no-label --no-viz` 12 s,
  eksport Obsidian 22 s; 358 plików → 9124 węzłów, 33 506 krawędzi, 203
  społeczności bez nazw; `graph.json` 20 MB, cache 21 MB, raport 56 KB, vault 30 MB
  (razem 70 MB); zero tokenów modelu. Ocena wstępna: niska użyteczność względem
  Serena i mapy kodu (patrz `TOKEN_TOOLING.md`, sekcja 4).
- Instalacje nie dotykają `.venv` projektu; `package.json` zmieniony wyłącznie
  dodaniem skryptu `code-map:check`.

### Not completed

- **Przebiegi pomiaru (zakres punktu 6 taska) nie zostały wykonane**: wymagają 36
  niezależnych, świeżych sesji uruchamianych przez operatora i ich raportów
  zużycia; agent wykonawczy nie może ich uruchomić. Dostarczono protokół,
  skrypt zbierający i szablon tabeli. Brakuje raportu
  `ai_docs/quality/TOKEN_TOOLING_PILOT_<data>.md` z liczbami, więc kryterium
  akceptacji „Raport pomiaru z liczbami… decyzja zostaje / wypada” jest
  niespełnione, a narzędzia pilotowe (Serena, Graphify) nie mają stałego wpisu w
  `AGENTS.md`.
- Audyt Codex (gpt-6-astra / medium) runda 1: REVISE; poprawki P0-1..P2-2
  wykonane w tej samej rundzie (niżej); ponowny audyt tylko na żądanie operatora.
- Rejestracja Serena w Claude Code (`claude mcp add`) jest decyzją operatora.
- Po nieudanej pierwszej próbie `uvx` zostały poza repozytorium pliki:
  `C:\Users\tuszy\AppData\Roaming\uv` (ok. 67 MB, pobrany Python 3.13) i
  `C:\Users\tuszy\AppData\Local\uv` (14 KB). Usunięcie zostało odrzucone przez
  piaskownicę; do skasowania ręcznie przez operatora (nic ich nie używa).
- Nie uruchamiano `npm run typecheck`/`lint` dla TS (brak zmian w kodzie TS).

### Poprawki po audycie (runda 1)

- **P0-1:** pomiar pozostaje po stronie operatora; Outcome i „Not completed” mówią
  to jawnie, task jest otwarty.
- **P0-2:** `AGENTS.md` oznacza regułę mapy kodu i podsekcję „Oszczędzanie
  kontekstu” zdaniem „pilot TASK-0939: obowiązuje do czasu pomiaru; stałe
  włączenie zależy od wyniku”; ten sam status w akapicie o hooku w
  `TOKEN_TOOLING.md`. Kontrola aktualności mapy wyjęta z `docs:check`/`quality` do
  `npm run code-map:check`; reguła utrzymania w `AGENTS.md`: regeneracja przy
  zamykaniu tasku zmieniającego moduły lub publiczne symbole.
- **P1-1:** protokół definiuje `<PILOT>` jako commit dostarczający narzędzia
  (`v1.7.284`), nie commit zamykający.
- **P1-2:** protokół ma jawne przygotowanie worktree (dowiązanie `.venv`, nakładka
  plików, venv, instalacja, indeks, graf) i kontrolę dostępności przed każdą
  sesją; `start_serena_mcp.ps1` przy braku venv wypisuje polecenia naprawcze (kod
  2; sprawdzone na kopii skryptu bez venv).
- **P2-1:** `CODE_MAP_SYMBOLS.md` zawiera wszystkie symbole modułu; limit 8 tylko w
  `CODE_MAP.md`; test `test_symbol_index_lists_every_symbol_and_check_detects_a_late_rename`.
- **P2-2:** wersje przypięte w komendach instalacji (`serena-agent==1.7.0`,
  `graphifyy==0.9.82`, `uv==0.12.24`); `start_serena_mcp.ps1 -Index` wypisuje
  zainstalowane wersje na początku logu indeksu (sprawdzone).
- Wyniki po poprawkach: `npm run docs:check`, `npm run code-map:check`, 13 testów
  pytest (hook + skrypty), `ruff check`/`format --check`, `mypy --strict`
  (nowe pliki Python), `prettier --check AGENTS.md package.json`,
  `python -m json.tool .claude/settings.json`: zielone.

### Documentation updates

- `AGENTS.md`, `ai_docs/README.md`, nowe: `ai_docs/architecture/CODE_MAP.md`,
  `CODE_MAP_SYMBOLS.md`, `ai_docs/guides/TOKEN_TOOLING.md`,
  `ai_docs/quality/TOKEN_TOOLING_PILOT_PROTOCOL.md`.
- `CURRENT_STATE.md`: sekcja TASK-0939 zaktualizowana (`in_progress`). Brak wpisu
  w `DECISION_LOG.md`: nie zmieniono modelu domenowego ani architektury produktu.

### Recommended next task

Pomiar pilota wg `TOKEN_TOOLING_PILOT_PROTOCOL.md` (najpierw jeden przebieg
kalibracyjny `baseline`/A i zgoda operatora na koszt całości), potem raport
`TOKEN_TOOLING_PILOT_<data>.md`, decyzje „zostaje / wypada”, wpis stałych narzędzi
w `AGENTS.md` i zamknięcie TASK-0939.
