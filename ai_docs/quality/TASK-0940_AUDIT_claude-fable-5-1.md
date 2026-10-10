# Audyt TASK-0940 — Atomowa maszyna, preview i trwałe usuwanie zakresu panelu

Werdykt: REVISE
Audytor: claude-fable-5-1, high
Wykonawca: gpt-6.1-sol, high
Zakres: 32f78371d7deebae820c807a62178e4f2596925e...32f78371d7deebae820c807a62178e4f2596925e oraz zmiany niezacommitowane, data 2026-10-09
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano pełny diff niezacommitowany w worktree `codex/admin-compact-panel`: domenę i repozytoria management (atomowa maszyna, preview, purge), migrację `0152_management_compact_panel`, trigger immutable i funkcję SECURITY DEFINER, klasyfikator receiptów, metryki pinów, kontrakt OpenAPI z wygenerowanym klientem, wrappery, publiczny adapter i proxy oraz nowe testy. Implementacja jest spójna z „Kontraktem bezpiecznych mutacji”: kolejność blokad (sesja → UUID operacji → preview → punkt → maszyny → gry → digesty) jest zachowana we wszystkich writerach, klucz advisory purge jest identyczny z kluczem `_version`, token jest przechowywany wyłącznie jako SHA-256, a retry pure delete wraca z własnego receiptu przed sprawdzeniem istnienia wiersza. Główne ryzyko to brak testów żądań HTTP dla nowych tras na prefiksie Admin oraz dla tras maszyny i update-preview (nowy moduł `api/management_mutations.py` ma pokrycie HTTP tylko w teście PostgreSQL pomijanym domyślnie). Pozostałe uwagi są P2: nadmiarowa redakcja receiptów przy odpięciu gry, przejściowa regresja odpinania w istniejącym UI do czasu TASK-0941, luka w instrukcji operatorskiej (dwuetapowy upgrade do 0151 przed preview) i niezapisana w planie zmiana semantyki pustej listy gier.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `services/api/src/game_predictor_api/api/management_mutations.py:19` — nowy moduł routera (pięć tras na dwóch prefiksach) nie ma testu żądań HTTP na prefiksie Admin ani dla tras `machines/{id}/delete-preview`, `machines/{id}/delete` i `machines/{id}/update-preview` na żadnym prefiksie. Jedyne pokrycie HTTP to `services/api/tests/integration/test_management_sessions_postgres.py:239-294` (publiczny point delete-preview/delete, wymaga PostgreSQL, domyślnie skip). Istniejący test kontraktu HTTP `services/api/tests/test_management.py:219` nie został rozszerzony. Narusza to regułę CLAUDE.md/AGENTS.md („zmiana API musi dostarczyć backend, OpenAPI, klienta, wrapper i request test razem”) oraz wymóg taska „Nowe moduły muszą dostać własne testy razem z kodem”. Skutek: mapowanie 403 security guard, 404 (maszyna spoza punktu), 409 `MANAGEMENT_PREVIEW_REQUIRED`, 422 (`confirmed=false`, unia `ManagementUpdatePreviewCommand`) i 503 `MANAGEMENT_PURGE_REQUIRES_POSTGRESQL` dla nowych tras nie jest sprawdzane na poziomie HTTP w domyślnym przebiegu. Poprawka: dodać do `test_management.py` przypadki TestClient na SQLite dla `/api/v1/admin/management/points/{id}/delete-preview` (200 z 43-znakowym tokenem i `expiresAt`), `/machines/{id}/update-preview` z `command` typu machine i assignment (200 oraz 422 dla braku `gameIds`), `/points/{id}/machines/{id}/delete-preview` dla maszyny z innego punktu (404), `PUT assignments` z `gameIds: []` bez tokenu (409 `MANAGEMENT_PREVIEW_REQUIRED`) oraz `POST .../delete` z `confirmed: false` (422); analogiczny minimalny przypadek dla publicznego routera z fałszywym guardem jak w `test_management_sessions.py`.

### P2

- [P2-1] `services/api/alembic/versions/0152_management_compact_panel.py:97-101` — w trybie odpięcia gry (`p_games IS NOT NULL`) warunek `game_id IS NULL OR game_id=ANY(p_games)` redaguje wszystkie receipty maszyny bez `game_id`, czyli także wcześniejsze `machine.write`/`assignments.write` maszyny, która nadal istnieje. Dokładny retry wcześniejszej zmiany nazwy po utracie odpowiedzi zwraca wtedy 409 `MANAGEMENT_TARGET_DELETED` z komunikatem „The original target is no longer available.” (`management_repository.py:168-175`), choć cel istnieje. Zachowanie jest fail-closed i nie odtwarza encji, więc kryteria są spełnione, ale kod błędu wprowadza w błąd klienta. Poprawka: ograniczyć redakcję w trybie gry do receiptów z `game_id=ANY(p_games)` oraz `assignments.write`/`machine.write` z `gameIds` w body, albo zapisać ryzyko i nadać osobny komunikat dla redakcji zakresu, nie usunięcia celu.
- [P2-2] `packages/board-search-ui/src/management/management-workspace.tsx:351-360` — istniejące współdzielone UI (Admin i reviewer) nadal wysyła odpięcie gry przez `updateManagementAssignments` bez `previewToken`, więc po tej zmianie odpięcie z panelu kończy się 409 `MANAGEMENT_PREVIEW_REQUIRED`. Dodatkowo `retained` pomija legacy wiersze `attached=false`, więc na maszynie z takimi wierszami każda zmiana przypisań (także dopięcie) wymusza preview. To przejściowy stan do TASK-0941 i wynika z zaakceptowanej kolejności planu, ale nie jest nazwany w Outcome ani w CURRENT_STATE. Poprawka: zapisać w Outcome taska i CURRENT_STATE, że do zamknięcia TASK-0941 odpinanie gier z istniejącego UI zwraca 409, oraz przekazać TASK-0941 wymóg wywołania `update-preview` przed zapisem (również dla legacy `attached=false`).
- [P2-3] `scripts/preview_management_receipt_migration.py:30-31` wymaga dokładnie jednej głowy `0151_super_game_roles`, a `ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md:17` każe uruchomić klasyfikator „na niezmodyfikowanej bazie 0151”, podczas gdy ten sam dokument (`:59-64`) stwierdza, że ostatni odczyt produkcji dał `0149_management_stake_saves`. Zwykłe `alembic upgrade head` z 0149 wykona 0150, 0151 i 0152 w jednym kroku i ominie bramkę preview; uruchomienie skryptu przed upgrade kończy się `RuntimeError`. Skutek jest fail-closed, ale instrukcja operatorska jest niekompletna. Poprawka: dodać jawny krok `alembic upgrade 0151_super_game_roles`, potem preview, potem osobna zgoda i `upgrade head`.
- [P2-4] `services/api/src/game_predictor_api/storage/management_repository.py:402,428` — preview jest wymagane tylko wtedy, gdy `removed` jest niepuste, więc pusta lista `gameIds` na nowej lub pustej maszynie nie wymaga preview. Plan (`ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md:121`) mówi „Pusta lista jest jawnym odpięciem i wymaga preview”. Założenie jest rozsądne i zapisane w requirements/architecture/task, ale nie w planie ani w `DECISION_LOG.md` (D-536), które są wyżej w hierarchii źródeł prawdy. Poprawka: dopisać jednozdaniowe doprecyzowanie do D-536 lub do sekcji kontraktu w planie.
- [P2-5] `packages/board-search-ui/test/management-pin-metrics.test.mjs:21-23` — test TS pomija przypadki `zero` i `unavailable`, więc zgodność dla spinu 0 opiera się na osobnym warunku wykresu `controlled && point.spinNumber === 0` w `packages/board-search-ui/src/board-search-approximate-win.tsx:965-975`, nie na helperze (`approximateWinStakeToPoint` dla spinu 0 zwróciłoby `spinCost`). Kryterium 7 jest spełnione funkcjonalnie, ale tylko połowicznie dowiedzione po stronie TS. Poprawka: dodać w teście TS asercję ścieżki kontrolowanego zera (0/0) albo wprost zapisać w fixture, że zero/unavailable są semantyką wywołującego.
- [P2-6] `packages/admin-api-client/src/generated/client.gen.ts`, `generated/client/*.gen.ts`, `generated/core/*.gen.ts` — pliki widoczne jako zmodyfikowane w `git status`, ale `git diff --stat` nie pokazuje żadnych zmian treści (wyłącznie normalizacja LF/CRLF). Zgodnie z regułą „stage only the task's hunks” nie należy ich dodawać do commita taska. Poprawka: przed commitem wykonać `git checkout --` na tych plikach lub `git add --renormalize`, a następnie `git diff --cached --check`.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Atomowy create/update name+games, omitted games bez zmiany, inactive game bez nowego przypisania; rollback przy błędzie | spełnione | `storage/management_repository.py:285-325,380-441` (jedna transakcja, jeden `finish_operation`, `game_ids is None` pomija `_apply_assignments`, `MANAGEMENT_GAME_NOT_ACTIVE` tylko dla `newly_attached`); testy `tests/test_management_mutations.py:38-81`, `integration/test_management_mutations_postgres.py:228-249` |
| Detach bez tokenu 409 MANAGEMENT_PREVIEW_REQUIRED; token innego aktora/body/rewizji, wygasły lub stale nie kasuje | spełnione | `storage/management_mutation_repository.py:55-76,293-324` (actor, action, scope, body_sha256, fingerprint, expiry); `test_management.py:153-162`, `test_management_mutations.py:84-130,258-301` |
| Purge kasuje tylko zakres w opisanej kolejności; współdzielony wynik przeżywa; globalne korekty i session audit pozostają | spełnione (statycznie) | `alembic/versions/0152_management_compact_panel.py:66-121` (journal → sloty → konteksty → wersje bez referencji → assignments → maszyny → punkt; brak DML na `management_session_audit` i danych gry); `test_management_mutations_postgres.py:226,333-335` |
| App z GUC i owner bez flagi otrzymują odmowę triggera; funkcja ma własność i granty | spełnione (statycznie) | `0152_management_compact_panel.py:36-62` (`current_user=owner_name` AND tryb), `storage/database_roles.py:378-414` (owner, prosecdef, search_path, PUBLIC/app execute); `test_management_mutations_postgres.py:150-167,172-194` |
| Exact retry delete zwraca własny receipt także po usunięciu rodzica; stare create/update/save/clear nie odtwarzają encji | spełnione | `management_repository.py:162-176` (receipt przed `lock_point`), `management_mutation_repository.py:352-359`; wykluczenie `point.delete`/`machine.delete` z redakcji `0152:97-101`; `test_management_mutations_postgres.py:271-294`, `test_management_stakes_postgres.py:548-584` |
| Nieznane stare receipty policzone w preview i fail-closed; brak tokenów w response history/logs | spełnione | `storage/management_receipt_backfill.py` (kategoria `legacy_redacted`), `scripts/preview_management_receipt_migration.py:21-45` (READ ONLY, bez zrzutu response); token tylko jako SHA-256 w `management_mutation_repository.py:205`; journal zapisuje wyłącznie before/after response (`management_repository.py:203-213`); `test_management_receipt_backfill_postgres.py` |
| Złote przykłady pinów zgodne Python/TS, zero i unavailable; GET fallback nie zapisuje i ma limit 6×6 | spełnione z zastrzeżeniem P2-5 | `domain/management_pin_metrics.py:39-58` vs `board-search-approximate-win-state.ts:523-556` (ten sam algorytm), zero przez `board-search-approximate-win.tsx:965-975`; fallback `management_stake_repository.py:227-244` bez przypisania do ORM; `test_management_stakes_postgres.py:247-296` |
| Publiczny revoke/expiry/replacement session podczas operacji blokuje commit; generowane typy i klient zgodne | spełnione | `main.py:2027` (`guard.before_commit()` po yield dla wszystkich tras publicznych, w tym nowych przez `management_public_structure.py:101`); `test_management_sessions_postgres.py:259-278`; OpenAPI/klient/wrappery `admin-api-client/src/index.ts:1195-1234`, `src/management.ts:104-147`, `board-search-ui/management/management-client.ts:45-49`; testy `admin-api-client/test/management-mutations-request.test.mjs`, `reviewer/test/management-proxy.test.mjs:15-56` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy.

Otwarte: P1-1, P2-1, P2-2, P2-3, P2-4, P2-5, P2-6.

## Proponowane testy

- `services/api/tests/test_management.py`: rozszerzyć `test_http_contract_and_commit_precedes_response` o nowe trasy Admin (delete-preview 200, update-preview 200 i 422, maszyna spoza punktu 404, detach bez tokenu 409, `confirmed=false` 422, `delete` na SQLite 503 `MANAGEMENT_PURGE_REQUIRES_POSTGRESQL`); komenda: `.venv\Scripts\python.exe -m pytest services/api/tests/test_management.py -q`.
- `services/api/tests/test_management_sessions.py`: przypadek TestClient dla `POST /api/v1/management-public/machines/{id}/update-preview` z fałszywym guardem, sprawdzający 404 dla nieistniejącej maszyny i brak `previewToken` w logu/journalu.
- `services/api/tests/integration/test_management_mutations_postgres.py`: po odpięciu gry zweryfikować, że retry wcześniejszego `machine.write` (rename) zwraca oczekiwany wynik (receipt lub jawny kod), aby utrwalić decyzję z P2-1; komenda: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .venv\Scripts\python.exe -m pytest services/api/tests/integration/test_management_mutations_postgres.py -q` wyłącznie na disposable DB.
- `packages/board-search-ui/test/management-pin-metrics.test.mjs`: dodać asercję kontrolowanego zera (0/0) i braku wartości dla pinu niedostępnego, zgodnie z P2-5; komenda: `npm run test --workspace @game-predictor/board-search-ui`.

## Zakres przeglądu i ograniczenia

Przeczytano w całości: `management_repository.py`, `management_mutation_repository.py`, `management_pin_metrics.py`, `management_mutations.py`, `management_receipt_backfill.py`, migrację `0152`, zmiany w `database_roles.py`, `management_stake_repository.py` (fragmenty `_begin`/`_finish`/`_response`/`_version`), `management_public.py`, zależności publiczne w `main.py:1925-2061`, proxy `management-proxy.ts`, helpery TS `board-search-approximate-win-state.ts:523-556` i wykres `board-search-approximate-win.tsx:962-975`, `management-workspace.tsx:346-360`, wszystkie nowe i zmienione testy oraz dokumenty z diffu (requirements, architecture, operations, CURRENT_STATE, task). Sprawdzono git log/status i `git diff --stat` dla generowanych plików klienta. Nie uruchamiano żadnych testów, lintów, migracji ani serwerów; wyniki PostgreSQL (purge, trigger, provisioning, backfill, race dedup/purge) przyjęto z Outcome wykonawcy i zweryfikowano wyłącznie statycznie. Nie weryfikowano zachowania 3 równoległych instancji API operatora wobec nowego `EXPECTED_ALEMBIC_HEAD`, ponieważ lifecycle i baza operatora są poza zakresem taska.

## Rozliczenie wykonawcy po jednej rundzie poprawek

Autor tej sekcji: Codex. Oryginalny raport Claude i werdykt REVISE pozostają
powyżej bez zmiany. Ta sekcja nie jest ponownym audytem ani werdyktem PASS Claude.
Szczegółowe rozliczenie zawiera Outcome TASK-0940.

- Zamknięte: P1-1 (testy HTTP na obu prefiksach), P2-2 (jawny stan przejściowy
  i handoff do0941), P2-3 (dwuetapowa migracja z preview), P2-4 (D-536 i plan),
  P2-5 (jawna semantyka wywołującego w fixtures), P2-6 (13 plików bez diffu treści).
- P2-1: zaakceptowane ryzyko. Dawny receipt rename zawiera snapshot przypisań;
  jego odtworzenie po detach mogłoby przekazać klientowi usunięty zakres.
  Zachowano redakcję fail-closed. MANAGEMENT_TARGET_DELETED nie dowodzi usunięcia
  całej maszyny; po unieważnieniu receiptu trzeba pobrać bieżący snapshot.
- Otwarte P0/P1 po poprawkach: brak. Nie zmieniono wykonywalnego kodu backendu,
  klienta ani migracji. Poprawka P1 dodaje testy, zatem nie wymaga automatycznego
  drugiego audytu zgodnie z regułą jednej rundy AGENTS.md.
- Dowody: test_management.py zawiera trzy parametryzowane scenariusze na Admin
  i publicznym prefiksie, obejmujące wszystkie pięć nowych tras. Testuje 200,
  403,404,409,422,503, obie gałęzie command, commit przed response, aktora,
  rollback i brak ujawniania tokenu. Publiczny test podmienia uwierzytelnienie
  capability, zachowując produkcyjny proxy guard oraz wiring service/actor.
  Rzeczywiste expiry/revoke/session replacement chronią wcześniejsze testy PG.
- Wyniki końcowego przebiegu i zakres commita zapisano w Outcome taska.

Oświadczenie audytora z rundy1 nadal obowiązuje: przegląd statyczny, bez zmian
w plikach. Poprawki i ich testy wykonał Codex, nie audytor.
