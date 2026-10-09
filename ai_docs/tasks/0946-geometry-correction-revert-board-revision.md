# TASK-0946 — Cofnięcie korekty istniejącej planszy (rewizja N + 1 = N − 1)

## Status

`todo`

## Goal

`GeometryCorrectionRevertService.revert` obsługuje korekty istniejących plansz (przypadek A): zapisuje rewizję `N + 1` z geometrią `N − 1` i przywraca decyzje komórek sprzed korekty.

## Context

Plan `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`, sekcje „Przypadek A”, „Warunki dopuszczenia”, „Założenia” (Z1, Z2).

## Dependencies / entry conditions

- TASK-0945 ukończony (migracja `0153`, status `reverted`, serwis, audyt, warunki wspólne).

## Recommended execution

`claude-opus-5-5`, reasoning `high`: odtwarzanie decyzji komórek z historii i render nowej rewizji; ryzyko utraty zatwierdzeń człowieka. Eskalacja: Z1 nie zachodzi i fallback blokuje typowe korekty → zatrzymaj i zapytaj operatora. Review: Codex `gpt-6-astra`, `high`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GEOMETRY_CORRECTION_REVERT_EXECUTION_PLAN.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — D-462, D-467, D-488

## Scope

- Weryfikacja Z1 (wspólne `created_at` zdarzeń komórek jednej transakcji) w kodzie (`image_symbol_review_events.created_at` `server_default now()`, brak jawnego ustawiania) i teście PG. Wynik zapisz w `Outcome`.
- Wyznaczenie geometrii `N − 1` (wiersz rewizji planszy albo wpis slotu poprzedniej rewizji źródła dla `N − 1 = 0`) i poprzedniej rewizji źródła.
- Zapis rewizji `N + 1` wskazującej poprzednią rewizję źródła (bez dopisywania nowej rewizji źródła), manifest renderu `N + 1`, projekcja planszy, zdarzenie `geometry_reverted`.
- Komórki: render `N + 1`, przywrócenie decyzji z najwcześniejszego zdarzenia transakcji korekty, reguła zatwierdzenia po pikselach (D-462), reguła `assignment_source` z planu, zdarzenie komórki `geometry_reverted` z pełnymi `previous_*`.
- Warunek `GEOMETRY_REVERT_REOPENED_RESOLUTION` i pozostałe warunki wspólne dla A.
- Rewizja źródła korekty `reverted`, odwrotne przepięcie sąsiadów, liczniki, wyszukiwarka, wersja supergry, bramka kompletności, audyt (`kind = board_revision`, migawka stanu komórek przed i po).
- Wzorzec przepisania z zachowaniem decyzji: `_convert_current_cells` (`storage/virtual_grid_geometry_repository.py:1107`).

## Out of scope

- Przywracanie roszczenia kanonicznego (odmowa kodem), cofanie dowolnej starszej rewizji, HTTP, UI.

## Acceptance criteria

- [ ] Korekta planszy z komórkami `grid_issue` → cofnięcie → komórki znów `grid_issue`, plansza w widoku `correction`, geometria równa `N − 1`, `approved_geometry_revision` równe wartości sprzed korekty.
- [ ] Korekta z symbolami D-488 → cofnięcie przywraca poprzednie symbole/stany; zatwierdzenia sprzed korekty wracają tylko przy identycznych pikselach.
- [ ] Korekta, która ponownie otworzyła rozstrzygniętą pozycję → 409 `GEOMETRY_REVERT_REOPENED_RESOLUTION` bez zapisu.
- [ ] Drugie cofnięcie → `GEOMETRY_REVERT_NOT_LATEST`; nowa korekta po cofnięciu działa (rewizja `N + 2`).
- [ ] Liczniki, wyszukiwarka i bramka zdjęcia równe stanowi sprzed korekty (porównanie w teście PG).

## Technical notes

- `N + 1` jest nową rewizją append-only; nie obniżaj `geometry_revision`.
- `geometry_approved_at/by`: ze zdarzenia geometrii planszy, którego `approved_geometry_revision` = przywracana wartość; brak → `NULL`.
- Zdarzenia D-488 (`reassign`, `mark_unreadable`) w transakcji korekty mają `previous_*` sprzed symboli, ale po `geometry_invalidated`; bierz najwcześniejsze zdarzenie komórki w transakcji.

## Expected files

- Zmieniane: `application/geometry_correction_reverts.py`, `domain/geometry_correction_reverts.py`, `storage/geometry_correction_revert_repository.py` (z TASK-0945).
- Nowe (proponowane): `services/api/tests/integration/test_geometry_correction_revert_board_postgres.py`; testy jednostkowe w `services/api/tests/test_geometry_correction_reverts.py`.

## Test cases

- Pierwsza korekta planszy (N = 1, N − 1 = 0) z `grid_issue` → pełne przywrócenie.
- Druga korekta (N = 2) → geometria z rewizji 1.
- Korekta z symbolami narzuconymi D-488 → wycofanie symboli.
- Zmiana croppera (symulowana) → zatwierdzenia wracają jako `pending` z podpowiedzią.
- Reguła `assignment_source` dla zdarzeń bez `previous_assignment_source`.
- Odmowy: późniejsza weryfikacja, reopened, nowsza rewizja źródła, CAS.

## Verification

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_geometry_correction_reverts.py services/api/tests/integration/test_geometry_correction_revert_board_postgres.py services/api/tests/integration/test_geometry_correction_revert_pending_postgres.py -q
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_correction_cell_symbols_postgres.py services/api/tests/integration/test_cell_render_specs_postgres.py -q
npm run python:lint
npm run python:typecheck
```

## Risks / open questions

- Z1 i Z2 z planu.

## Outcome

Wypełnia agent po pracy.
