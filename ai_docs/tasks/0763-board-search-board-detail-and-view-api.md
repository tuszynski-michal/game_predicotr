---
title: TASK-0763 — API szczegółów planszy z liniami wypłat i przyciętego widoku planszy
status: todo
last_updated: 2026-09-30
---

# TASK-0763 — API szczegółów planszy z liniami wypłat i przyciętego widoku planszy

## Status

`todo`

## Goal

Endpointy `getBoardSearchBoardDetail` i `getBoardSearchBoardView` zwracają linie wypłat jednej planszy i przycięty obraz z wielokątami pól, dla obu źródeł danych wyszukiwania, i są w kliencie TypeScript.

## Context

Punkt 1 (dane do modala) i przygotowanie punktu 5 (przycięte obrazy). Ewaluator `PreparedPayoutEvaluator.evaluate` już zwraca `matches`; kalkulator zakresu je odrzuca. Plan: §3 R2–R3, §4.1–4.2, §5 T4.

## Dependencies / entry conditions

- TASK-0760 done.
- Niewiadoma: czy archiwum `legacy_archive` ma geometrię pól. Rozstrzyga ten task; bez dowodu `cellPolygons = null`.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Pion API, dwa źródła danych, geometria, pliki i cache. Audyt: niezależny agent `claude-opus-5-5` (`high` warunkowo — poziomu agenta nie da się ustawić jawnie). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/requirements/ALGORITHMS.md`

## Scope

- Wydzielenie budowy ewaluatora z `BoardSearchApproximateWinService.calculate` do wspólnej metody bez zmiany zachowania zakresu.
- Endpoint szczegółów planszy (§4.1) z liniami, kodami symboli i `view`.
- Endpoint widoku (§4.2): WebP, obrys + 20%, dłuższy bok ≤ 1280 px, cache plikowy z atomowym zapisem i ograniczeniem rozmiaru.
- Pion API: schematy, OpenAPI, wygenerowany klient, wrapper, test żądania.
- `API_CONTRACT.md`.

## Out of scope

- UI modala (TASK-0764).
- Zmiana algorytmu wypłat lub rankingu.
- Zmiana karuzeli Admina (TASK-0765).

## Acceptance criteria

- [ ] `sum(matches.payoutCredits) == payoutCredits` dla każdej planszy.
- [ ] Plansza przycięta z lewej (kolumna 1 = `?`, kolumny 2–5 tworzą ciąg) daje `matches = []`, `payoutKind = none`.
- [ ] Plansza przycięta z prawej z pełnym prefiksem daje `confirmed_minimum`.
- [ ] Błędy: 404 gry/planszy, 409 reguł/projekcji/symbolu spoza reguł, 409 konfliktu checksumy widoku, odmowa niebezpiecznej ścieżki.
- [ ] Geometria planszy z inną checksumą niż `boardChecksumSha256` dokumentu daje 409 `BOARD_SEARCH_BOARD_REVISION_CONFLICT` w szczegółach i widoku.
- [ ] Drugi odczyt widoku pochodzi z cache i ma identyczne bajty; równoległe żądania renderują raz.
- [ ] Istniejące testy `test_board_search_approximate_win_*` przechodzą bez zmian; `openapi:check` PASS.

## Technical notes

Szczegóły: dokument planszy czytany tym samym źródłem co wyszukiwanie
(`_document_source`) — nowa metoda repozytorium (proponowana)
`board_document(game_id, sequence_number)` zwraca dokument razem z
tożsamością operacyjną (`review_item_id`, `recognized_board_id`,
`import_job_id`) albo archiwalną (`board_relative_path`), wyłącznie do
użytku wewnętrznego. `payoutKind`: `none` gdy suma 0, `exact` dla
kompletnej, `confirmed_minimum` dla częściowej. Mapowanie `payline_id` →
kod, nazwa, `display_order`, `row_path` z tej samej wersji reguł
(`RulesPayoutConfiguration` — sprawdzić, czy zawiera nazwy linii; jeżeli
nie, doczytać z tabeli linii tej wersji). `mobile_code` → kod symbolu z
symboli gry.
Widok: dla `operational_review` źródłem jest zdjęcie źródłowe i
geometria, której checksuma równa się `boardChecksumSha256` dokumentu
(`resolve_operational_source_asset`, geometria jak w
`getOperationalImageReviewItem`); inna checksuma = 409
`BOARD_SEARCH_BOARD_REVISION_CONFLICT`, aby obraz w cache `immutable` nigdy
nie łączył się z innymi wielokątami. Dla `legacy_archive` obraz archiwalny z
`resolve_board_search_archive_asset` jest już obrazem jednej planszy — widok
go tylko zmniejsza. Wielokąty pól przeliczane do układu
0–1 widoku. Orientacja EXIF: ta sama konwencja co geometria (sprawdzić w
workerze przed implementacją). Cache pod
`artifact_root/cache/board-search-views/`, klucz SHA-256 z wersji
renderera, checksumy obrazu, checksumy geometrii i parametrów; wzorzec
`VirtualCellPreviewService` (`_atomic_write`, `_acquire_flight`, `_prune`).
Checksumą planszy w URL jest `boardChecksumSha256` dokumentu; niezgodna =
409 `BOARD_SEARCH_BOARD_REVISION_CONFLICT`. Nie ujawniać ścieżek w błędach.

## Expected files

- Istniejące: `services/api/src/game_predictor_api/api/board_search.py`, `application/board_search_approximate_win.py`, `storage/board_search_projection_repository.py`, `storage/board_search_approximate_win_repository.py`, `schemas/board_search_approximate_win.py`, `main.py`, `packages/admin-api-client/src/index.ts` + generowane pliki, `ai_docs/architecture/API_CONTRACT.md`.
- Nowe (proponowane): `domain/board_search_board_detail.py`, `application/board_search_board_view.py`, `services/api/tests/test_board_search_board_detail_api.py`, `services/api/tests/test_board_search_board_view.py`, test wrappera klienta.

## Test cases

- Kompletna plansza z dwiema liniami; częściowa z `confirmed_minimum`; przycięta z lewej; bez wypłaty; linia z jokerem.
- Brak dokumentu → 404; brak reguł → 409; symbol spoza reguł → 409.
- Geometria z inną checksumą niż dokument → 409 w szczegółach i widoku.
- Widok: niezgodna checksuma → 409; brak pliku → 404; ścieżka z `..` → odmowa; cache hit identyczne bajty; wielokąty w 0–1.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_board_detail_api.py services/api/tests/test_board_search_board_view.py services/api/tests/test_board_search_approximate_win_api.py services/api/tests/test_board_search_approximate_win_domain.py services/api/tests/test_board_search_api.py
npm run python:lint
npm run python:typecheck
npm run openapi:generate
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Geometria archiwum nieustalona.
- Integracja PostgreSQL (`GAME_PREDICTOR_RUN_POSTGRES_TESTS=1`) uruchamiana tylko na dedykowanej bazie testowej.

## Outcome

Wypełnia agent po pracy.
