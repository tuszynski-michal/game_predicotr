# TASK-0599 — Kontrakt profilu geometrii etykiet V7

## Status

done

## Goal

Wersjonowany profil etykiet V7 mierzy centra, cropy i różnorodność źródeł bez
możliwości mieszania rodzin geometrii lub ponownego użycia wcześniejszego
raportu kalibracji.

## Context

Dotychczasowy lokalizator posiadał prowizoryczne cropy, lecz nie utrwalał
dowodów ich ręcznej weryfikacji ani niezależności ujęć. Ten task przygotowuje
kontrakty dla trwałej sesji anotacji, nie uruchamia V7.

## Dependencies / entry conditions

- TASK-0598 pozostawia V7 zablokowane przez serwer.
- D-409 rezerwuje `reels_test` jako wyłączny holdout.
- Ustalenie: rodzina `standard_3x3_numeric_labels_v1` obejmuje tylko numeryczne
  cropy etykiet; nie jest geometrią ramek ani modelem symboli.

## Recommended execution

`gpt-5.6-terra` z `xhigh`; końcowy review `gpt-6-astra` z `medium`. Eskalacja
jest konieczna tylko, gdy pomiar wymaga zmiany progu p95 lub użycia holdoutu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md`

## Scope

- Kontrakty anotacji, profilu, adopcji i ekspozycji źródeł.
- Globalny nearest-rank p95, pięć SHA i dwie grupy ujęć na pozycję.
- Manifest V2, pełna serializacja konfiguracji cropów i zgodność V1.
- `reels_test` jako holdout, `wybrane mumie` jako reference-only, a Treasure
  poza pierwszą rodziną.

## Out of scope

- API, UI, trwała sesja, anotacje użytkownika, OCR, runtime, output JPEG i
  aktywacja V7.

## Acceptance criteria

- [x] Kalibracja wymaga pięciu SHA-256, dwóch `captureGroupId`, `contained` i
  jednej rodziny na każdą pozycję.
- [x] Pełna konfiguracja cropów, residual per pozycja, profil, adopcja i
  ekspozycja mają deterministyczną reprezentację.
- [x] Manifest V1 zachowuje fingerprint, ale odrzuca niepuste pola V2;
  manifest V2 wiąże rodzinę i grę źródłową.
- [x] Nowy kontrakt kalibracji `v7-calibration-v2` odrzuca w T12 dawny raport
  `v1`.
- [x] Testy obejmują crop, różnorodność, rodziny, granice p95, V1/V2 i holdout.

## Technical notes

- `V7LabelGeometryAnnotation` przechowuje współrzędne [0,1], SHA, split,
  rodzinę, grupę ujęcia i ocenę cropu. Brak widocznego slotu będzie osobnym
  stanem sesji T0600, a nie zgadywanym punktem.
- Kalibracja nie akceptuje `clipped` ani `uncertain`. Mediana jest liczona per
  slot, a p95 to `sorted[ceil(0.95*N)-1]`; `0.04` przechodzi, `0.0401` nie.
- Profil zostanie wyeksportowany i adoptowany dopiero w kolejnych taskach;
  identyczny border nie jest dowodem adopcji.
- Ewalutor T12 odczytuje wyłącznie raport `v7-calibration-v2`, więc historyczny
  raport bez oceny cropów, grup ujęć i rodziny nie może spełnić nowej bramki.

## Expected files

- Istniejące: `v7_calibration.py`, `v7_configuration.py`,
  `v7_label_locator.py`, oba ewaluatory i ich testy.
- Nowe: `ai_docs/quality/v7-source-exposure-history.example.json`.

## Test cases

- Pięć SHA w dwóch grupach, kompletne cropy jednej rodziny → profil `passed`.
- Jedna grupa ujęć, crop `clipped`/`uncertain` albo mieszana rodzina → błąd.
- Globalny p95 poniżej/równo/powyżej `0.04` → odpowiednio passed/passed/failed.
- Manifest V1 bez nowych pól → ten sam fingerprint; pola V2 w V1 → odrzucenie.
- Raport `v7-calibration-v1` przekazany do holdoutu → odrzucenie.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout 30 s
.venv\Scripts\python.exe -m pytest --basetemp .tmp\pytest-task-0599-audit-fix services/worker/tests/test_v7_calibration.py services/worker/tests/test_v7_configuration.py services/worker/tests/test_v7_label_locator.py services/worker/tests/test_evaluate_v7_calibration_script.py services/worker/tests/test_evaluate_v7_holdout_script.py -q
.venv\Scripts\python.exe -m ruff check <zmienione-moduły-i-testy>
.venv\Scripts\python.exe -m ruff format --check <zmienione-moduły-i-testy>
```

## Risks / open questions

- Nie ma jeszcze realnych anotacji; p95 jest kontraktem i testem, nie wynikiem
  pomiaru materiału 777.
- Pełny mypy jest obecnie blokowany przez wcześniejsze błędy importów modułów
  `structured_geometry`, niezwiązane z tym taskiem.

## Outcome

### Changed

- Dodano rodzinę geometrii, grupy ujęć, ocenę cropu, profile, adopcje i
  checksummowaną historię ekspozycji.
- Zaktualizowano manifest do V2 z bezpieczną kompatybilnością V1.
- Zmieniono kontrakt kalibracji na `v7-calibration-v2` i zablokowano w T12
  wcześniejszy raport.

### Verification results

- 50 testów skoncentrowanych: passed.
- Ruff check i format: passed; compileall: passed.
- Mypy uruchomiono; wykrył 13 istniejących błędów importów i `Any` w ośmiu
  modułach `structured_geometry`, poza zmianami taska.
- Self-audyt i dwukrotny Astra Medium: poprawiono V1/V2 fingerprint i wersję
  raportu; końcowy review potwierdził brak dalszych problemów statycznych.

### Not completed

- Sesja anotacji, API i UI należą do kolejnych tasków.

### Documentation updates

- D-411, przykład manifestu V2, przykład historii ekspozycji i plan V7.

### Recommended next task

- TASK-0600 — trwałe sesje kalibracji.
