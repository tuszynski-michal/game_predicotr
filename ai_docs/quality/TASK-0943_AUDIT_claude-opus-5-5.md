# Audyt TASK-0943 — Odbiór kompaktowego panelu i instrukcja operatorska

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6-sol, medium
Zakres: af1218b0685b5d472f2e7eb4842934b205f2ec26 (v1.7.275)...HEAD oraz zmiany niezacommitowane TASK-0943 (snapshot `artifacts/audits/TASK-0943_STAGE/audit-source`), data 2026-10-09
Runda: 1

To był przegląd statyczny. Audytor nie zmieniał żadnych plików i nie uruchamiał poleceń, testów ani usług.

## Streszczenie

Przejrzano przyrostowe skrypty odbioru przeglądarkowego, nowy test PostgreSQL backup/restore, zmianę `package.json` oraz aktualizacje dokumentacji. Na tej podstawie oceniono cały przepływ punkt → maszyna → stawka → zapis/zastąpienie/usunięcie względem celu operatora. Fixture rzetelnie sprawdza rzeczywiste współdzielone React/CSS na 390/1440/1920px i dla 1/4/40 punktów. Raport odbioru i Outcome jasno odróżniają wynik fixture od rolloutu produkcyjnego i gotowości do merge. Nie znaleziono błędów P0/P1.

Główne ryzyko to kolejność kroków w instrukcji operatorskiej. Polecenie migracji pojawia się przed sekcjami podglądu SQL i backupu. Przy nieodwracalnym hard delete wymaga to uporządkowania. Drugim ryzykiem jest integracja z main, która ma inną migrację 0152. Jest ona jawnie opisana jako osobny krok przed merge.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md:53-60` — Instrukcja zawiera dwie procedury migracji:
  - `alembic upgrade head` w sekcji D-536 (linia 54);
  - `alembic upgrade 0152_management_compact_panel` w sekcji „Apply schema” (linia 177).

  Pierwsza z nich stoi przed sekcjami podglądu SQL (linie 98-104) i backupu/restore (linie 127-169). Linie 13 i 44 wprawdzie warunkują ją backupem i zgodą, ale operator czytający od góry może uruchomić nieodwracalną migrację przed weryfikacją backupu. Dodatkowo `head` po integracji z main oznacza inną rewizję. Propozycja: zastąpić blok z linii 53-60 odwołaniem do sekcji „Apply schema” albo jedną numerowaną listą kroków: 0151 → klasyfikator → podgląd SQL → backup + restore → zgoda → upgrade 0152 → provisioning `--check` → ręczny start.
- [P2-2] `package.json:29` — `reviewer:management:browser` wywołuje teraz `python` z PATH zamiast `.venv\Scripts\python.exe`, wbrew konwencji z CLAUDE.md („All npm scripts call `.venv\Scripts\python.exe`”). Na maszynie bez globalnego Pythona albo z aliasem Microsoft Store bramka zakończy się błędem. Nie da fałszywego PASS, więc ryzyko jest niskie. Zmiana jest jawnie przewidziana w „Expected files” taska. Propozycja: użyć `.venv` z fallbackiem do `python` przez mały wrapper PowerShell albo zaakceptować ryzyko w Outcome.
- [P2-3] `scripts/management_browser_flow.mjs:2` i `:356` — Scenariusz `flow` startuje z `existing: true`, czyli z zapisanym slotem 20 PLN (`apps/reviewer/test-interactions/management-panel.test.mjs:343`). Dlatego klika „Zapisz zmiany”, a ścieżka pierwszego zapisu pustej stawki („Zapisz układ”, `MANAGEMENT_PANEL_OPERATIONS.md:256`) nie jest sprawdzana w przeglądarce. Pokrycie daje TASK-0942. Propozycja: w przyszłości dodać w flow zapis drugiej, pustej stawki albo zapisać w raporcie odbioru, że ta ścieżka pochodzi z TASK-0942.
- [P2-4] `ai_docs/architecture/MANAGEMENT_PANEL.md:182` — Zostało stare określenie „Open/Search again/Clear transitions”. D-536 zastąpiło ten przepływ akcjami „wybór stawki / Nowy układ / Zastąp / Usuń zapisany układ” (`DECISION_LOG.md`, adnotacja D-533). Nie jest to sprzeczny zakaz, tylko nieaktualna terminologia. Propozycja: zmienić na „Stake selection/Nowy układ/Zastąp/Usuń zapisany układ transitions”.
- [P2-5] `services/api/tests/integration/test_management_backup_restore_postgres.py:62` — `SELECT content_sha256 ... LIMIT 1` nie ma `ORDER BY`. Przy jednej wersji wyniku działa to deterministycznie, ale po rozszerzeniu seeda porównanie źródła z celem mogłoby losowo trafić na różne wiersze. Propozycja: dodać `ORDER BY id` albo porównywać posortowaną listę digestów.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Wszystkie kryteria planu mają dowód testu albo jawnie niewykonany odbiór operatora; brak fikcyjnego PASS | spełnione | `ai_docs/quality/ADMIN_COMPACT_PANEL_ACCEPTANCE.md:18-27`, `:61-70`, `:85-89`. Wyniki 55/56 i `docs:check` „Missing script” są opisane jawnie, bez deklarowania PASS. |
| Desktop i telefon bez horizontal overflow, max 320 i touch 44; niezależne UI Admin/Reviewer zgodne | spełnione (statycznie: asercje; wynik 10/10 według dowodu wykonawcy) | `scripts/management_browser_flow.mjs:165-224` (overflow, kolumny, nested button, 44px, 320px), `:144-147`, `:298-316` (kontenery 1000/750/500/320), `:234-281` (modale); `scripts/verify_management_panel_browser.mjs` (przypadki 390/1440/1920 × 1/4/40) |
| Świeży proces: trwałe receipty/zapisy/historia, odrzucona odwołana sesja, rollback całej transakcji | spełnione przez reużyte dowody TASK-0940 | `ADMIN_COMPACT_PANEL_ACCEPTANCE.md:23` (59 testów backend, 5 modułów PG); bez nowego uruchomienia |
| Read-only podgląd migracji z liczbą legacy, provisioning check i jedna głowa w torze panelu | spełnione na gałęzi; bramka produkcyjna operatora otwarta | `MANAGEMENT_PANEL_OPERATIONS.md:17-60`; `ADMIN_COMPACT_PANEL_ACCEPTANCE.md:24-25`; jedna głowa `0152_management_compact_panel` (offline `alembic heads`) |
| Instrukcja opisuje backup binarny i restore do osobnej DB, preview/confirm/migrację/ręczny restart; nie obiecuje rollbacku danych przez downgrade | spełnione (uwaga P2-1 o kolejności) | `MANAGEMENT_PANEL_OPERATIONS.md:127-169`, `:171-193`, `:195-206`, `:106-113`; test `test_management_backup_restore_postgres.py:136-196` |
| Requirements/architecture bez sprzecznego zakazu hard delete i bez archive-only workflow | spełnione | `ai_docs/requirements/MANAGEMENT_PANEL.md:20-27`, `:82`; `ai_docs/architecture/MANAGEMENT_PANEL.md:12`, `:79-80`; `DECISION_LOG.md` (adnotacja D-533) |
| Audyt Claude, Outcome i osobny commit; brak push/merge/deployment | częściowo — ten audyt PASS; commit i `done` pozostają do wykonania | `ai_docs/tasks/0943-management-compact-acceptance.md` (Outcome, „Not completed”) |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `scripts/management_browser_flow.mjs`: w scenariuszu `flow` dodać pierwszy zapis pustej stawki (np. 10 PLN) przyciskiem „Zapisz układ”. Polecenie: `npm run reviewer:management:browser`.
- `services/api/tests/integration/test_management_backup_restore_postgres.py`: porównywać posortowaną listę `content_sha256` oraz liczbę `management_machines`. Polecenie: `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_management_backup_restore_postgres.py`, tylko na izolowanych bazach `*_test`.

## Zakres przeglądu i ograniczenia

Przeczytano ze snapshotu TASK-0943:
- `scripts/management_browser_flow.mjs` (w całości);
- `services/api/tests/integration/test_management_backup_restore_postgres.py` (w całości);
- `ai_docs/quality/ADMIN_COMPACT_PANEL_ACCEPTANCE.md` (w całości);
- `ai_docs/process/MANAGEMENT_PANEL_OPERATIONS.md` (w całości);
- wybrane fragmenty `ai_docs/architecture/MANAGEMENT_PANEL.md`, `package.json` i wyniki grep wymagań oraz dokumentów pod kątem archive/hard delete.

Pozostałe pliki zmiany sprawdzono na podstawie diffu z briefu. W worktree sprawdzono listę migracji 0150-0152, konfigurację mypy oraz fixture `backend()` w teście Reviewera.

Nie uruchamiano testów, buildów, przeglądarki, PostgreSQL ani `alembic`. Wyniki 10/10, 41/41, 39/39, 1/1 restore i buildy przyjęto jako dowody wykonawcy oraz reużyto wcześniejsze audyty 0941 (runda 2 PASS) i 0942 (PASS). Nie weryfikowano integracji z main `1b97ad65` (inna migracja 0152, koszt per pozycja). Jest to jawnie odłożony krok przed merge, a ten PASS nie oznacza gotowości do merge ani rolloutu produkcyjnego. Fizyczne urządzenie, live ingress, restart komputera i bramki danych operatora pozostają do odbioru przez operatora.
