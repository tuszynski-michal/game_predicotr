---
title: Atomowa maszyna, preview i trwałe usuwanie zakresu panelu
status: done
last_updated: 2026-10-09
---

# TASK-0940 — Atomowa maszyna, preview i trwałe usuwanie zakresu panelu

## Status

`done`

## Goal

Dostarczyć jeden zgodny pion API do atomowej edycji maszyny, bezpiecznego hard delete oraz szybkich danych pinów.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

Plan zaakceptowany, D-538 zapisane, worktree od 3bc6c64b. TASK-0933–0936 nie blokują. Przed migracją potwierdzić wolny pełny revision ID i head0151. Żadna migracja na danych operatora nie jest dozwolona.

## Recommended execution

gpt-6.1-sol / high. Ryzyka: concurrent dedup/purge, immutable backfill i uprawnienia SECURITY DEFINER. Raport audytu jest warunkiem commita. Zgoda na API i kontrakt już udzielona w zaakceptowanym planie; informujemy operatora o rozpoczęciu tego pionu. Nie wolno użyć bazy operatora jako fixture. Przy konflikcie domeny/architektury zatrzymać zależny fragment.
Wymagany niezależny ręczny review claude-fable-5-1 / high przed commitem. Konfiguracja musi
odpowiadać końcowej tabeli planu; niedostępność albo zmiana ryzyka wymagają jawnej
aktualizacji, bez ukrytej zamiany modelu.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/ADMIN_COMPACT_PANEL_EXECUTION_PLAN.md — sekcje TASK-0940 i reguły wspólne.
- ai_docs/requirements/MANAGEMENT_PANEL.md
- ai_docs/architecture/MANAGEMENT_PANEL.md
- ai_docs/process/DECISION_LOG.md — D-538 i D-533.
- ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md
- ai_docs/quality/AUDIT_REPORT_TEMPLATE.md

## Scope

- Opcjonalne gameIds/previewToken w komendzie maszyny; ten sam mechanizm dla kompatybilnego assignments; jedna transakcja i jeden wpis journal.
- Preview i POST delete punktu/maszyny oraz update-preview po obu prefiksach API; wygasanie, counts, actor/body/fingerprint binding, cleanup≤100 własnych preview.
- Kontrolowany purge PostgreSQL, redakcja starych receiptów i niezmienione retry pure delete, migracja scope/backfill z read-only preview operatora.
- ManagementPinnedPoint: requiredStakeCredits i machineCashCredits; wspólna semantyka helperów, bounded read-only fallback.
- OpenAPI/generowany klient/wrappery/public adapter/proxy i request tests; manifest v3, schema readiness, provisioning --check.

## Out of scope

- Push, merge, deployment, dane/baza operatora i lifecycle API/Admin.
- Nowa kopia wyszukiwarki/kalkulatora, konta/chmura/Redis/Celery i benchmarki.
- Usuwanie katalogu gier, symboli, plansz, globalnych korekt i innych dzienników.
- Taski innych torów oraz niezwiązane wcześniejsze błędy.

## Acceptance criteria

- [x] Atomowy create/update name+games, omitted games bez zmiany, inactive game bez nowego przypisania; rollback przy błędzie.
- [x] Detach bez tokenu zwraca 409 MANAGEMENT_PREVIEW_REQUIRED. Token z innego aktora/body/rewizji, wygasły lub stale nie kasuje niczego.
- [x] Purge kasuje tylko zakres panelu w opisanej kolejności; współdzielony wynik przeżywa, globalne korekty i session audit pozostają.
- [x] App ustawiająca GUC i kasująca bezpośrednio oraz owner bez flagi otrzymują odmowę triggera; funkcja ma prawidłową własność i granty.
- [x] Exact retry delete zwraca własny receipt także po usunięciu rodzica; stare create/update/save/clear nie odtwarzają usuniętej encji.
- [x] Nieznane stare receipty policzone w preview i fail-closed; brak tokenów/sekretów w response history/logs.
- [x] Złote przykłady pinów zgodne Python/TS, zero i unavailable; GET fallback nie zapisuje i ma limit6×6.
- [x] Publiczny revoke/expiry/replacement session podczas operacji blokuje commit; generowane typy i klient są zgodne.

## Technical notes

Obowiązuje pełna sekcja „Kontrakt bezpiecznych mutacji” planu. Implementacja nie może zastąpić sprawdzenia owner samym GUC ani osłabić immutable session audit. Locks: session → operation UUID → preview → point → sorted machines → sorted games → sorted result digests. Zredaguj stare receipty przed utworzeniem receipt bieżącego destrukcyjnego update. Nie twórz journalu delete z usuniętym FK. Reset/clear pojedynczego slotu nadal zachowuje historię; dopiero structural purge ją usuwa. Wszystkie writerzy zachowują wspólne blokady. Migracja/backfill wyłącznie Alembic, bez destructive downgrade; osobna read-only instrukcja/script preview przed bazą operatora.

## Expected files

- Istniejące: services/api/src/game_predictor_api/domain/management.py — komendy i records.
- Istniejące: application/management.py, storage/management_repository.py, storage/management_models.py — service/receipt/atomic edit.
- Istniejące: storage/management_stake_repository.py, management_stake_models.py, management_result_snapshots.py — pins i wynik/fingerprint.
- Istniejące: api/management.py, api/management_public_structure.py, schemas/management.py, schemas/management_stakes.py — kontrakt.
- Istniejące: storage/management_manifest.py, storage/schema_readiness.py, storage/database_roles.py; scripts/provision_database_roles.py — ownership/readiness.
- Istniejące: packages/admin-api-client/src/management.ts i generowane źródła/OpenAPI; packages/board-search-ui/src/management/management-client.ts; apps/reviewer/src/security/management-proxy.ts.
- Nowe, proponowane: services/api/src/game_predictor_api/storage/management_mutation_repository.py i domain/management_pin_metrics.py — preview/purge orchestration i wspólna czysta semantyka pinów.
- Nowa, proponowana: services/api/alembic/versions/0152_management_compact_panel.py.
- Zrealizowane nowe pliki: api/management_mutations.py,
  storage/management_receipt_backfill.py, scripts/preview_management_receipt_migration.py,
  test_management_mutations.py, test_management_pin_metrics.py,
  integration/test_management_mutations_postgres.py,
  integration/test_management_receipt_backfill_postgres.py oraz wspólne fixtures pinów.
- Zrealizowane istniejące integracje: apps/reviewer/src/features/management/management-public-adapter.ts,
  test-interactions/management-panel.test.mjs i helper integration/_application_role_database.py.
- Testy istniejące services/api/tests/test_management*.py oraz integration/test_management*_postgres.py, klient/proxy; nowe testy mutation i złote fixtures.

## Test cases

- Create machine games i duplicate operation po utracie odpowiedzi → jeden zapis/journal.
- Purge punkt/maszyna/game z wynikami dzielonymi między maszynami i games → dokładny zakres i brak orphans.
- Nowy journal/refresh/revision między preview i confirm → stale conflict, brak częściowego sukcesu.
- Utrata odpowiedzi po commit i nowy proces → dokładny receipt; stare create/update/save/clear po purge → target deleted.
- App role + custom GUC direct DML → denied; owner bez GUC → denied; session audit zawsze denied.
- Revocation/session swap przed final flush → rollback, żadnego delete receipt sukcesu.
- Stare pins absent/null, spin0/ujemny balance/unavailable → dokładne wartości i bounded GET.
- Read-only migration preview rozróżnia journal/context/response i legacy exception; ponowienie migracji/rollback test na disposable DB.

## Verification

Katalog: root oddzielnego worktree. Każdą poniższą skończoną komendę wykonaj
z wymuszonym timeoutem 120s w runnerze; provisioning check:30s. PG wyłącznie
disposable DB, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 tylko w procesie testowym.
Brak venv/node_modules worktree wymaga izolowanego środowiska; nie buduj dist
ani aplikacji w głównym checkout operatora. Wyniki wykonanych kontroli znajdują
się w Outcome. Najpierw pion, potem lint/typecheck/scoped
format, dopiero regresje/build. Znany build >120s poprzedź komunikatem.

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_management.py services/api/tests/test_management_stakes.py services/api/tests/test_management_sessions.py services/api/tests/test_schema_readiness.py -q
.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_management_postgres.py services/api/tests/integration/test_management_stakes_postgres.py services/api/tests/integration/test_management_sessions_postgres.py -q
npm run openapi:check
npm run test --workspace @game-predictor/admin-api-client
npm run test --workspace @game-predictor/reviewer
```

Nowe moduły muszą dostać własne testy razem z kodem. Po zmianach Python uruchom
Ruff i mypy odpowiednich plików z istniejącej konfiguracji; TS: lint/typecheck
zmienionych workspace. PG ownership/provisioning uruchamiaj tylko na bazie
izolowanej. Każde pominięcie/skip i istniejący niezwiązany błąd podaj w Outcome.
Warunek zakończenia: kryteria potwierdzone, wymagany audyt bez otwartych P0/P1,
osobny commit i dokumentacja stanu. Brak audytu zatrzymuje następny task.

## Risks / open questions

Ryzyka: concurrent dedup/purge, immutable backfill i uprawnienia SECURITY DEFINER. Raport audytu jest warunkiem commita. Zgoda na API i kontrakt już udzielona w zaakceptowanym planie; informujemy operatora o rozpoczęciu tego pionu. Nie wolno użyć bazy operatora jako fixture. Przy konflikcie domeny/architektury zatrzymać zależny fragment.

## Outcome

### Changed

- Plan i cztery taski utrwalone w commicie v1.7.272,
  `32f78371d7deebae820c807a62178e4f2596925e`.
- Implementacja TASK-0940 jest przygotowana do niezależnego audytu. Atomowa
  maszyna, wspólne assignments, preview/delete po obu prefiksach, redakcja
  retry i PostgreSQL purge są połączone w jeden pion backend/kontrakt/klient/proxy.
- Migracja `0152_management_compact_panel` ma parent `0151_super_game_roles`;
  manifest v3, startup guard i provisioning sprawdzają nową granicę uprawnień.
  Read-only klasyfikator i instrukcja operatorska poprzedzają migrację danych.
- Piny zapisują wkład i kwotę na maszynie. Stare brakujące pola są wypełniane
  w odpowiedzi GET z zamrożonego wyniku, bez zapisu ani bieżących reguł.
- Współdzielone środowisko Python wskazywało główny checkout w nowych procesach.
  Helper fixture trwale ustawia PYTHONPATH dla procesów potomnych na źródła
  aktualnego worktree. Testy restartu sprawdzają już właściwą implementację.
- Założenie jawne: pusta lista gier w nowej/pustej maszynie nie usuwa zakresu;
  preview jest wymagane dopiero przy usunięciu istniejącego przypisania.

### Verification results

- Python, 53 PASS: test_management.py, test_management_mutations.py,
  test_management_pin_metrics.py, test_management_stakes.py,
  test_management_sessions.py, test_schema_readiness.py (12.02s).
- PostgreSQL, wszystkie pięć modułów PASS na disposable DB z rzeczywistą rolą
  aplikacji: structure, stakes, sessions, mutations, receipt_backfill.
  Ostatnie wyniki: purge+metadata 2 PASS (44.84s), stakes 1 PASS (23.48s),
  sessions i backfill PASS w zestawie 11 PASS/1 błąd testu (96.48s); błąd dotyczył
  nazwy importu obserwatora SQL w stakes i został naprawiony, stakes ponownie PASS.
  Nie twierdzimy, że ten wcześniejszy łączny przebieg był w całości zielony.
- Purge: wspólne wyniki między punktami, atomowe rename+detach/jedno journal,
  rollback, stare retry create/update/save/clear, pure delete po usunięciu rodzica
  oraz po restarcie procesu. Rzeczywisty `_version` blokuje współbieżny purge;
  po commit nowa referencja przeżywa. Testy mają ograniczone oczekiwanie.
- Granica SQL: app + GUC i owner bez flagi nie usuwają immutable historii;
  zmiana tożsamości receipt i session audit pozostają zabronione. Provisioning
  wykrywa PUBLIC EXECUTE, błędny SECURITY INVOKER purge i zmieniony search_path.
- Publiczne ścieżki preview/delete działają; expiry przed commit wycofuje purge
  i receipt. Istniejące revoke/token replacement races pozostają zielone.
- Backfill: cztery kategorie po jednym starym zapisie, read-only preview bez
  DML, rzeczywista migracja zachowuje UUID/aktora/checksum/czas; wyjątek fail-closed.
- Legacy GET fallback: sześć payloadów dla sześciu slotów, brak DML, metadata
  nadal niezmienione w DB. Golden fixtures Python 7 / istniejące helpery TS 5
  (zero/unavailable kontroluje Python; istniejący chart zachowuje zero).
- admin-api-client: build i 104 testy PASS; board-search-ui: 85 testów PASS.
  Reviewer management-proxy 11 PASS, management-panel interactions 14 PASS.
- OpenAPI export --check i check:generated PASS. Porównanie z HEAD: brak zmian
  ścieżek spoza management; tylko trzy rozszerzone istniejące DTO i sześć nowych.
- Ruff check/format: 30 plików PASS; strict scoped mypy: 25 źródeł PASS.
  Typecheck Admin, Reviewer, admin-api-client i board-search-ui PASS.
  Scoped ESLint proxy/public adapter/shared client PASS; client lint PASS.
- Pełny Reviewer: 236/238 PASS. Dwa wcześniejsze source-contract failures:
  test/local-reviewer-workspace-contract.test.mjs:52 i
  test/operational-review-workspace-contract.test.mjs:36. Dotyczą niezmienionych
  modułów poza panelem; wcześniejszy CURRENT_STATE dokumentuje tę parę.
- Pełny transitive mypy dochodzi do wcześniejszych błędów board_search_share_queries
  i worker shape_geometry_v2/core, a następnie timeout 120s. Nie zmieniono tych
  modułów ani konfiguracji repo, żeby uzyskać zielony wynik. Brak osieroconego mypy.

Kontrole uruchamiano z katalogu worktree. Interpreter:
`C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe`;
pytest używa pythonpath repo, dzieci fixture jawnie przypinają źródła worktree.
Node `C:\Program Files\nodejs\node.exe` 24.21.0 i npm-cli.js 11.19.0:
`C:\Program Files\nodejs\node_modules\npm\bin\npm-cli.js`.
Każdy proces miał timeout 120s (lint/format 30–60s); PG flag tylko w procesie
testowym. OpenAPI sprawdzono równoważnymi poleceniami export_admin_openapi.py
--check i npm run check:generated --workspace @game-predictor/admin-api-client,
ponieważ worktree nie ma własnego .venv. Dist i node_modules należą do worktree.

Scoped mypy używa tymczasowego `artifacts/audits/0940_mypy.ini`:

```ini
[mypy]
strict = True
python_version = 3.12
mypy_path = services/api/src,services/worker/src
follow_imports = normal
[mypy-game_predictor_api.*]
follow_imports = skip
[mypy-game_predictor_worker.*]
follow_imports = skip
```

Jawne argumenty to wszystkie zmienione pliki services/api/src oraz bazy typów:
storage/metadata.py, schemas/catalog.py, schemas/board_search_approximate_win.py,
application/board_search_approximate_win.py, application/board_search_board_detail.py,
domain/board_search_board_detail.py, domain/board_search.py,
domain/board_search_approximate_win.py. Te 25 źródeł pozostaje sprawdzanych strict;
zewnętrzne biblioteki są normalnie typowane. Pozostałe niezmienione moduły lokalne
są poza tym scoped sprawdzeniem. To nie zastępuje zielonego pełnego mypy.

### Not completed

- Nie wykonano drugiego audytu: jedyna uwaga P1 dotyczyła brakujących testów
  HTTP, poprawka nie zmienia zachowania backendu. Obowiązuje jedna runda
  poprawek; rozliczenie uwag jest poniżej i w raporcie audytu.
- Produkcyjna migracja/backfill/usuwanie, lifecycle usług, push/merge/deployment
  i benchmarki nie wykonane i nie są autoryzowane. Buildy całych aplikacji oraz
  nowe wizualne UI pozostają w kolejnych taskach planu.
- Definition of Done porównano z każdym kryterium taska i sekcją TASK-0940
  planu: wszystkie osiem kryteriów potwierdzają testy/analiza audytu; backend,
  kontrakt, migracja, klient/proxy i dokumentacja należą do tego samego pionu.
  Nie ma otwartych P0/P1. Ograniczenia pełnych wcześniejszych kontroli oraz
  zaakceptowane ryzyko P2-1 są jawne; UI i live rollout należą do kolejnych tasków.

### Documentation updates

- Wymagania/architektura panelu opisują implementowany kontrakt D-538,
  operator guide opisuje preview/backup/granty i osobną zgodę na dane.
- CURRENT_STATE zawiera stan oczekiwania na audyt i handoff. Skill claude-audit
  wygenerował `artifacts/audits/TASK-0940_BRIEF_claude.md` (321 KB,
  2026-10-09 00:25 +02:00), Base HEAD, pełne ścieżki taska. Skrypt nie uruchomił
  audytora, ponieważ CLI nie było w PATH; nie ma jeszcze werdyktu. Operator przekazał brief do
  `claude-fable-5-1 / high`; raport docelowy:
  `ai_docs/quality/TASK-0940_AUDIT_claude-fable-5-1.md`.
- Kolejne sprawdzenie znalazło CLI 2.1.293 w pakiecie Claude Desktop, pod fizyczną
  ścieżką LocalCache opisaną w CURRENT_STATE. Instalacja nie jest potrzebna.
  Osobne CLI zgłasza jednak `loggedIn=false`, `authMethod=none`; automatyczne
  przekazywanie kolejnych audytów pozostaje niezweryfikowane. Nie odczytano ani
  nie skopiowano poświadczeń i nie rozpoczęto logowania. Operator udzielił zgody
  na samodzielne przekazywanie audytów, bez ponownego pytania o wysłanie.
  Operator dostarczył raport TASK-0940; jego rozliczenie znajduje się poniżej.
  Nie zlecono drugiego audytu. Raport TASK-0940 w torze Mumie dotyczy innego zakresu i nie może
  zamknąć tego zadania. Należy potwierdzić worktree, zakres i bazę każdego raportu.

### Recommended next task

- TASK-0941 dopiero po zamknięciu tego taska.

### Audit resolution — jedna runda poprawek

Raport operatora zachowano bez zmiany werdyktu rundy 1 (`REVISE`):
`ai_docs/quality/TASK-0940_AUDIT_claude-fable-5-1.md`, audytor
claude-fable-5-1 / high, baza 32f78371, właściwy worktree panelu.
Rozliczenie wykonawcy nie jest drugim audytem ani werdyktem Claude `PASS`.

- P1-1 zamknięto: sześć domyślnych testów HTTP (trzy scenariusze × dwa
  prefiksy) obejmuje wszystkie pięć tras, produkcyjne mapowanie błędów i
  middleware. Sprawdza 200/token/expiry/commit/aktora, obie komendy unii,
  403 przed zapisem, 404 scope/missing, 409 missing/invalid preview, 422 brak
  gameIds i confirmed=false, 503 SQLite bez częściowego delete oraz brak
  tokenów w receipcie, journalu, hashach preview i lokalnym logu bezpieczeństwa.
- P2-1 zaakceptowane ryzyko: odpięcie redaguje także dawne receipty maszyny
  bez game_id. Nawet rename zawiera dawny snapshot przypisań; jego odtworzenie
  po odpięciu mogłoby przekazać klientowi usunięty zakres. Zachowano ochronę
  fail-closed, bez zmiany mechanizmu purge. Kod MANAGEMENT_TARGET_DELETED może
  dotyczyć unieważnionego zakresu starej odpowiedzi, choć maszyna nadal istnieje;
  klient musi odczytać aktualny snapshot zamiast traktować ten receipt jako
  dowód usunięcia całej maszyny. Nie zmieniono kodów API w rundzie poprawek.
- P2-2 zamknięto dokumentacją/handoff do0941: stary formularz odpinania nie
  przekazuje tokenu i zwraca409 do zakończenia0941; pominięte legacy
  attached=false również wymagają preview. CURRENT_STATE i operator guide
  ujawniają ten stan. TASK-0941 dostał obowiązek update-preview tego zakresu.
- P2-3 zamknięto: operator guide ma upgrade wyłącznie do0151, sprawdzenie
  rewizji, read-only preview, osobną zgodę i dopiero upgrade head/provisioning.
  Nie wykonano żadnego z tych poleceń na danych operatora.
- P2-4 zamknięto: D-538 i kontrakt planu jawnie wyłączają preview dla nowej
  lub już pustej maszyny; każdy usuwany istniejący wiersz nadal wymaga tokenu.
- P2-5 zamknięto doprecyzowaniem fixtures: zero i unavailable mają jawne
  metricSource wskazujące semantykę kontrolowanego wywołującego. TS helpery
  liczą tylko dostępne dodatnie spiny; kontrolowane zero/unavailable nie są
  wynikiem approximateWinStakeToPoint. Python sprawdza wszystkie siedem
  przypadków, TS pięć numerycznych. Nie deklarujemy siedmiu testów helpera TS.
- P2-6 zamknięto: przywrócono13 wygenerowanych plików o zerowym diffie
  treści; właściwe zmiany SDK/types/index/OpenAPI pozostają w tasku.

Kontrole po poprawkach: skoncentrowany Python59 PASS (27.54s), Ruff check/format,
Prettier fixture i git diff --check dla dokumentacji
i pięć testów helperów TS. Wcześniejszych kosztownych kontroli PG/klienta/types
nie powtarzano: poprawki nie zmieniają wykonywalnego kodu ani wygenerowanego API.
Commit taska: **v1.7.273**, `0625512d4a37072f1d6d44f3f85ef225e7db1835`.
Po commicie sprawdzono git show --stat i czysty git status. Ten zapis pełnego
hasha powstał po commicie; pozostaje metadanymi do utrwalenia z następnym taskiem.
