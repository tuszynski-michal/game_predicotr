---
title: Inkrementalne i wznawialne tworzenie geometrii siatek
status: done
last_updated: 2026-09-16
---

# TASK-0559 — Inkrementalne i wznawialne tworzenie geometrii siatek

## Status

`done`

## Goal

Skrócić kolejne preflighty geometrii przez bezpieczne ponowne użycie wyników v2/v3, trwałe checkpointy i deterministyczne równoległe dodatkowe dopasowanie.

## Context

Job geometrii przelicza wszystkie źródła po każdej korekcie, przechowuje bieżące wpisy głównie w pamięci i wykonuje retry kotwic sekwencyjnie. Dla stagingu 45163–70371 bezpieczna migracja v2→v3 pozwala zachować około 1686 wyników i przeliczyć około 1115.

## Dependencies / entry conditions

- Bazowy commit: `69e4cf0d6d9443155bffac04a1bb17a3595e9aba`.
- Implementacja powstaje w osobnym worktree i nie uruchamia API ani workera na danych działającego joba.
- Job `07691c10-2c6c-43f4-a1a8-f77f9720c81d` kończy się na dotychczasowym kodzie przed merge i restartem usług.
- Zaakceptowano zgodność `v2→v3` oraz `v3→v3`.

## Recommended execution

`gpt-6-astra` z reasoning `high`. Dodatkowy review: `gpt-6-astra/high` przed merge, ze szczególną kontrolą zgodności v2→v3, atomowości checkpointów i izolacji worktree.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_DATA_IMPORT.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- API przypina najnowszy zgodny ukończony manifest do nowego joba.
- Worker ponownie używa bezpiecznych wpisów v2/v3 i przelicza tylko różnicę.
- Worker utrwala checksummowane shardy checkpointu i wznawia bez powtarzania zapisanej pracy.
- Retry automatycznych kotwic działa równolegle w deterministycznej kolejności.
- API, generowany klient i panel pokazują liczniki reuse/recompute.
- Dokumentacja opisuje nowy kontrakt i zachowanie po restarcie.

## Out of scope

- Zmiana progów jakości geometrii lub algorytmu oceny obramowania.
- Nowe tabele bazy albo migracja Alembic.
- Automatyczne uruchomienie nowego rzeczywistego preflightu.
- Czyszczenie checkpointów zakończonych jobów.

## Acceptance criteria

- [x] Nowy job przypina kompatybilny manifest, preferując dokładną politykę przed v2↔v3.
- [x] Zmiana source manifestu wyłącza reuse.
- [x] v2→v3 zachowuje tylko bezpieczne klasy i przelicza review oraz 1–3 słabe sloty.
- [x] v3→v3 przelicza review, zmienione override'y i zależności zmienionych kotwic.
- [x] Checkpoint przetrwa restart oraz utratę odpowiedzi między zapisem pliku i bazy.
- [x] Równoległy retry jest byte-identyczny i zachowuje naturalną kolejność.
- [x] Postęp raportuje użyte ponownie i przeliczone źródła.
- [x] Aktualny job oraz dane w głównym worktree nie są modyfikowane.
- [x] Testy skoncentrowane, OpenAPI, klient, lint, TypeScript i build zmienionych części przechodzą; pełny mypy ma opisany istniejący blocker bazowy.

## Technical notes

API zapisuje opcjonalny deskryptor `basePageGeometryManifest` w input payload i kluczu idempotencji. Deskryptor przypina job, checksumę manifestu, checksumę source manifestu i tryb `exact_policy`, `lateral_v2_to_v3` albo `lateral_v3_to_v2`. Worker weryfikuje manifest fail-closed.

Dla v2→v3 automatyczne `registered` z 0 lub co najmniej 4 slotami poniżej progu 0,65 można zachować; 1–3 słabe sloty oraz wszystkie `review_required` trzeba przeliczyć. Ręczny wpis można zachować wyłącznie przy zgodnej decyzji. Zmieniona lub usunięta kotwica unieważnia wpisy wskazujące jej checksumę.

Checkpoint składa się z atomowo zapisanych, checksummowanych shardów oraz indeksu z fingerprintem inputu. Kolejność publikacji: shard → indeks → checkpoint DB. Worker rekoncyliuje stan plików z bazą i wznawia od pierwszego brakującego wpisu.

Retry używa istniejącej konfiguracji workerów i batchy po 25. Cache kotwic powstaje przed uruchomieniem wątków. Wątki nie modyfikują mapy wpisów; główny wątek publikuje wyniki w kolejności źródeł.

## Expected files

- `services/api/src/game_predictor_api/application/jobs.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/worker/src/game_predictor_worker/images/page_geometry_preflight.py`
- `services/worker/src/game_predictor_worker/images/page_geometry_registration.py`
- testy API i workera dla preflightu
- wygenerowany OpenAPI i klient TypeScript
- panel jobów w `apps/admin`
- dokumenty wskazane w Relevant docs

## Test cases

- Exact v3 z nowym, zmienionym i usuniętym override'em.
- Zmiana kotwicy unieważnia wpisy zależne.
- v2→v3 dla 0, 1, 2, 3 i 4 słabych slotów oraz review.
- Brakujący lub zmieniony przypięty manifest kończy się stabilnym błędem.
- Restart po shardzie, po indeksie i przed checkpointem DB.
- Równoległy wynik i manifest są identyczne z przebiegiem referencyjnym.
- API wybiera exact przed przejściem v2↔v3; brak kandydata uruchamia pełny skan.
- Po rollbacku v3→v2 zachowuje bezpieczne `registered`, a review przelicza.
- Anulowany nieprzypięty job nie blokuje nowego joba z przypiętą bazą.
- UI pokazuje liczniki i zachowuje zgodność ze starszym jobem bez nowych pól.

## Verification

```powershell
python -m pytest services/worker/tests/test_page_geometry_incremental.py services/worker/tests/test_page_geometry_preflight.py -q
python -m pytest services/api/tests/test_jobs_domain.py services/api/tests/test_jobs_api.py -q
python scripts/export_admin_openapi.py --check
npm run check:generated --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin-api-client
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Warunkiem zakończenia są zielone testy skoncentrowane, kontrola OpenAPI, typecheck, lint i build oraz kontrola odczytowa klasyfikacji istniejącego manifestu.

## Risks / open questions

- Historyczne manifesty mogą nie zawierać pełnej proweniencji kotwicy; taki wpis musi zostać przeliczony.
- Dodatkowe pola manifestu pozostają opcjonalne i wstecznie zgodne.
- Rzeczywisty rollout nastąpi dopiero po terminalnym stanie obecnego joba.

## Outcome

Zaimplementowano pełny pion inkrementalnego i wznawialnego preflightu w
odizolowanym worktree. Nie uruchomiono API, workera ani nowego preflightu na
bieżących danych.

### Changed

- API wybiera i przypina najnowszy zgodny manifest z pierwszeństwem exact.
- Worker planuje reuse v2→v2, v3→v3, v2→v3 i po rollbacku v3→v2,
  unieważnia zmienione override'y oraz
  zależności kotwic i kończy fail-closed dla uszkodzonej przypiętej bazy.
- Trwałe shardy i indeks pozwalają wznowić pierwszy przebieg oraz dodatkowe
  dopasowanie bez powtarzania zapisanych batchy.
- Dodatkowe dopasowanie działa równolegle z istniejącym budżetem CPU i zachowuje
  deterministyczny manifest.
- OpenAPI, generowany klient i panel udostępniają liczniki reuse/recompute.

### Verification results

- Worker: 20 testów, wszystkie zaliczone.
- API jobów: 52 testy, wszystkie zaliczone.
- Admin: 493 testy, typecheck klienta i aplikacji, lint oraz build zaliczone.
- OpenAPI i wygenerowany klient: brak driftu.
- Ruff zmienionych plików: zaliczony po uporządkowaniu importów.
- Odczytowy audyt manifestu
  `abf1587804f16ffd375020a3e26dfc43851cbb842ebde9c72ab5db41f335bc69`:
  `1686` reuse, `1115` recompute, razem `2801`.
- Pełny mypy przekroczył limit 60 sekund bez wyniku. Krótszy przebieg wykazał
  wyłącznie istniejące błędy bazowe w niezmienionych liniach, m.in. float
  `Literal` w `schemas/jobs.py`; nowe moduły nie dodały osobnej klasy błędu.

### Not completed

- Nie wykonano rollout'u, merge ani restartu usług przed terminalnym stanem
  działającego joba. Nie uruchomiono nowego rzeczywistego preflightu.
- Nie dodano czyszczenia zakończonych checkpointów; pozostają audytem zgodnie z
  zakresem zadania.

### Documentation updates

- Zaktualizowano wymagania, kontrakt API, `CURRENT_STATE.md` i `DECISION_LOG.md`.

### Recommended next task

- Po terminalnym stanie dotychczasowego joba: zaktualizować branch względem
  `version-0.10`, ponowić kontrole, połączyć i wykonać jawny pierwszy preflight.
  Cleanup checkpointów pozostaje osobnym zadaniem.

### Integration after rollback (2026-09-16)

Branch zaktualizowano względem `version-0.10` po wycofaniu gałęzi słabych
obramowań. Nowe joby pozostają na v2, a ukończony manifest v3 może być bazą
przejścia v3→v2 tylko dla bezpiecznych wyników. Dodano test dokładnej bazy v2,
odwrotnego przejścia, proweniencji kotwicy i zastąpienia anulowanego runu z
nowo dostępną bazą. Testy po integracji: worker `20 passed`, API `53 passed`
przed dodatkowymi przypadkami; OpenAPI, generowany klient, panel `493 passed`,
lint, typecheck i build przeszły. Po ostatnim rozszerzeniu testy skoncentrowane
zostaną powtórzone przed wdrożeniem.

Niezależny review ujawnił zależności przez automatycznie promowane kotwice,
kotwice ręczne spoza stagingu oraz restart po pustym przebiegu retry. Odciski
historycznych decyzji są teraz przypięte w input joba, a każde źródło
przeliczane unieważnia przechodnio zależne wyniki. Test po restarcie potwierdza,
że zakończony zerowym wynikiem przebieg nie startuje ponownie. Po tej poprawce
worker `26 passed`, API `55 passed`, panel `493 passed`; OpenAPI, klient,
kontrola typów, lint i build przeszły. Nie uruchomiono pełnego benchmarku.
