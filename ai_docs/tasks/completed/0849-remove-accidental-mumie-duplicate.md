---
title: Remove the accidentally created Mumie duplicate
status: done
last_updated: 2026-10-05
---

# TASK-0849 — Usunięcie omyłkowej gry Mumie (`mumie-1`)

## Status

`done`

## Goal

Zarchiwizować i trwale usunąć wyłącznie omyłkową grę `mumie-1`, zachowując
oryginalną grę `mumie`, grę `777` i ich dane.

## Context

Operator potwierdził, że sam utworzył drugi wpis, i jawnie polecił:
„to niechcący ja stworzyłem. możesz ją zarchiwizować i usunąć”. Zgoda dotyczy
konkretnej gry `12180d9f-6c1a-43a9-a480-4056d2da81a9`, code `mumie-1`,
name `Mumie`, utworzonej 2026-10-05T12:29:35.777455Z.

## Dependencies / entry conditions

- TASK-0848 wdrożony; baza 0143, manifest `game-data-v2-manifest-v5`.
- Read-only preview: zero symboli, wersji zasad, jobów, danych partycji
  i ścieżek źródłowych; istnieje 9/64 partycji, status katalogu `draft`,
  magazynu `migrating`.
- Log API wskazuje retryable `LockNotAvailable` podczas tworzenia partycji
  `image_board_geometry_pending`. Należy odczytać receipt i stan blokad.
- Zachować `mumie` (`fea55cc1-ebf4-4cee-b3ab-a520017ed1be`) i `777`
  (`bfc4f949-5c14-4850-b02a-db99610bcfa5`).
- Zastane zmiany metadanych w worktree należą do wcześniejszych tasków;
  nie włączać ich do tego commita.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`: sprawdzenie tożsamości i checkpointu oraz
kontrolowane wykonanie istniejącego mechanizmu. Bez delegacji. Przy drift,
nieznanych zależnościach albo konieczności anulowania cudzej transakcji
zatrzymać zależny krok i zgłosić konkretny blocker.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — Games, stan magazynu.
- `ai_docs/architecture/API_CONTRACT.md` — Games i symbols, stan magazynu gry.
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — trwałe usunięcie zarchiwizowanej gry.

## Scope

- Zapisać read-only preview i snapshot chronionych wpisów w artefaktach.
- Wznowić istniejący provisioning, o ile checkpoint jest poprawny i running,
  przez istniejącą implementację; nie przestawiać statusu ręcznym SQL.
- Zarchiwizować dokładny UUID przez istniejący DELETE Admin API.
- Zapisać nowy preview, zweryfikować brak blokad i wykonać istniejące CLI
  z jego dokładnym fingerprintem oraz frazą potwierdzenia.
- Zweryfikować usunięcie w nowym procesie i zachowanie chronionych gier.

## Out of scope

Nowe funkcje, zmiany schematu/API/UI, migracje, restart usług, anulowanie
transakcji innych gier, import/trening/shadow, push/merge i usuwanie plików.

## Acceptance criteria

- [x] Tożsamość i pełny zakres zweryfikowane przed usunięciem; zgoda zapisana.
- [x] Standardowy provisioning zakończony; początkowa blokada już ustąpiła.
- [x] Gra zarchiwizowana przed uruchomieniem trwałego usunięcia.
- [x] Brak katalogu, registry i partycji `mumie-1`; delete receipt `done`.
- [x] Snapshot oryginalnych gier i jobów zgodny po operacji.
- [x] Nowy proces odczytuje wynik; brak usunięć plików i zmian usług.
- [x] Raport, Outcome i CURRENT_STATE zaktualizowane; osobny commit v1.7.195.

## Technical notes

Wznowienie provisioning korzysta z
`services/api/src/game_predictor_api/storage/game_partition_lifecycle.py`
(`GamePartitionLifecycleRepository.start_or_resume` i `run_next`) albo
identycznego POST `/api/v1/admin/games`. Każdy krok ma osobną transakcję,
lock timeout 2 s i statement timeout 30 s. Dopuszczalny jest wyłącznie
istniejący receipt `provision` i niezmieniona tożsamość. Ponowienie po
retryable timeout wymaga odczytu stanu; nie należy obchodzić guardów.

Archiwizacja: DELETE `/api/v1/admin/games/{gameId}` z lokalnym Origin,
`X-Admin-Intent: local-owner`, `X-Admin-Confirmation: confirmed` i
`X-Admin-Target: game:{gameId}`. Oczekiwany wynik 204.

Usunięcie: `scripts/delete_archived_v2_game.py`; najpierw preview, potem
`--execute --expected-preview-sha256 <SHA> --confirmation <dokładna fraza>`.
Retry kodu 2 wznawia checkpoint. Nie usuwa plików na dysku. Całość kroków
CLI ograniczyć do 120 s; odczyty i HTTP mają osobne krótkie limity.

## Expected files

- Nowy: `ai_docs/tasks/0849-remove-accidental-mumie-duplicate.md`, po wykonaniu
  przeniesiony do `ai_docs/tasks/completed/`.
- Nowy: `ai_docs/quality/MUMIE_DUPLICATE_REMOVAL_20261005.md`.
- Istniejący: `ai_docs/process/CURRENT_STATE.md`, wyłącznie sekcja TASK-0849.
- Lokalne artefakty: `artifacts/mumie-duplicate-removal-20261005/`.

## Test cases / Verification

- Read-only preview odrzuca `draft` i `migrating`; wynik już potwierdzony.
- Archiwizacja dokładnego UUID daje 204 i kolejny odczyt `archived`.
- Preview po archiwizacji nie ma blockerów; fingerprint sprawdzany przez CLI.
- Nowy proces: game/location nie istnieją, 0 partycji, delete receipt `done`.
- Chronione katalogi, magazyny i fingerprinty jobów są zgodne ze snapshotem.
- Kontrola dokumentacji i `git diff --cached --check`; bez nowych testów kodu,
  ponieważ nie zmieniamy implementacji.

## Risks / open questions

Blokada parent może powrócić. Najpierw ograniczone ponowienie i read-only
diagnostyka, bez przerywania cudzych procesów albo ręcznych zmian statusu.
Usunięcie jest trwałe; operator udzielił zgody na wskazany pusty duplikat.

## Outcome

### Changed

- Wznowiono wyłącznie receipt `a9b41fcb-3005-4bff-88d6-cf64e5e20d6e`,
  9/64 do 64/64, `done`; żadnych ręcznych zmian statusu SQL.
- DELETE Admin API zwrócił 204; odczyt potwierdził `archived`.
- Końcowy preview nie miał blockerów. Fingerprint
  `81eb8dcf941dfd77dc02c18c436dff034a534b18eb064a9ca1d9c2106ce7cfaa`
  i frazę `DELETE GAME mumie-1 12180d9f-6c1a-43a9-a480-4056d2da81a9`
  sprawdziło istniejące CLI przed usunięciem.
- Usunięto 64 partycje i katalog gry; delete receipt
  `d328ae9d-880d-43b0-8871-03054f482294`, `done`, bez failure_code.
  Jedynym rekordem partycji była domyślna polityka geometrii tworzona
  przez provisioning. Duplikat nie miał danych użytkownika ani plików.

### Verification results

- Read-only preview, receipt i blokady: PASS. Lock timeout z logu tworzenia
  nie powrócił; nie anulowano transakcji ani procesów.
- Provision: 8,92 s; archive: 3,81 s; preview: 4,84 s;
  wykonanie CLI: 12,70 s. Bez timeoutów wykonania.
- Świeży proces 2026-10-05T12:46:40Z: PASS, zero katalogu/registry/symboli/
  zasad/jobów/partycji duplikatu; API 404 `GAME_NOT_FOUND`.
- Oryginalne katalogi, magazyny, liczby symboli i fingerprinty wszystkich
  jobów `mumie` i `777` są identyczne ze snapshotem przed operacją.
- Helper odczytu początkowo przerwał na ochronnym limicie 500 jobów 777;
  zastąpiono go fingerprintem agregowanym w bazie. Pierwszy verifier oczekiwał
  obiektu `items`; poprawiono go zgodnie z kontraktem listy API. Oba błędy
  dotyczyły lokalnego helpera odczytu i nie wykonały mutacji danych.
- Własny review: kryteria taska i właściwe punkty DoD spełnione. Nie zmieniono
  kodu produktu; testy kodu, lint/typecheck/build i nowa migracja nie dotyczyły
  tego zadania. Kontrole staged diff i zakresu commita przed zapisem.

### Not completed

- Nie usuwano plików, nie restartowano usług, nie uruchamiano importu,
  treningu ani shadow. Nie wykonano push ani merge dokumentacji.

### Documentation updates

- `ai_docs/quality/MUMIE_DUPLICATE_REMOVAL_20261005.md`, ten task i sekcja
  TASK-0849 w CURRENT_STATE. Zastane metadane innych tasków poza commitem.
- Osobny commit `v1.7.195`; pełny hash dopisać po zapisie commita.

### Recommended next task

Brak dalszych działań dla duplikatu. Kontynuacja Mumii wyłącznie w oryginalnej
grze `mumie`.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0849 | gpt-6.1-sol | high | Kontrolowana operacja jednego UUID z istniejącym checkpointem, fingerprintem i weryfikacją izolacji. | Własny przegląd dowodów; bez delegacji. Zatrzymać przy drift albo nieznanej zależności. |
