# TASK-1211 — Job rozpoznawania symboli po korekcie siatek

## Status

`done`

## Goal

Lokalny ekran korekty uruchamia jawny job rozpoznawania symboli wyłącznie dla zapisanych, ręcznie poprawionych plansz z oczekującymi polami.

## Context

Operator 2026-11-15 zlecił przycisk zamiast rozpoznawania przy każdym zapisie geometrii. Zgoda po ostrzeżeniu o kosztach obejmuje ten pion implementacji i jego kontrole, bez restartów, uruchomienia joba na danych operatora ani merge.

## Dependencies / entry conditions

- Istnieje IMAGE_SYMBOL_REINFERENCE, bieżący renderer i ochrona ręcznych decyzji.
- Zastane zmiany TASK-1210 w głównym checkoutcie nie należą do taska.
- Uprawnienia sesji pozwalają czytać `.git`, nie zapisywać; gałąź/commit pozostają blokerem środowiskowym. Nie omijamy uprawnień.

## Recommended execution

gpt-6.1-sol, high (rekomendacja warunkowa; dostępność nazwy potwierdzona w środowisku). Jeden istniejący pion joba, bez delegowania. Rozbieżność ochrony decyzji lub zmiana schematu wymaga ponownej analizy.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md` — Korekta cięcia siatki
- `ai_docs/architecture/API_CONTRACT.md` — pending-symbol-reinference
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Rozszerzenie istniejącego preview/start o opcjonalny zakres corrected_geometry i import_job_id; stare wywołania bez zmian.
- Trwały snapshot par review_item_id/geometry_revision w payloadzie joba, model przypięty przy tworzeniu.
- Przycisk i licznik w lokalnej korekcie, odświeżane po zapisie; start tylko na kliknięcie, postęp przez istniejący job.

## Out of scope

- Zdalne uprawnienia sesji Reviewera, automatyczny start, zmiana geometrii przez job, zatwierdzanie przez człowieka, trening, dane operatora i restarty.

## Acceptance criteria

- [x] Zapis nie tworzy joba; przycisk tworzy jeden job dla aktualnego zakresu gry/importu.
- [x] Wybrano tylko bieżące plansze z zapisaną korektą aktualnej geometrii i dostępnym polem pending.
- [x] Job zapisuje zestaw i rewizje w trwałym payloadzie; test odtwarza utratę checkpointu i wznowienie. Późniejsze korekty i zastąpione zdjęcia są pomijane. Rzeczywisty restart joba na PostgreSQL nie był wykonywany.
- [x] Rozpoznanie korzysta z aktualnych renderów; ręczne decyzje chroni istniejący write-through.
- [x] UI pokazuje loading/empty/error i ID utworzonego joba; nie wysyła drugiego startu podczas żądania.
- [x] Backend/OpenAPI/klient/wrapper/test żądania są spójne; odpowiednie testy i dokumentacja zaktualizowane.

## Technical notes

Wykorzystać istniejący typ joba, bez migracji. Wspólny selektor SQL wiąże aktualny review, aktualną rewizję ImageBoardGeometryRevisionModel i pending cells; wspólna selekcja dla API oraz workera. Limit snapshotu 20 000 plansz: przekroczenie blokuje start i prosi o wybór importu, bez cichego obcięcia. Licznik opisuje poprawione plansze z polami pending, nie liczbę ręcznych zatwierdzeń ani gwarancję braku wcześniejszej inferencji. Ponowne jawne uruchomienie jest dozwolone; istniejąca unikalność model/crop chroni powtórny zapis. Ochrona rewizji sprawdzana przed inferencją i pod blokadą przy zapisie. Lokalny port Reviewera uzyskuje dostęp do startu tylko z istniejącymi nagłówkami lokalnego admina; sesje Bearer nie dostają nowej capability.

## Expected files

- Istniejące: application/image_reviews.py, application/jobs.py, api/image_reviews.py, schemas/jobs.py, storage/image_review_repository.py, security/local_admin.py.
- Istniejące: images/pending_symbol_reinference.py, packages/admin-api-client/src/index.ts i pliki generowane.
- Istniejące: board-geometry-correction-workspace.tsx, access/local-reviewer-workspace.tsx.
- Nowe proponowane: storage/corrected_grid_symbol_targets.py; corrected-grid-symbol-reinference.tsx; testy selektora, HTTP, workera i UI.

## Test cases

- Selekcja tylko korekt aktualnej rewizji; gra/import/current owner/pending/source available.
- Utrwalony payload i serializacja; pusta lista blokuje start; stary globalny job zachowany.
- Restart/utracony checkpoint i zmiana geometrii po utworzeniu joba.
- Kliknięcie nie zapisuje geometrii, podwójne kliknięcie daje jeden request, błąd startu widoczny.

## Verification

Komendy z katalogu repo, każda z limitem 120 s: `.venv/Scripts/python.exe -m pytest` dla zmienionych testów, `-m ruff check/format --check`, scoped mypy, `node .../tsx/dist/cli.mjs --test` dla klienta/UI, scoped eslint i `tsc --noEmit`. Eksport przez `scripts/export_admin_openapi.py`, generacja przez `packages/admin-api-client/scripts/generate-client.mjs`; `npm run docs:check`, mapa `scripts/generate_code_map.py`. Build tylko po scoped kontrolach. Wyniki poniżej.

## Risks / open questions

- Brak zapisu `.git` blokuje izolację gałęzi i commit; nie raportować taska jako zamkniętego bez nich.
- Ochrona pól pending z historyczną decyzją człowieka pozostaje w istniejącym koordynatorze; regresja jest blockerem.

## Outcome

Commit: v1.7.637 (hash dopisuje kolejny commit).

### Changed

- Lokalny Reviewer: jawny przycisk, licznik poprawionych plansz, zakres gry/importu, ID/postęp joba i odświeżanie; opcjonalna capability zachowuje istniejących konsumentów. Zdalny proxy/allowlista Bearer bez zmian.
- Rozszerzono istniejące preview/start i IMAGE_SYMBOL_REINFERENCE, bez migracji ani równoległego typu joba. Wspólny selektor wiąże bieżące ręczne rewizje. Model i cele są zapisane w payloadzie; walidacja pustego/uszkodzonego zakresu jest fail-closed.
- Worker chroni aktualność rewizji i źródła; utracona kwalifikacja/pending i zmienione/zastąpione plansze są pomijane, bez rozszerzenia scope. Odświeżanie predykcji nadal korzysta z istniejącego koordynatora decyzji człowieka.
- Powtórzenie identycznego startu odzyskuje istniejący job zamiast tworzyć duplikat; ukończony/nieudany job można obejrzeć w Adminie.

### Verification results

- UI: 40 istniejących testów `board-geometry-correction.test.mjs` i 2 nowe testy przycisku PASS w jednym przebiegu (42/42). Po dodaniu odzyskiwania utraconej odpowiedzi: komplet 3 nowych testów PASS. Regresje starych konsumentów i brak automatycznego startu potwierdzone.
- Klient: `corrected-grid-symbol-request.test.mjs` PASS; sprawdza query preview/start, metodę, nagłówek targetu i stare wywołanie bez query.
- Backend/worker: 18 PASS przy wyłączeniu 4 testów HTTP TestClient; po dodaniu testu wycofanego źródła komplet 12/12 testów nowego workera PASS (łącznie 19 nowych przypadków zaliczonych). Sprawdzone selektor SQL, payload/serializacja, endpointy bez sieci, pusty i błędny zakres, duplikat startu, owner-intent/Bearer, restart kontekstu po utracie checkpointu oraz zmiana geometrii/źródła.
- Dodatkowe regresje: `test_image_symbol_review_virtual_source.py` + `test_board_search_projection_repository.py`: 42/42 PASS, w tym ochrona ludzkich symboli przed predykcjami.
- Mypy zmienionych 8 plików źródłowych: PASS. TypeScript Reviewer i admin-api-client: PASS. Scoped ESLint i Ruff: PASS; formatowanie zmienionych plików wykonane.
- Eksport OpenAPI, generacja i `check-generated-client.mjs`: PASS. Mapa kodu zregenerowana, `generate_code_map.py --check`: PASS. `npm run docs:check`: PASS (startup 44 982/45 000 B).
- Produkcyjny build Reviewera: PASS (kompilacja, TypeScript, strony statyczne). Usługi nie były uruchamiane/restartowane przez agenta.
- Próba szerszego zestawu Python przerwana jawnym timeoutem 120 s. Diagnostyka pojedynczego HTTP: zawieszenie Windows asyncio `_fallback_socketpair` podczas tworzenia TestClient; timeout 35 s. Endpointy i middleware dodatkowo sprawdzono bez użycia sieci. Odczyt procesów CIM/Process niedostępny w sandboxie; nie uruchomiono serwerów ani watcherów.
- Zastana usterka `test_restart_after_lost_checkpoint_response_skips_committed_prefix`: TypeError mocka `session.scalar`, lambda nie przyjmuje dodatkowych argumentów kontroli źródła. Odtworzono również po załadowaniu oryginalnego modułu z HEAD (96e70230); nie zmieniano testu ani zabezpieczeń dla zielonego wyniku.
- Zamknięcie (Claude Code, 2026-11-15, poza sandboxem Codexa): PASS 23/23 w `test_corrected_grid_symbol_reinference.py`, `test_corrected_symbol_job_security.py` i `test_corrected_grid_symbol_reinference_handler.py`, w tym 4 testy HTTP TestClient. PASS 43/43 testów interakcji Reviewera (nowy przycisk + `board-geometry-correction`), test żądania klienta, `tsc --noEmit` Reviewera i `npm run openapi:check`.
- `test_pending_symbol_reinference.py`: 5 FAIL / 9 PASS, identycznie na czystym HEAD 96e70230 w osobnym worktree (`SourceReplacementError` i mock `session.scalar`), więc to zastana usterka, nie regresja tego taska; poza zakresem.
- Build Reviewera (`BUILD_ID` 21:08:45) poprzedza ostatnią edycję `corrected-grid-symbol-reinference.tsx` (21:08:53); ostatnią wersję potwierdzają typecheck i testy interakcji. Działającego `.next` nie przebudowywano.

### Not completed

- Merge i push wymagają osobnej zgody. Blokada zapisu `.git` w sandboxie Codexa: commit i zamknięcie wykonał Claude Code na gałęzi roboczej `codex/super-series-grid-symbols`.
- Rzeczywisty przebieg PostgreSQL, restart procesu workera podczas tego joba i odbiór przez przeglądarkę na danych operatora pozostają niewykonane.
- Zastane zmiany TASK-1210 zachowane. Nie uruchomiono joba na danych operatora i nie restartowano usług.

### Documentation updates

- ADMIN_APP.md: zachowanie przycisku i znaczenie licznika, który nie oznacza wyłącznie nowych korekt.
- API_CONTRACT.md: query, snapshot, błędy, wznowienie i lokalne uprawnienia; schemat joba + wygenerowany klient.
- CURRENT_STATE.md: wskaźnik i blocker; mapa kodu zaktualizowana.

### Recommended next task

Po umożliwieniu zapisu git: odizolować tylko hunki TASK-1211 (bez TASK-1210), wykonać 4 testy HTTP i odbiór operatora, następnie zamknąć task wymaganym skryptem i osobnym commitem z następną wersją ustaloną z bieżącego git log. Merge tylko po zgodzie.

Do odbioru operator zatrzymuje odpowiednie procesy we własnych terminalach i uruchamia ponownie z katalogu repo: `npm run reviewer:start`, `npm run worker:poll`, a jeśli API nie przeładowało kodu — `npm run api:dev`. Każda komenda w osobnym terminalu; nie uruchamiać drugiej kopii istniejącej usługi. Build Reviewera jest gotowy. Najpierw zweryfikować licznik/zakres i wybrać jawnie job przyciskiem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1211 | gpt-6.1-sol | high | Rozszerzenie istniejącego joba i pełnego kontraktu; rekomendacja warunkowa dla nowej sesji. | Nie; testy istniejącej ochrony decyzji i nowego zakresu. |
