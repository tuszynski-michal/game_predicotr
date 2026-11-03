# Audyt TASK-1153 — Propozycje modelu w korekcie i pełny kadr

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...c6f9597a0cbaf8c3a2d27966a586693ab2498fde oraz zmiany niezacommitowane, data 2026-11-03
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zgodnie z sekcją „Focused review” w pliku taska ta runda sprawdza tylko, czy zamknięto uwagi P1-1, P2-1, P2-2 i P2-3 z `TASK-1153_AUDIT_ROUND1.md`, oraz dowody w `TASK-1153_VERIFICATION.md`.

Wszystkie cztery uwagi są zamknięte:
- **P1-1:** test renderera ma adnotacje i jawny błąd ładowania. Strict mypy przeszedł, co potwierdza log.
- **P2-1:** komendy uruchomienia testów są zapisane w dokumentacji.
- **P2-2:** komunikaty po decyzji zostają na ekranie, a odrzucenie odczytuje bieżący kursor i zachowuje historię.
- **P2-3:** błąd API jest oddzielony od niezgodności wersji, a przy niezgodności działa przycisk „Odśwież kolejkę”.

Zostaje jedna drobna luka w dowodach. Kilka kontroli zadeklarowanych „po poprawkach” nie ma logu z czasem po ostatniej edycji plików.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-4] `ai_docs/quality/TASK-1153_VERIFICATION.md:41` — weryfikacja deklaruje, że po poprawkach przeszły: testy Reviewera 59/59, scoped ESLint, Ruff, `docs:check` i `code-map:check`. Logi w `D:/game_predicotr/artifacts/task1153/` tego nie potwierdzają:
  - `reviewer-lint.log` i `admin-lint.log` pochodzą z 15:40, a `docs-check.log` i `code-map-check.log` z 15:44, czyli sprzed audytu rundy 1 (`audit.log`, 15:50). Logu Ruff po poprawkach nie ma.
  - `reviewer-postaudit.log` (59/59) zapisano o 15:54:25. Tymczasem `board-geometry-correction-workspace.tsx`, `correction-grid-proposals.tsx` i oba pliki testów interakcji zmieniły się o 15:54:42–43, zapewne przy formatowaniu Prettierem.
  - Treść końcową obejmuje tylko build Reviewera z 15:56:47 (pełny TypeScript, 7/7 stron).

  **Skutek:** ryzyko jest niskie, bo późna zmiana wygląda na samo formatowanie, a build przeszedł na wersji końcowej. Mimo to deklaracja „PASS po poprawkach” nie ma pełnego dowodu w logach.

  **Poprawka:** przy `task-close` uruchomić ponownie testy interakcji Reviewera, scoped ESLint, Ruff, `docs:check` i `code-map:check`, zapisać nowe logi i dopiero potem zamknąć task. Można też przyjąć ryzyko z adnotacją w weryfikacji.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Propozycje w korekcie bez POST na otwarciu; ten sam workflow accept/edit/reject; konflikty, retry i spóźnione odpowiedzi nie przechodzą na inną planszę | spełnione | `correction-grid-proposals.tsx` (tylko GET, porównanie sześciu pól tożsamości, flaga `active`, osobny stan `stale`); `board-geometry-correction-workspace.tsx:366-398`; `grid-geometry-proposals.tsx:92-95` (cleanup `onEditingChange(false)`), `:252-253`; testy `board-geometry-correction.test.mjs:1255`, `:1286`, `grid-geometry-proposals.test.mjs:606`, `:663`; `reviewer-postaudit.log` 59/59 |
| Skrót nie uruchamia treningu ani rozpoznania; pilot/broader zachowane | spełnione | ocena rundy 1 bez zmian w tej części; `Admin 16/16` w weryfikacji |
| Szerszy i pełny kadr w obu widokach; kadr nie zmienia geometrii; regresja 35% | spełnione | ocena rundy 1; `board-geometry-correction-workspace.tsx:400`; `reviewer-postaudit.log` (test „full-photo viewport … legacy framing stays unchanged”) |
| Renderer HTML nie myli zmian z trafnością; provenance zachowane; raport przebudowany | spełnione | ocena rundy 1; `report-postaudit.log` 3/3 OK; `python-types.log`: „Success: no issues found in 2 source files” |
| Testy, lint/typecheck/build, docs/map, Opus bez P0/P1, task-close i commit | niezweryfikowane | Opus bez P0/P1 jest spełnione tym raportem. Build Reviewera (15:56:47) obejmuje wersję końcową. Logi lint/docs/map są sprzed poprawek (P2-4). `task-close` i commit jeszcze się nie odbyły |

## Listy zamknięte i otwarte

Zamknięte:
- **P1-1:** `scripts/tests/test_grid_correction_comparison.py:12` ma jawny `RuntimeError`, gdy `spec` albo `spec.loader` jest `None`. Adnotacje są w `:19`, `:84`, `:89`, `:108`, `:118`. Atrybuty `module.*` są typu `Any` przez `ModuleType.__getattr__`, więc strict mypy ich nie odrzuca. Plik mieści się w `line-length = 100` (`pyproject.toml:82`). Strict mypy przeszedł: `python-types.log` z 15:54:13, plik testu zmieniono o 15:53:55, a renderer o 15:38.
- **P2-1:** `ai_docs/architecture/VISION_LAB.md:1115-1116` podaje komendy `unittest discover` i `mypy` oraz to, że testy nie wchodzą do `python:test`. Komenda `discover -s scripts/tests` działa bez `__init__.py`.
- **P2-2:**
  - `board-geometry-correction-workspace.tsx:372-381`: przyjęcie ustawia komunikat, a potem woła `loadPage(undefined, { preserveNotice: true, resetHistory: true })`.
  - `:382-389`: odrzucenie ustawia komunikat i woła `loadPage(history.at(-1)?.nextCursor, { preserveNotice: true })`. To kursor bieżącej strony zgodnie z `showNext` (`:203-209`), a historia zostaje zachowana.
  - Test: `board-geometry-correction.test.mjs:1255` (`afterCursor === '1'`, aktywny przycisk „← Poprzednia”, ta sama plansza, komunikat, brak zapisu).
- **P2-3:**
  - `correction-grid-proposals.tsx`: `result.error` i brak `data` dają komunikat błędu z `stale=false`, a niezgodność tożsamości daje `stale=true`.
  - Przycisk „Odśwież kolejkę” pojawia się tylko przy `stale && onReloadQueue`, a w workspace jest podpięty pod odczyt bieżącego kursora (`:390-397`).
  - Testy: `board-geometry-correction.test.mjs:1286` (pierwsza plansza, odczyt nowej rewizji 3) i `grid-geometry-proposals.test.mjs:663`.

Otwarte: P2-4.

## Proponowane testy

- Przed `task-close` ponownie uruchomić testy interakcji Reviewera na wersji końcowej: `npm run test:geometry --workspace @game-predictor/reviewer`. Do tego `npm run lint --workspace @game-predictor/reviewer`, `.\.venv\Scripts\python.exe -m ruff check scripts/render_grid_correction_comparison.py scripts/tests/test_grid_correction_comparison.py`, `npm run docs:check` i `npm run code-map:check`. Logi zapisać w `artifacts/task1153/`.
- Opcjonalnie w `apps/reviewer/test-interactions/grid-geometry-proposals.test.mjs`: po niezgodności tożsamości kliknąć „Odśwież propozycje” i sprawdzić, że przycisk „Odśwież kolejkę” znika, gdy kolejny odczyt jest zgodny.

## Zakres przeglądu i ograniczenia

Przeczytałem:
- brief rundy 2 (task, plan, diff, nowe pliki, raport rundy 1, weryfikację);
- w worktree `board-geometry-correction-workspace.tsx` w całości oraz `grid-geometry-proposals.tsx:86-263`, czyli cleanup `onEditingChange`, ścieżki accept/reject i wywołania `onChanged`/`onRejected`;
- w `pyproject.toml` konfigurację mypy (strict, `explicit_package_bases`) i ruff, a w `package.json` skrypty `python:typecheck`, `typecheck` i `quality`;
- logi wykonawcy w `D:/game_predicotr/artifacts/task1153/` wraz ze znacznikami czasu względem plików.

Zgodnie z zakresem rundy 2 nie audytowałem ponownie części ocenionych pozytywnie w rundzie 1: Admina, edytora kadru, renderera HTML i szablonu.

Nie uruchamiałem testów, lintu, typechecku ani buildów, bo mypy, pytest i build zapisują cache albo artefakty. Wnioski o mypy wynikają z analizy statycznej i z logu wykonawcy. Nie oglądałem UI ani HTML w przeglądarce.
