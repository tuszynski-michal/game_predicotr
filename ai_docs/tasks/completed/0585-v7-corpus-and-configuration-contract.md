---
title: TASK-0585 — V7 corpus and configuration contract
status: done
last_updated: 2026-09-20
---

# TASK-0585 — Korpus i konfiguracja v7

## Status

`done`

## Goal

Udostępnić deterministyczny kontrakt pełnych stron v7 oraz zamrażalny manifest korpusu bez ścieżki testowej w kodzie produkcyjnym.

## Context

T00 potwierdził runtime OCR, lecz nie dodatni proof na zdjęciach. T01 nie rozszerza OCR; ustanawia jedyne dopuszczalne wejście konfiguracji i dane, na których T02–T05 będą mierzone.

## Dependencies / entry conditions

- T00 jest ukończone w `v0.10.318`; lokalny manifest może wskazywać zewnętrzny katalog testowy.
- `wybrane mumie` jest wyłącznie `reference_only`, nigdy dowodem grupowania.

## Recommended execution

`gpt-5.6-terra xhigh`; niezależny review `gpt-6-astra medium` przed commitem. Zatrzymać task przy niejednoznacznym semantycznie wejściu konfiguracji, a nie zgadywać kierunek zdjęć z nazw.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- Normalizacja pojedynczego numeru i pełnego zakresu 3×3; kierunek stron, nazwy rosnące i sąsiedni output `cut`.
- Trzy style ramki i testowy manifest korpusu z rozłącznymi splitami oraz fingerprintami plików.

## Out of scope

- OCR, geometria, ranking, job, migracja, API, UI i zapis JPEG-a.

## Acceptance criteria

- [x] `1` normalizuje się do `1–9`; `1–8` i niezgodny kierunek są fail-closed.
- [x] `19–27 → 1–9` w kierunku malejącym ma trzy strony o kanonicznie rosnących granicach.
- [x] Korpus ma development/calibration/validation/holdout/reference_only; katalogi i zawartość mają fingerprint.
- [x] `wybrane mumie` nie może wejść do metryk grupowania.
- [x] Użyty lokalnie manifest testowy opisuje wskazany przez operatora korpus, bez zaszycia ścieżki w kodzie.

## Test cases

- Pełne strony w obu kierunkach; niepełna strona i konflikty kierunku.
- Zmiana bajtów JPEG-a lub listy katalogów zmienia/odrzuca zamrożony korpus.
- Treasure ma `irregular_or_none`; wszystkie pozostałe nieoznaczone style pozostają jawnie `null` do anotacji, nie są zgadywane.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_configuration.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_configuration.py services/worker/tests/test_v7_configuration.py
```

## Risks / open questions

- Kierunek i style poza Treasure nie są jeszcze oznaczone niezależnie; `null` jest stanem jawnej niewiedzy, nie domyślną ramką.

## Outcome

### Changed

- Dodano czysty kontrakt v7 konfiguracji: domyślny półautomat i kierunek
  rosnący, normalizację numeru/pełnego zakresu, trzy style ramki oraz wynikowy
  katalog `<źródło> cut`. Kierunek porządkuje strony, ale zakresy i przyszłe
  nazwy pozostają zawsze rosnące.
- Dodano wersjonowany manifest corpus-only z rozłącznymi splitami oraz
  fingerprintami bezpośrednich JPEG-ów. Manifest przykładowy nie zawiera
  ścieżki użytkownika; skrypt otrzymuje ją jawnie przez `--corpus-root`.
- Wszystkie style poza Treasure są w lokalnym manifeście jawnie `null`, bo nie
  zostały jeszcze niezależnie opisane; nie przyjęto ich po cichu jako ramki
  domyślnej. `wybrane mumie` ma wyłącznie rolę `reference_only`.

### Verification results

- `pytest`: 17 passed; `ruff` i `mypy`: PASS.
- Zamrożony read-only inwentarz przekazanego korpusu: 3 241 JPEG-ów, manifest
  `604185fbe5d8bbfe071788dd38a9bf6cf764d16561415afcf4e29b70d54ffda9`;
  raport znajduje się lokalnie pod `artifacts/v7-selection/t01-corpus-inventory.json`.

### Not completed

- Nie oznaczono jeszcze rzeczywistych kierunków stron, przycięć góra/dół ani
  stylów poza Treasure. Są to dane anotacyjne T05, nie wnioski z nazw katalogów.
- Audyt Astra rozszerzył kontrakt o blokadę przeetykietowania `wybrane mumie`,
  reparse points/junctions, puste katalogi i jednolity błąd odwróconego zakresu.

### Documentation updates

- Dodano przykład manifestu do `ai_docs/quality/v7-corpus-manifest.local.example.json`.

### Recommended next task

- T02 — lokalizator etykiet i kontrakt dowodu 5 / 3+3, oparty na tym samym
  manifestowym korpusie i bez używania sąsiednich zdjęć jako dowodu.
