---
title: TASK-0756 — S3 — kompaktacja wyników pipeline na V2 i runbook utrzymania bazy
status: in_progress
last_updated: 2026-09-30
---

# TASK-0756 — S3 — kompaktacja wyników pipeline na V2 i runbook utrzymania bazy

## Status

`in_progress`

## Goal

Job `storage_pipeline_compaction` działa na magazynie V2 i zwalnia
reprodukowalne payloady etapów (`board_crops`, `symbol_inference`,
`board_cell_geometry`, `sequence_ocr`) z `public.image_pipeline_stage_results`
(6,8 GB, z tego 5,36 GB `board_crops`); operator ma runbook utrzymania
(VACUUM po dużych przebiegach, raport zajętości, kompaktowanie VHDX).

## Context

D-467, S3. Narzędzie z v0.9 (`scripts/compact_image_pipeline_state.py`,
`storage/pipeline_state_compaction_repository.py`,
`worker/pipeline_state_compaction.py`) nigdy nie było uruchomione
(`image_pipeline_terminal_manifests` = 0 wierszy). Podgląd 2026-09-30
zakończył się `UndefinedTable: image_import_job_files`: wykluczenia
(aktywny job importu, link `failed`, nierozwiązana geometria) czytają
`image_import_job_files`, `image_board_geometry_pending` i `source_images`,
które od D-374 są partycjami per gra w `game_data_v2` (RLS, wymagane
wiązanie `game_storage_scope`). `public.image_file_executions` i
`public.image_pipeline_stage_results` są globalne, bez `game_id`.

## Dependencies / entry conditions

- Fakt: przebiegi zapisu biblioteki wzorców zakończone (TASK-0750).
- Fakt: 56 714 executions `waiting_for_review`, 102 `failed`; 3 aktywne gry
  w `game_storage_locations`.

## Recommended execution

`claude-opus-5-5`, reasoning `medium` (warunkowo). Audyt: `claude-opus-5-5`,
`high`, osobny agent.

## Relevant docs

- `ai_docs/delivery/LEGACY_V1_REMNANTS_REMOVAL_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md` (D-467, D-374)
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` (sekcja storage)

## Scope

- Repozytorium podglądu: kandydaci nadal z globalnych
  `image_file_executions` + `image_pipeline_stage_results`; wykluczenia
  liczone per aktywna gra w `game_storage_scope(game_id)` (zbiory
  `file_execution_key` do wykluczenia: aktywny job importu, link `failed`,
  nierozwiązana geometria), zsumowane po grach, potem zastosowane do
  kandydatów; klucz wykonania bez żadnej gry (osierocony) traktowany jako
  wykluczony (fail-closed).
- Worker `_compact_entry`: ta sama ponowna kontrola wykluczeń per gra
  przed `DELETE`; manifest terminalny bez zmian.
- Skrypt: bez zmian kontraktu (`preview` / `start --confirm`).
- Test na izolowanej bazie PostgreSQL: gra V2 z executions: (a) zwykły
  kandydat → w podglądzie i usuwany, (b) z aktywnym jobem → wykluczony,
  (c) z nierozwiązaną geometrią → wykluczony, (d) klucz bez gry →
  wykluczony; `board_detection` zostaje.
- Runbook `ai_docs/guides/DATABASE_MAINTENANCE.md`: kolejność po dużych
  przebiegach (`VACUUM (ANALYZE)` tabel komórek i rewizji, kompaktacja
  pipeline, opcjonalnie `VACUUM FULL` w oknie bez zapisów z wymogiem
  wolnego miejsca), raport zajętości per tabela (zapytanie), kompaktowanie
  `docker_data.vhdx` przy zatrzymanym Dockerze (`Optimize-VHD` /
  `diskpart compact vdisk`), migracja danych na inny dysk (Docker disk image
  location, `GAME_PREDICTOR_ARTIFACT_ROOT`, repo).

## Out of scope

- Uruchomienie kompaktacji i `VACUUM FULL` na bazie operatora bez zgody;
  retencja zdarzeń weryfikacji; zmiana listy `DISPOSABLE_STAGE_PAYLOADS`.

## Acceptance criteria

- [x] `preview` na bazie operatora kończy się raportem (liczba kandydatów,
  bajty) bez błędu.
- [x] Test izolowany (a)–(d) przechodzi; `board_detection` nietknięte.
- [x] Runbook z komendami sprawdzonymi na tym repo (polecenia tylko do
  odczytu wykonane; destrukcyjne — `VACUUM FULL`, `diskpart`, `robocopy`,
  zmiana lokalizacji dysku Dockera — nie były uruchamiane).
- [x] Ruff, mypy, testy; audyt bez P0–P2.
- [ ] Wykonanie (`start --confirm`, worker, VACUUM) za osobną zgodą.

## Technical notes

- `game_storage_scope` jest `ContextVar`; wiązanie sesji per gra przez
  `GameStorageRouter().bind(session, game_id, intent=READ)` w pętli po
  `game_storage_locations` (status `active`). Przy zmianie gry w tej samej
  sesji wiązanie musi być odświeżone (sprawdzić `_require_same_binding`;
  w razie konfliktu osobna sesja per gra).
- Job jest checkpointowany i idempotentny; manifest podglądu z sumą
  kontrolną chroni przed zmianą zbioru.

## Test cases

- Jak w Scope; dodatkowo: klucz w dwóch grach (jedna wyklucza) → wykluczony.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -q services/api/tests/integration/test_pipeline_state_compaction_v2.py
.\.venv\Scripts\python.exe scripts/compact_image_pipeline_state.py preview
```

## Outcome

### Audit

- Audyt `claude-opus-5-5`: PASS w zakresie zadania. P2 poza zakresem: rola
  `game_predictor` jest superuserem z `BYPASSRLS`, więc RLS nie izoluje gier
  — dopisane jako TASK-0765 w planie D-467. P3 wdrożone: link importu w
  stanie nieterminalnym (job do ponowienia) chroni wykonanie; `VACUUM`
  kwalifikowany `public.`; runbook: wymóg wersji workera, czas podglądu,
  `lock_timeout` przy `VACUUM FULL`, `fstrim` przed `diskpart`, uwaga o
  `wsl --shutdown`. Pozostałe P3 (osobno): `rehydrate` po kompaktacji
  powinien jawnie odmawiać zamiast pomijać etap; test gry nieaktywnej w
  teście izolowanym; skrypty benchmarków ze sztywną ścieżką `artifacts`.
- Reguła zaostrzona względem Scope: gra w stanie innym niż `active` chroni
  wszystkie swoje klucze; worker sprawdza ponownie także linki `failed` /
  nieterminalne.


Stan: implementacja i runbook zacommitowane po audycie PASS; wykonanie
kompaktacji na bazie operatora czeka na zgodę.

- **Repozytorium podglądu**
  (`services/api/src/game_predictor_api/storage/pipeline_state_compaction_repository.py`):
  kandydaci stronicowani z globalnych `image_file_executions` +
  `image_pipeline_stage_results` w transakcji bez wiązania gry. Nowa funkcja
  `load_pipeline_execution_references(session_factory, keys)` czyta
  `public.game_storage_locations` i dla każdej gry otwiera osobną sesję z
  `game_storage_scope(game_id)` i `GameStorageRouter().bind(..., READ)`
  (jedna transakcja nie może związać dwóch gier). Per gra: klucze należące do
  gry (linki importu, źródła), wykluczenia (job `created`/`processing`, link
  `failed`, geometria `status != 'resolved'`) oraz identyfikatory źródeł i
  plansz do manifestu terminalnego. Zapytania są dodatkowo zawężone jawnie
  do gry (`jobs.game_id` / `game_id` wiersza): rola lokalna
  `game_predictor` jest superuserem z `BYPASSRLS`, więc samo RLS nie izoluje
  gier (test to wykrył — identyfikatory źródeł dublowały się między grami).
  Konstruktor przyjmuje teraz `sessionmaker` zamiast sesji.
- **Scalanie fail-closed** (`domain/pipeline_state_compaction.py`,
  `merge_game_execution_references`): kompaktowany jest tylko klucz należący
  do co najmniej jednej gry i niewykluczony w żadnej; klucz bez gry jest
  pomijany; gra w stanie innym niż `active` chroni wszystkie swoje klucze
  (zaostrzenie względem „tylko aktywne gry”: klucz współdzielony z grą
  `migrating`/`deleting` nie jest kompaktowany).
- **Worker** (`services/worker/src/game_predictor_worker/pipeline_state_compaction.py`):
  batch najpierw blokuje `image_file_executions` `FOR UPDATE` (posortowane
  klucze), potem liczy te same wykluczenia per gra i `_compact_entry`
  odrzuca klucz spoza `compactable_keys`. Linki V2 i źródła mają FK do
  `public.image_file_executions` (KEY SHARE), więc równoległy link albo jest
  już zatwierdzony i widoczny, albo czeka do końca batcha. Ponowna kontrola
  obejmuje teraz także link `failed` (wcześniej tylko podgląd). Manifest
  terminalny bez zmian.
- **Skrypt**: kontrakt `preview` / `start --confirm` bez zmian; `preview`
  przekazuje fabrykę sesji.
- **Testy**: nowy `services/api/tests/integration/test_pipeline_state_compaction_v2.py`
  (baza `game_predictor_task0756_*_test`, dwie gry przez `PROVISION`):
  (a) zwykły kandydat w podglądzie i usunięty przez worker, zostaje
  `board_detection` i manifest terminalny; (b) aktywny job, (c) geometria
  `pending`, (d) klucz bez gry, klucz w dwóch grach z linkiem `failed` w
  drugiej — wykluczone; klucz zablokowany po podglądzie (nowy job w drugiej
  grze) — konflikt workera, bez usunięcia. Unit testy scalania w
  `services/api/tests/test_pipeline_state_compaction_domain.py`. Wyniki:
  integracyjny 1 passed (ok. 11 s); domena + worker + routing 24 passed;
  ruff check/format i `mypy --strict` na zmienionych plikach źródłowych bez
  błędów.
- **Podgląd na bazie operatora** (2026-09-30, retencja 24 h, 163 s):
  `candidateCount` 56 710, `stageResultCount` 226 840, `candidateBytes`
  27 854 136 596 (długość tekstu JSON, bez kompresji; na dysku TOAST ok.
  6,0 GB), manifest
  `data/exports/storage-gc/pipeline-state/20feadcd-5608-49dc-b970-5c960d9ed19f/manifest.jsonl`,
  SHA-256 `6cdb9e10aaaa359b238750e88a3f79134ccd1d4c06f17c4e25a3e37cec2038a6`.
  Nieudany podgląd sprzed zmiany zostawił pusty katalog
  `pipeline-state/ee4c28f9-.../entries-*.tmp` (nieszkodliwy, bez manifestu).
- **Runbook**: `ai_docs/guides/DATABASE_MAINTENANCE.md` (link w
  `ai_docs/README.md` i w `LOCAL_OPERATION_GUIDE.md`). Sprawdzone na tym
  komputerze: zapytania raportu (przez potok PowerShell), preflight jobów,
  `pg_dump` przez `cmd /c` + `pg_restore --list` (próba na
  `public.alembic_version`), brak `Optimize-VHD` w Windows 11 Home, rozmiar
  VHDX 105,3 GB, wolne miejsce `C:` 43 GB.
- **Otwarte**: audyt; `start --confirm`, worker i `VACUUM FULL` za osobną
  zgodą; commit, `CURRENT_STATE.md`, przeniesienie zadania po odbiorze.
