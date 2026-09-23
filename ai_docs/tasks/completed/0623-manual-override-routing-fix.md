---
title: TASK-0623 — poprawka routingu wpisów manifestu ze slotQualifications
status: done
last_updated: 2026-09-23
---

# TASK-0623 — poprawka routingu wpisów manifestu ze slotQualifications

## Status

`done`

## Goal

Import stron ze stagingu, na którym strony zostały zaakceptowane
automatycznie przez relaksację D-420 (mają `slotQualifications`, ale
`registrationVersion != "manual-page-geometry-override-v1"`), przechodzi
zamiast kończyć się `IMAGE_PAGE_GEOMETRY_INVALID: Qualified manual page
evidence is incomplete.`.

## Context

Użytkownik wykonał ręczną korektę geometrii na stagingu `a139379b` (odbiór
T1/T2), a następnie uruchomił import (job `562b0cd1-b9dd-4fa5-83d7-2b4908333fab`,
`import`, `failed`, `IMAGE_PAGE_GEOMETRY_INVALID: Qualified manual page
evidence is incomplete.`, 2952/2952 progress, 0 success).

Diagnoza (potwierdzona w kodzie i bazie, read-only): w
`production_workflow.py:1975` routing `if isinstance(manual_entry, Mapping)
and "slotQualifications" in manual_entry:` sprawdza wyłącznie obecność klucza
`slotQualifications`, nie `registrationVersion`. Klucz ten pojawia się w
manifeście geometrii stron z dwóch niezależnych źródeł:

1. Prawdziwa ręczna korekta (Admin, `page-geometry-correction-panel`) →
   `registrationVersion: "manual-page-geometry-override-v1"`
   ([page_geometry_preflight.py:1089](../../services/worker/src/game_predictor_worker/images/page_geometry_preflight.py)).
2. Automatyczna rejestracja przez relaksację D-420 (jedna słaba plansza) →
   `registrationVersion: "verified-page-registration-v1"`
   (`PAGE_REGISTRATION_VERSION`), ale też ma `slotQualifications`
   (`_slot_qualifications_for_relaxed_coverage`,
   `page_geometry_registration.py`, wprowadzone `v0.10.367`, **przed**
   T1/T2 z tej sesji).

Obecny routing wpada w gałąź #1 dla obu przypadków. Dla #2
`apply_qualified_page_override` odrzuca wpis (`qualified_manual_geometry.py:178-186`),
bo `registrationVersion != "manual-page-geometry-override-v1"`.

Bug jest pre-existing (od `v0.10.367`, 17 commitów przed T1/v0.10.388),
niezwiązany z T1/T2. Ujawnił się teraz, bo to pierwsza próba pełnego
importu stagingu `a139379b`, na którym (per fakty z planu T1/T2) większość
już zarejestrowanych stron przeszła przez relaksację D-420
(`slotQualifications` obecne, `registrationVersion` inny niż manualny).

## Dependencies / entry conditions

- Brak zależności od T1/T2 poza tym, że bug ujawnił się przy odbiorze ich
  wyniku. Nie wymaga cofania żadnej zmiany z T1/T2.
- Serwery lokalne (API, DB) działają; worker zrestartowany po T2.

## Recommended execution

`claude-sonnet-5`, reasoning `medium`. Uzasadnienie: jednoznaczna,
potwierdzona przyczyna (brak sprawdzenia `registrationVersion` w istniejącym
warunku), lokalna poprawka jednego warunku plus test regresyjny
odtwarzający zgłoszony przypadek (import z realnym błędem z bazy). Eskalacja:
gdyby poprawka warunku miała wpływać na inne gałęzie routingu (V1.2,
lateral partial) w sposób niejasny z samego kodu.
Dodatkowy review: nie wymagany.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-420, D-430, D-431)
- `ai_docs/requirements/IMAGE_INGESTION.md`

## Scope

- `services/worker/src/game_predictor_worker/images/production_workflow.py`:
  warunek routingu w `_detect_structured_geometry` (~linia 1975).
- Nowy test regresyjny w `services/worker/tests/test_production_image_workflow.py`.
- Dokumentacja: `DECISION_LOG.md` (nowy wpis), `CURRENT_STATE.md`.

## Out of scope

- Ścieżka V1.2 (`apply_v12_page_geometry`, `contrast_frame_grid_v1_2`) — inny
  routing (`self._geometry_engine_variant`), niezwiązany z tym bugiem.
- Ścieżka lateral partial (`lateralRegistrationCandidate`) — inny klucz,
  niezwiązany.
- `qualified_manual_geometry.py` — logika `apply_qualified_page_override`
  sama w sobie jest poprawna dla prawdziwych ręcznych override'ów; problem
  jest wyłącznie w tym, KIEDY jest wywoływana.
- `_relaxed_red_edge_accepted`, `_slot_qualifications_for_relaxed_coverage`,
  progi D-420, zmiany z T1/T2 — bez zmian.
- Ponowne uruchomienie importu na danych produkcyjnych — poza zakresem
  code-only taska; użytkownik uruchamia po potwierdzeniu poprawki.

## Acceptance criteria

- [x] Wpis manifestu z `status: "registered"`, `slotQualifications`
      obecnym i `registrationVersion` innym niż
      `"manual-page-geometry-override-v1"` (np. `PAGE_REGISTRATION_VERSION`)
      przechodzi przez zwykłą ścieżkę `_registered_page_geometry` (detektor
      strukturalny z pinned quads), NIE przez `apply_qualified_page_override`.
- [x] Wpis manifestu z `registrationVersion: "manual-page-geometry-override-v1"`
      i `slotQualifications` nadal przechodzi przez `apply_qualified_page_override`
      (bez wywołania detektora) — istniejący test
      `test_qualified_manual_page_keeps_all_slots_without_detector_or_missing_pixel_inference`
      pozostaje zielony bez zmiany asercji.
- [x] Nowy test regresyjny odtwarza dokładnie zgłoszony przypadek: wpis
      `registered` z `slotQualifications` i
      `registrationVersion=PAGE_REGISTRATION_VERSION` nie kończy się
      `IMAGE_PAGE_GEOMETRY_INVALID`.
- [x] Wszystkie istniejące testy `test_production_image_workflow.py`
      pozostają zielone bez osłabienia asercji.
- [x] `ruff` i `mypy` czyste (bez nowych błędów) dla zmienionego pliku.

## Technical notes

Aktualne zachowanie: `production_workflow.py:1975`
```python
if isinstance(manual_entry, Mapping) and "slotQualifications" in manual_entry:
```

Wymagane zachowanie: dodać wymóg `registrationVersion ==
"manual-page-geometry-override-v1"`, np.:
```python
if (
    isinstance(manual_entry, Mapping)
    and manual_entry.get("registrationVersion") == "manual-page-geometry-override-v1"
    and "slotQualifications" in manual_entry
):
```
Literał `"manual-page-geometry-override-v1"` już istnieje w tym samym pliku
(`qualified_manual_geometry.py:179`) i w `page_geometry_preflight.py:1089` —
sprawdzić, czy w `production_workflow.py` istnieje już nazwana stała do
reużycia zamiast wpisywać drugi literał; jeśli nie, zaimportować
`registrationVersion` z jednego miejsca (np. z `qualified_manual_geometry`
jeśli tam już jest zdefiniowany jako stała, w przeciwnym razie zostawić
literał zgodny z pozostałymi dwoma wystąpieniami — nie wprowadzać nowej,
czwartej wersji stringa).

Auto-zarejestrowane wpisy (`registrationVersion=PAGE_REGISTRATION_VERSION`
lub `PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION`) z `slotQualifications`
przejdą wtedy do bloku `_registered_page_geometry` (linia ~2014), który już
poprawnie obsługuje taki wpis (nie czyta `slotQualifications` w ogóle —
używa tylko `quads`/`boardRedEdgeCoverages`) i uruchamia normalny silnik
strukturalny z pinned quads jako seed. To zachowanie sprzed D-420 dla
wpisów `baseline_accepted` (bez `slotQualifications`) — nie zmienia się.

Przykład wejście → wynik: manifest entry `{"status": "registered", "quads":
[...9 quadów...], "boardRedEdgeCoverages": [...9 wartości...],
"registrationVersion": "verified-page-registration-v1",
"slotQualifications": [...9 kwalifikacji, jedna z
exclude_from_geometry_training=True...]}` → `board_detection` zwraca
`recoveryMode: "pinned_verified_page_registration"` (nie
`geometrySource: "manual"`), 9 plansz, bez wyjątku.

## Expected files

- Istniejące:
  `services/worker/src/game_predictor_worker/images/production_workflow.py`
  (`_detect_structured_geometry`).
  `services/worker/tests/test_production_image_workflow.py` (nowy test).
  `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Nowy test (obok `test_pinned_final_page_geometry_uses_only_attested_five_boards`):
  manifest entry ze `status: "registered"`, `slotQualifications` (jedna
  plansza `exclude_from_geometry_training=True`), `registrationVersion:
  PAGE_REGISTRATION_VERSION` → `board_detection` zwraca
  `recoveryMode == "pinned_verified_page_registration"`, nie rzuca wyjątku.
- Regresja: `test_qualified_manual_page_keeps_all_slots_without_detector_or_missing_pixel_inference`
  (oba warianty `all_missing`) bez zmian.
- Regresja: `test_pinned_final_page_geometry_uses_only_attested_five_boards`
  bez zmian (ten wpis nie ma `slotQualifications`, więc i tak zawsze szedł
  ścieżką zwykłą — sprawdza, że dodanie warunku `registrationVersion` nie
  psuje przypadku, gdzie klucz `slotQualifications` w ogóle nie występuje).

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_production_image_workflow.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/images/production_workflow.py services/worker/tests/test_production_image_workflow.py
.\.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/images/production_workflow.py
```

Timeout 120 s na każdą komendę.

## Risks / open questions

- Real dane: po poprawce kodu ponowne uruchomienie importu na
  `a139379b` wymaga osobnej akcji operatora (poza zakresem code-only
  taska) — nowy job importu, nie automatyczny retry starego.

## Outcome

### Changed

- `services/worker/src/game_predictor_worker/images/production_workflow.py`:
  warunek routingu w `_detect_structured_geometry` (~linia 1975) wymaga
  teraz `manual_entry.get("registrationVersion") ==
  "manual-page-geometry-override-v1"` oprócz obecności `slotQualifications`,
  zanim wpis trafi do `apply_qualified_page_override`. Literał zgodny z
  pięcioma istniejącymi wystąpieniami tego samego stringa w kodzie
  (`page_geometry_preflight.py`, `qualified_manual_geometry.py`,
  `page_geometry_incremental.py`, `large_import_geometry_guard.py`) — brak
  nazwanej stałej w repo, więc nie wprowadzono nowej.
- `services/worker/tests/test_production_image_workflow.py`: nowy test
  `test_relaxed_auto_registration_with_slot_qualifications_skips_manual_override_path`,
  zbudowany na wzorcu `test_structured_v2_binds_registered_preflight_quads_to_the_source`
  (fake `_StructuredGeometryEngine`, `_structured_default_rollout()`), żeby
  faktycznie przejść przez `_detect_structured_geometry` (nie tryb legacy).
  Pierwsza wersja testu (wzorowana na innym, legacy-routed teście) fałszywie
  przechodziła bez wykrycia buga — `board_detection()` domyślnie (bez
  jawnego `geometry_rollout`) używa `_legacy_board_detection`, która nigdy
  nie wywołuje `apply_qualified_page_override`. Zweryfikowałem to przez
  debug print w kodzie (branch nigdy nie wchodzony) i przepisałem test na
  jawny nie-legacy rollout.
- `ai_docs/process/DECISION_LOG.md`: nowy wpis D-432 (na górze pliku).
- `ai_docs/process/CURRENT_STATE.md`: nowa sekcja TASK-0623 na górze.
- `ai_docs/tasks/0623-manual-override-routing-fix.md`: utworzony i
  uzupełniony (ten plik).

### Verification results

- `pytest services/worker/tests/test_production_image_workflow.py::test_relaxed_auto_registration_with_slot_qualifications_skips_manual_override_path -q`:
  najpierw zielony z poprawką; następnie tymczasowo cofnięta poprawka
  (niecommitowana) → test failuje z dokładnie tym samym błędem co
  zgłoszony przez użytkownika (`ImagePipelineExecutionError: Qualified
  manual page evidence is incomplete.`, ślad przez
  `_detect_structured_geometry` → `apply_qualified_page_override`);
  poprawka przywrócona, test znów zielony.
- `pytest services/worker/tests/test_production_image_workflow.py -q`:
  59 passed (58 istniejących bez zmian w asercjach + 1 nowy).
- `ruff check` na obu zmienionych plikach: czysty.
- `mypy` na zmienionym pliku źródłowym: 89 błędów, w tym głównie
  `import-not-found` dla `game_predictor_api.*` (ten plik ma dużo więcej
  importów niż `page_geometry_registration.py` z T1, stąd wyższa liczba).
  Potwierdzone `git stash` na samym pliku (baseline bez zmiany z tego taska):
  dokładnie 89 błędów, identyczna liczba — zero nowych błędów.

### Not completed

- Ponowne uruchomienie importu na `a139379b` z danymi produkcyjnymi — worker
  uruchomiony po T2 nie ma jeszcze tej poprawki; wymaga kolejnego restartu
  workera i osobnej akcji operatora poza zakresem code-only taska.
- Sprawdzenie, czy inne, analogiczne miejsca w kodzie (np. `page_geometry_incremental.py`,
  `large_import_geometry_guard.py`) mają ten sam wzorzec sprawdzania
  wyłącznie obecności klucza bez `registrationVersion` — nie było w zakresie
  zgłoszonego bugu (tam string `"manual-page-geometry-override-v1"` już
  występuje jako część warunku, per `git grep` wykonany podczas diagnozy),
  ale nie zostało to formalnie zweryfikowane testem.

### Documentation updates

- `ai_docs/process/DECISION_LOG.md` (D-432), `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- Restart workera i ponowna próba importu stagingu `a139379b` (operator).
- Rozważyć krótki audit pozostałych 4 miejsc z literałem
  `"manual-page-geometry-override-v1"` pod kątem tego samego wzorca błędu
  (`page_geometry_incremental.py:607`, `large_import_geometry_guard.py:152`),
  jeśli po ponownym imporcie pojawią się kolejne nieoczekiwane błędy.
