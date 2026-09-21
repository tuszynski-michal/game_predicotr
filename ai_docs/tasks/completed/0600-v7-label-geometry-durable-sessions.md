---
title: TASK-0600 V7 durable label geometry calibration sessions
status: in_progress
---

# TASK-0600 — Trwałe sesje kalibracji geometrii etykiet V7

## Status

done

## Goal

Serwerowa sesja anotacji V7 utrwala przypięte źródła i każde potwierdzone
działanie atomowo, idempotentnie i bez możliwości użycia holdoutu.

## Context

TASK-0599 przygotował wersjonane dowody punktu i cropu. Przed UI potrzebny jest
trwały stan, który przetrwa restart API, utraconą odpowiedź oraz konflikt dwóch
kart, nie zmieniając plików źródłowych ani bramki V7.

## Dependencies / entry conditions

- TASK-0599 / D-411: `v7-calibration-v2`, rodzina i kontrakty cropów.
- D-409: `reels_test` jest reserved holdout i nigdy nie tworzy sesji kalibracji.
- Założenie: pierwszy pion sesji zapisuje wyłącznie server-owned JSON pod
  `.runtime`; HTTP i wybór assetu należą do TASK-0601.

## Recommended execution

`gpt-5.6-terra` z `xhigh`, końcowy review `gpt-6-astra` z `medium`. Zmiana
formatu profilu, progu p95 lub dopuszczenie holdoutu wymaga eskalacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0599-v7-label-geometry-contract.md`

## Scope

- Czysty, framework-free magazyn sesji `.runtime/v7-label-geometry/sessions`.
- Zapis sesji z revision, manifest fingerprint, rodziną i przypiętymi SHA
  źródeł; pełna kontrola driftu dostarczonego inwentarza.
- Operacje `annotated`, `unavailable` i capture group z `operationId`,
  `expectedRevision`, trwałym receiptem i identycznym replayem.
- Blokada sesji, zapis fsync → replace, recovery po pliku tymczasowym,
  niezmienny eksport snapshotu.

## Out of scope

- Endpointy, OpenAPI, UI, IndexedDB, dekoder EXIF, pobieranie JPEG, OCR,
  profil gotowy do użycia, adopcje, worker i aktywacja.

## Acceptance criteria

- [ ] Ten sam `operationId` i ten sam payload zwraca pierwotny receipt przed
  kontrolą rewizji; inny payload z tym ID jest konfliktem.
- [ ] Zła rewizja, nieznane źródło, nieprawidłowy stan slotu, holdout lub drift
  inwentarza kończą się stabilnym błędem bez częściowego zapisu.
- [ ] Restart i odzyskanie prawidłowego temp przywracają ten sam stan; uszkodzone
  state/temp kończy się fail-closed.
- [ ] Dwie równoległe operacje nie mogą oba zmienić tej samej rewizji.
- [ ] Eksport jest niezmienny i nie tworzy kolejnej wersji przy identycznym
  snapshotcie.

## Technical notes

- `V7CalibrationSessionSource` jest już checksummowanym, server-created
  snapshotem; magazyn nie przyjmuje ścieżki od klienta.
- Stan slotu jest `unreviewed`, `annotated` albo `unavailable`. Punkt ma
  współrzędne [0,1] i ocenę cropu wyłącznie dla `annotated`.
- Przed mutacją magazyn porównuje pełny bieżący inwentarz źródeł z przypiętym;
  różnica trwale blokuje sesję `blocked_source_drift`.
- Wspólna blokada procesu i pliku obejmuje odczyt, deduplikację operation ID,
  rewizję, zapis atomowy i receipt. Odpowiedź nie jest dowodem zapisu;
  receipt jest w tym samym snapshotcie.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration_sessions.py`.
- Nowe: `services/worker/tests/test_v7_calibration_sessions.py`.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`, ten task card i ewentualny
  `DECISION_LOG.md` dla nowej trwałej granicy.

## Test cases

- Utworzenie z pięcioma calibration SHA → revision 0 i niezmienny snapshot.
- Annotate → utracona odpowiedź → ten sam operation ID/revision → ten sam
  receipt; różny payload → konflikt.
- Dwa zapisy z revision 0 → jeden sukces i jeden revision conflict.
- Restart magazynu, brak state z prawidłowym temp, błędny temp i różny SHA
  źródła → odpowiednio restore / fail-closed.
- Source holdout lub reference-only → odrzucenie; export z tą samą rewizją →
  ten sam SHA i jeden plik.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout 30 s
.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest-task-0600 services/worker/tests/test_v7_calibration_sessions.py -q
.venv\Scripts\python.exe -m ruff check <moduł-i-test>
.venv\Scripts\python.exe -m ruff format --check <moduł-i-test>
```

## Risks / open questions

- Sprawdzenie rzeczywistej ścieżki i EXIF nastąpi w TASK-0601; ten task ma
  testowalny, już przypięty inwentarz i nie przyjmuje ścieżek od klienta.

## Outcome

### Changed

- Dodano framework-free `V7CalibrationSessionStore` z przypiętym inwentarzem
  calibration-only, slotami `unreviewed`/`annotated`/`unavailable`, grupami
  ujęć, rewizją i receiptami idempotency.
- Snapshot sesji zapisuje `state.json.tmp`, fsyncuje i publikuje atomowo.
  Recovery dopuszcza tylko checksummowany, poprawny następnik zachowujący
  historię receiptów albo przejście `active` → `blocked_source_drift` bez
  zmiany anotacji.
- Eksport jest niezmienny: pełna suma jest identyfikatorem odpowiedzi, a krótki
  klucz ścieżki jest publikowany z pliku tymczasowego przez atomowy hard-link;
  kolizja prefiksu jest konfliktem.
- Odczyt weryfikuje zgodność ID snapshotu z katalogiem sesji, a blokada pliku
  i procesu zwalnia zasób również po błędzie otwarcia.

### Verification results

- 24 testy sesji i regresji kontraktu kalibracji: passed.
- Ruff check, Ruff format i compileall: passed.
- Mypy nowego modułu nie wykrył błędu w nim, ale pełne sprawdzanie nadal
  raportuje 13 wcześniejszych błędów importów/`Any` w ośmiu modułach
  `structured_geometry`.
- Self-audyt i trzy rundy Astra Medium: poprawiono recovery między temp a
  publikacją, eksport atomowy, izolację ID, zwalnianie locka oraz niezmienność
  receiptów i blokady; ostatni review nie znalazł dalszego problemu.

### Not completed

- Sesja nie ma jeszcze endpointów, assetów EXIF, UI ani realnych anotacji.
  V7 nadal pozostaje zablokowane.

### Documentation updates

- Dodano D-412 i aktualizację `CURRENT_STATE.md`.

### Recommended next task

- TASK-0601 — API/OpenAPI i bezpieczne, kanoniczne assety sesji.
