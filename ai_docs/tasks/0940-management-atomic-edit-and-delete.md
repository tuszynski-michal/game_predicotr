---
title: Atomowa maszyna, preview i trwałe usuwanie zakresu panelu
status: todo
last_updated: 2026-10-08
---

# TASK-0940 — Atomowa maszyna, preview i trwałe usuwanie zakresu panelu

## Status

`todo`

## Goal

Dostarczyć jeden zgodny pion API do atomowej edycji maszyny, bezpiecznego hard delete oraz szybkich danych pinów.

## Context

Operator chce minimalnego UI i szybkiego przechodzenia między punktami, maszynami
i stawkami. Cały plan jest zaakceptowany i uruchomiony; koszt oraz manualne audyty
zostały uzgodnione. Nie trzeba rekonstruować historii rozmowy.

## Dependencies / entry conditions

Plan zaakceptowany, D-536 zapisane, worktree od 3bc6c64b. TASK-0933–0936 nie blokują. Przed migracją potwierdzić wolny pełny revision ID i head0151. Żadna migracja na danych operatora nie jest dozwolona.

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
- ai_docs/process/DECISION_LOG.md — D-536 i D-533.
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

- [ ] Atomowy create/update name+games, omitted games bez zmiany, inactive game bez nowego przypisania; rollback przy błędzie.
- [ ] Detach bez tokenu zwraca 409 MANAGEMENT_PREVIEW_REQUIRED. Token z innego aktora/body/rewizji, wygasły lub stale nie kasuje niczego.
- [ ] Purge kasuje tylko zakres panelu w opisanej kolejności; współdzielony wynik przeżywa, globalne korekty i session audit pozostają.
- [ ] App ustawiająca GUC i kasująca bezpośrednio oraz owner bez flagi otrzymują odmowę triggera; funkcja ma prawidłową własność i granty.
- [ ] Exact retry delete zwraca własny receipt także po usunięciu rodzica; stare create/update/save/clear nie odtwarzają usuniętej encji.
- [ ] Nieznane stare receipty policzone w preview i fail-closed; brak tokenów/sekretów w response history/logs.
- [ ] Złote przykłady pinów zgodne Python/TS, zero i unavailable; GET fallback nie zapisuje i ma limit6×6.
- [ ] Publiczny revoke/expiry/replacement session podczas operacji blokuje commit; generowane typy i klient są zgodne.

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
ani aplikacji w głównym checkout operatora. Testy poniżej są planowane,
nie zostały jeszcze uruchomione. Najpierw pion, potem lint/typecheck/scoped
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

- Nie rozpoczęto implementacji. Plan i task utrwalone; następny krok: warunki wejścia i kod.

### Verification results

- Brak wyników testów implementacji; komendy powyżej są planem.

### Not completed

- Implementacja, testy, ręczny audyt Claude i commit taska.

### Documentation updates

- Task utworzony według zaakceptowanego planu, D-536.

### Recommended next task

- TASK-0941 dopiero po zamknięciu tego taska.
