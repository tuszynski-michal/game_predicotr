# Audyt TASK-1169 — Spójność rewizji schematu przy cutover

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: c0bf03684523a06e4556e53269c3c01880043134 oraz zmiany niezacommitowane z zamrożonego pakietu, data 2026-11-09
Runda: 1
SHA pakietu: 320b590e55e90c13da93150286e3c5fa10d25f7619b99cfbf2fe5395b75bfc70
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano strażnika startowego, jego użycie w API i workerze, statyczną kontrolę `schema_readiness`, nowe testy oraz procedurę merge i cutover. Strażnik pozostaje dokładnym porównaniem z głową 0183. Preflight czyta przypięty commit i przy błędach grafu kończy stanem blokującym. Nie znaleziono ścieżki fałszywie zielonego wyniku. Pozostają dwa ryzyka P2: luki w syntetycznych przypadkach grafu oraz niepełne wskazanie gałęzi w instrukcji cutover.

Oczekiwany mismatch 181↔183 na c0bf0368 nie jest defektem nowego kodu. Pełne restarty usług pozostają krokiem po integracji i nie są przedstawiane jako sukces.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `F/services/worker/tests/test_integration_preflight_script.py:401` — Parametryzacja pokrywa cykl odłączony od głowy, który wykrywa kontrola osiągalności (`F/scripts/integration_preflight.py:256`). Nie ma przypadku cyklu osiągalnego z głowy (gałąź `active`, linie 245–246), duplikatu rewizji (linia 221) ani udanego scalenia krotką (linia 228). Skutek jest ograniczony: regresja tych gałęzi prowadziłaby praktycznie do `unknown` lub dodatkowej głowy, a graf rzeczywisty według raportu roota przeszedł analizę aż do stanu mismatch. Poprawka: dodać trzy przypadki do istniejących testów albo zaakceptować ryzyko.
- [P2-2] `F/ai_docs/guides/LOCAL_OPERATION_GUIDE.md:489` — Instrukcja nie podaje gałęzi ani katalogu uruchomienia, a krok 3 zakłada checkout usług. Uruchomienie bez argumentu na `main` kończy się kodem 1, bo gałąź jest bazą (`F/scripts/integration_preflight.py:415`, `:677`, `:679`). Zachowanie jest bezpieczne, ponieważ nie daje zgody, ale operator nie dostaje wskazówki, jak zaliczyć bramkę. Poprawka: zapisać wywołanie `integration_preflight.py <gałąź> --json` z worktree gałęzi przed scaleniem i dodać, że kod 1 również zatrzymuje wdrożenie.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| Guard: head 0183, opis manifestu v22, porównanie dokładne, jeden SELECT | spełnione | `F/services/api/src/game_predictor_api/storage/schema_readiness.py:3`, `:18`, `:38`, `:50` |
| Guard: API i worker używają tej samej funkcji, bez bypassu | spełnione | `F/services/api/src/game_predictor_api/__main__.py:13`, `:21`, `:35`; `F/services/worker/src/game_predictor_worker/cli.py:43-46`, `:404`. Wcześniejsza ścieżka `mark_lane_stopped` (`cli.py:392`) kończy się przed obsługą jobów. |
| Guard: odrzucenie None, 0181, 0182 i przyszłej rewizji | spełnione | `F/services/api/tests/test_schema_readiness.py:63`, `:84-86`, `:89-94` |
| Guard: dynamiczny ScriptDirectory i łańcuch 183→182→181 | spełnione | Tamże `:16-24`; `F/services/api/alembic/versions/0183_production_cell_evaluation.py:13-14`; `0182_cell_content_references.py:5-6`; `0181_validation_purposes.py:22` |
| Graph/ref: odczyt z `branch_tip`, bez bieżących plików | spełnione | `F/scripts/integration_preflight.py:204`, `:218`, `:488` |
| Graph/ref: AST i `literal_eval`, bez DB, importów i wykonania | spełnione | Tamże `:166-183`, `:204`, `:218` |
| Graph/ref: unikalność, rodzice, krotki, cykl, osiągalność, jedna głowa | spełnione | Tamże `:221-257` |
| Fail-closed: `unknown` jako stan domyślny, wyjątki blokują | spełnione | Tamże `:188-195`, `:266-267` |
| Fail-closed: N/A tylko bez źródeł API, brak guardu lub migracji blokuje | spełnione | Tamże `:196-202`, `:214-215` |
| Fail-closed: kontrakt raportu, warning, exit 0 / exit 1 | spełnione | Tamże `:188-195`, `:505-507`, `:610-616`, `:679-686` |
| Regresja: nowa migracja daje mismatch, zgodny guard daje matched | spełnione | `F/services/worker/tests/test_integration_preflight_script.py:351-377`. Test sprawdza stan, blokadę, head, głowy i warning. |
| Regresja: brudny checkout i inna gałąź | spełnione | Tamże `:380-398`. Dyskryminuje brudny guard i niepoprawny plik migracji. |
| Regresja: uszkodzony graf | spełnione, z P2-1 | Tamże `:401-441` |
| Regresja: brak importu i wykonania | spełnione | Tamże `:342-348` (pliki z `raise RuntimeError`) oraz `:586-607` (read-only, ścieżka N/A) |
| Procedura: canonical i mirror wymagają matched/false mimo exit 0, także tuż przed merge | spełnione | `F/.claude/skills/merge-to-main/SKILL.md:95-100`, `:169-171`; `F/.agents/skills/merge-to-main/SKILL.md:95-96`, `:170-171`; identyczne SHA w manifeście |
| Procedura: instrukcja cutover | spełnione, z P2-2 | `F/ai_docs/guides/LOCAL_OPERATION_GUIDE.md:489-495` |
| Mapy i dokumenty, tylko delta | spełnione | `artifacts/audits/TASK-1169_R1_DELTA.diff:53-116` |
| Uczciwość QA: poprzedni FAIL, przerwany zestaw, status restartów | spełnione | `F/ai_docs/quality/TASK-1169_VERIFICATION.md:11-17`, `:36-40`, `:51-56` |
| Liczby testów wykonawcy | niezweryfikowane uruchomieniem | Plik preflight ma 39 przypadków, zgodnie z 12 + 27. Plik guardu ma 28 przypadków; 29. test workera jest poza pakietem. |
| Rzeczywisty restart API/workerów i matched po commicie | niezweryfikowane, poza tym etapem | Jawnie odłożone: `F/ai_docs/quality/TASK-1169_VERIFICATION.md:38-39`, `:54` |

## Listy zamknięte i otwarte

Zamknięte: Brak.

Otwarte: P2-1, P2-2.

## Proponowane testy

- W `services/worker/tests/test_integration_preflight_script.py` dodać cykl osiągalny z głowy i duplikat rewizji (oczekiwane `unknown`) oraz scalenie krotką (oczekiwane `matched`). Polecenie: `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_integration_preflight_script.py -k schema`.
- Po commicie poprawki odnotować w raporcie wynik `schema_readiness` dla rzeczywistego czubka gałęzi; wymagane są `matched` i `blocks_merge=false`.

## Zakres przeglądu i ograniczenia

Przeczytano manifest, szablon i całą deltę, w całości `scripts/integration_preflight.py`, `schema_readiness.py`, oba pliki testów, `__main__.py` API i migracje 0182/0183. Z pliku 0181 odczytano nagłówek rewizji, z `cli.py` import i fragment 385–419, a z canonical SKILL linie 30–204. W kopii `.agents` sprawdzono zgodność przez deltę, wyszukiwanie i SHA z manifestu, a w instrukcji operacyjnej sekcję 468–527.

Nazwa `require_database_schema` występuje wyłącznie w API. Worker wywołuje bezpośrednio `require_alembic_head`.

Nie uruchamiano testów, poleceń, bazy ani usług. Nie przeliczano skrótów SHA, ponieważ narzędzia tylko do odczytu na to nie pozwalają; porównano wartości deklarowane. Pełny graf migracji jest poza pakietem, dlatego jego analiza opiera się na raporcie roota i testach dynamicznych. Definicja manifestu v22 również jest poza pakietem; sprawdzono jego opis w strażniku i dokumentach. Wyniki testów i odczyt bazy pochodzą z raportu wykonawcy i roota.