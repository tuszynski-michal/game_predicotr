---
title: TASK-0173 local worker lane process supervisor
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0173 — Local worker lane process supervisor

## Status

`done`

## Goal

Zapewnić trwały i kontrolowany sposób uruchamiania obu lokalnych worker lanes
bez dwóch stale otwartych terminali oraz bez ryzyka przypadkowego uruchomienia
drugiej kopii tego samego lane.

## Context

TASK-0172 rozdzielił wykonanie na `general` i `image-selection`, ale operator
nadal musi ręcznie uruchamiać dwa procesy. Wielogodzinne joby powinny działać w
tle, mieć osobne logi i dać się bezpiecznie sprawdzić oraz zatrzymać. Jednorazowe
zakończenie procesu albo PID bez weryfikacji czasu startu nie jest wystarczające,
ponieważ Windows może ponownie użyć tego samego PID.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/tasks/completed/0172-dedicated-image-selection-worker-lane.md`

## Scope

- dodać jeden skrypt operatorski z akcjami `Start`, `Status` i `Stop`,
- pozwolić zarządzać oboma lane albo jednym wskazanym lane,
- uruchamiać bezterminowe procesy w ukrytym tle z osobnymi logami,
- atomowo zapisywać ignorowany stan runtime z PID, nazwą procesu i czasem
  startu,
- przed użyciem PID potwierdzać tożsamość procesu także przez czas startu,
- usuwać stare wpisy po restarcie i uruchamiać wyłącznie brakujące procesy,
- serializować równoległe operacje start/stop krótką blokadą pliku,
- dodać proste komendy npm i instrukcję operatorską.

## Out of scope

- automatyczny start przy logowaniu albo przez Harmonogram zadań Windows,
- uruchamianie API, Admina, Reviewera lub PostgreSQL,
- nowy kontener, mikroserwis, URL, broker albo baza danych,
- zmiana algorytmu selekcji, execution lanes lub kontraktu OpenAPI,
- automatyczne ograniczanie CPU/RAM między równoległymi jobami.

## Acceptance criteria

- [x] `npm run workers:start` uruchamia najwyżej jeden proces każdego lane i
      wraca do terminala po ograniczonej czasowo kontroli startu.
- [x] Ponowne wywołanie startu jest idempotentne i nie tworzy duplikatów.
- [x] `npm run workers:status` pokazuje stan, PID, czas startu i ścieżki logów.
- [x] `npm run workers:stop` zatrzymuje wyłącznie zweryfikowane procesy i jest
      idempotentne.
- [x] Stary stan po restarcie nie blokuje ponownego uruchomienia workerów.
- [x] Każdy lane można uruchomić lub zatrzymać niezależnie.
- [x] Składnia PowerShell i kontrolowany test start/status/stop przechodzą bez
      pozostawienia osieroconych procesów.
- [x] Dokumentacja opisuje nową preferowaną procedurę i ręczne komendy
      foreground pozostają dostępne diagnostycznie.

## Expected files

- `scripts/manage_worker_lanes.ps1`
- `package.json`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
npm run powershell:check
npm run workers:status
npm run workers:start
npm run workers:start
npm run workers:status
npm run workers:stop
npm run workers:status
```

## Risks / assumptions

- Supervisor zarządza wyłącznie procesami uruchomionymi przez siebie. Ręcznie
  uruchomiony `npm run worker:poll` pozostaje odpowiedzialnością operatora.
- Procesy nie startują automatycznie po restarcie Windows. Stary stan jest
  rozpoznawany jako nieaktywny, a jedno `npm run workers:start` odtwarza oba
  lane.
- Równoległe lane nadal konkurują o lokalny CPU, RAM i dysk.

## Outcome

Dodano `manage_worker_lanes.ps1` z akcjami `Start`, `Status` i `Stop`, wyborem
obu albo pojedynczego lane, atomowym stanem oraz blokadą operacji. Procesy są
uruchamiane bez blokowania terminala i otrzymują osobne logi. Tożsamość przed
zatrzymaniem jest potwierdzana przez PID, nazwę procesu i dokładny UTC start
time, dlatego ponownie użyty PID nie zostanie omyłkowo zakończony.

Komendy `workers:start`, `workers:status` i `workers:stop` zostały sprawdzone na
obu lane. Drugi start zachował te same PID-y, stop był idempotentny, a
kontrolowane zakończenie jednego zarządzanego procesu odtworzyło scenariusz po
restarcie: status zwrócił `stale`, kolejny start utworzył nowy PID i końcowy
status obu lane wyniósł `stopped`. Logi błędów testowych procesów były puste.
`powershell:check` potwierdził poprawną składnię wszystkich 24 skryptów, a
`git diff --check` nie wykazał błędów whitespace.
