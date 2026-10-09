---
title: Exact super game series counter
status: done
last_updated: 2026-10-09
---

# TASK-0951 — Dokładny licznik serii supergry

## Status

done

## Goal

Sekcja „Supergry” pokazuje dokładną liczbę serii bez super symbolu i liczbę
wszystkich serii gry zamiast dolnego ograniczenia `200+`.

## Context

Operator widzi w sekcji „Supergry” Mumii licznik `200+` i nie wie, ile serii
jest łącznie ani ile zostało do zdefiniowania. Licznik z TASK-0934 liczył
serie bez symbolu jedną stroną `defined=false&limit=200`, więc przy większej
liczbie pokazywał tylko dolną granicę. Odczyt API 2026-10-09 (ostatnia
opublikowana generacja, `fresh = false`): 2553 serie, 4 z super symbolem,
2549 do zdefiniowania.

## Dependencies / entry conditions

Gałąź integracyjna `v1.1-vision-lab-hybrid-geometry` v1.7.296. Bez migracji:
liczniki to `COUNT` na istniejącej tabeli `super_game_series`. Bez zmian
danych i bez cyklu życia usług.

## Recommended execution

Claude Opus 5.5 / medium w bieżącej sesji (mała zmiana kontraktu API i
widoku, zlecona bezpośrednio przez operatora, bez planu). Eskalacja tylko
przy konflikcie z D-535/D-536. Audyt per task zawieszony przez operatora
(2026-10-01); wykonawca robi samoaudyt.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md` (sekcja „Supergry”)
- `ai_docs/architecture/API_CONTRACT.md` (serie supergry)

## Scope

- `SuperGameSeriesListResponse.counts { total, undefined }`: dokładne liczby
  wszystkich serii gry i serii bez super symbolu, niezależne od filtrów,
  kursora i limitu, z tego samego odczytu (snapshot) co strona.
- Admin: licznik „<undefined> z <total> serii bez super symbolu” z `counts`
  każdej strony listy; usunięcie osobnego zapytania licznika i
  `UNDEFINED_COUNT_LIMIT`.
- OpenAPI, wygenerowany klient, testy API, testy PostgreSQL i testy Admina;
  aktualizacja `ADMIN_APP.md` i `API_CONTRACT.md`.

## Out of scope

- Przeliczenie serii (`derive`) i zmiana danych operatora.
- Liczniki w innych sekcjach.

## Acceptance criteria

- [x] Lista serii zwraca `counts` niezależne od filtrów i strony; gra `none`
  zwraca `{ total: 0, undefined: 0 }`.
- [x] Licznik w Adminie pokazuje dokładne wartości, bez `200+`.
- [x] Zapis super symbolu odświeża licznik (przeładowanie listy).
- [x] Testy API, PostgreSQL i Admina przechodzą; OpenAPI i klient zgodne.

## Technical notes

`SqlAlchemySuperGameSeriesRepository.series_counts` wykonuje jedno
`SELECT count(*), count(*) FILTER (WHERE super_symbol_id IS NULL)` dla gry,
po `begin_read_snapshot`, więc liczniki opisują tę samą generację co strona.
Zapis symbolu już wywołuje `reloadList()`, więc nowa pierwsza strona niesie
nowe liczniki.

## Expected files

- `services/api/src/game_predictor_api/application/super_game_series.py`
  (`SuperGameSeriesCounts`, `SuperGameSeriesPage.counts`, `series_counts`)
- `services/api/src/game_predictor_api/storage/super_game_series_repository.py`
- `services/api/src/game_predictor_api/schemas/super_game_series.py`
  (`SuperGameSeriesCountsResponse`)
- `packages/admin-api-client/openapi/openapi.json`, wygenerowany klient
- `apps/admin/src/features/super-games/super-game-series-state.ts`,
  `super-game-series-workspace.tsx`
- testy: `services/api/tests/test_super_game_series_api.py`,
  `services/api/tests/integration/test_super_game_series_postgres.py`,
  `apps/admin/test/super-game-series-state.test.mjs`,
  `apps/admin/test/super-game-series-workspace-contract.test.mjs`

## Test cases

- Trzy serie (jedna z symbolem): `counts = { total: 3, undefined: 2 }` bez
  filtrów, z `defined=true&limit=1` i z `completeness=incomplete`.
- PostgreSQL: po derive (3, 3), po zdefiniowaniu (3, 0), po przeliczeniu z
  usunięciem dwóch serii (1, 0).
- Admin: kolejna strona podmienia liczniki; zmiana filtrów zachowuje je do
  nadejścia nowej strony; etykieta „2549” / „z 2553 serii bez super symbolu”.

## Verification

```powershell
# z worktree, PYTHONPATH na src worktree, timeout 120 s (PostgreSQL 600 s)
..\..\.venv\Scripts\python.exe -m pytest services/api/tests/test_super_game_series_api.py -q
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; ..\..\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_super_game_series_postgres.py -q -k "generation_swap or never_pair or none_kind"
npm run openapi:check
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
```

## Risks / open questions

- Liczniki opisują ostatnią opublikowaną generację; przy `fresh = false`
  mogą się zmienić po przeliczeniu serii (baner o tym informuje).

## Outcome

### Changed

- API: `SuperGameSeriesCounts`, `SuperGameSeriesPage.counts`,
  `SqlAlchemySuperGameSeriesRepository.series_counts` (jedno zapytanie
  `count(*)` z `FILTER`), `SuperGameSeriesCountsResponse` i pole
  `counts` w `SuperGameSeriesListResponse`.
- Admin: licznik z `counts` każdej strony listy, etykieta
  „<undefined> z <total> serii bez super symbolu”; usunięte
  `UNDEFINED_COUNT_LIMIT`, `undefinedSeriesCountQuery`,
  `undefinedSeriesCount`, `applySeriesListUndefinedCount` i osobny efekt
  pobierający licznik.
- OpenAPI, wygenerowany klient, eksport typu w `packages/admin-api-client/src/index.ts`,
  `ADMIN_APP.md`, `API_CONTRACT.md`, mapa kodu.

### Verification results

- `test_super_game_series_api.py`: 10 passed.
- PostgreSQL (`-k "generation_swap or never_pair or none_kind"`): 3 passed.
- Admin `npm run test`: 733 pass, 0 fail; typecheck PASS; lint 0 errors
  (5 ostrzeżeń w niezmienionych plikach).
- ruff, mypy (3 zmienione moduły), prettier, `export_admin_openapi.py --check`,
  `check:generated`, `check_current_state_window.py` PASS.
- Odczyt API Mumii 2026-10-09: 2553 serie, 4 z super symbolem, 2549 do
  zdefiniowania; generacja `fresh = false` (input 11887, generacja 11571).

### Not completed

- Brak widoku w przeglądarce na żywym API: API 8000 działa z głównego
  checkoutu i pokaże `counts` dopiero po scaleniu (przeładowanie `--reload`).
- Pełne `npm run quality` nie było uruchamiane; uruchomiono bramki zmienionych
  obszarów.

### Documentation updates

- `ai_docs/requirements/ADMIN_APP.md`, `ai_docs/architecture/API_CONTRACT.md`,
  `CODE_MAP.md`, `CODE_MAP_SYMBOLS.md`, `CURRENT_STATE.md` (sekcja TASK-0936
  przeniesiona do archiwum Q4).

### Recommended next task

- Po scaleniu: „Przelicz serie” dla Mumii (generacja nieświeża), potem
  sprawdzenie licznika w Adminie.
