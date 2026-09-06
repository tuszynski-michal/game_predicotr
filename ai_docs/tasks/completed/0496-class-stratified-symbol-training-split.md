---
title: Class-stratified symbol training split
status: done
---

# TASK-0496 — Poprawny podział klas w treningu symboli

## Status

`done`

## Goal

Nowe iteracje modelu symboli używają source-disjoint podziału, w którym każda
aktywna klasa ma dowód w train, validation, test i regression albo trening
kończy się kontrolowanym odrzuceniem przed pierwszą epoką.

## Context

Iteracja `e0467571-2e55-4267-9142-d9f45a1387c9` miała 768 próbek i 19 rodzin,
ale hash-based v2 przydzielił do testu jedną rodzinę zawierającą tylko `ARBUZ`
i `SIEDEM`. Model rozpoznał 10/10 próbek, lecz sześć klas bez supportu zostało
policzonych jako recall 0 i kandydat został odrzucony z macro recall 0,25.

## Dependencies / entry conditions

- Historyczne konfiguracje `source-family-balanced-split-v2` i gate v1 muszą
  pozostać odtwarzalne.
- Bieżąca kohorta ma co najmniej dziewięć rodzin dla każdej z ośmiu klas.

## Recommended execution

`gpt-6-astra` z poziomem `high`, ponieważ zmiana dotyczy deterministycznego
podziału grupowego, ochrony przed przeciekiem i odtwarzalności treningu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md`

## Scope

- Dodać wersjonowany, deterministyczny podział uwzględniający klasy i rodziny.
- Utrwalać przypisania v3 w konfiguracji joba i dziedziczyć wyłącznie wcześniejsze
  przypisania tej samej polityki.
- Zatrzymywać nową iterację przed treningiem, jeśli dowolna klasa nie ma
  niezależnego pokrycia w wymaganym splicie.
- Pokazać brak pokrycia jako twardą bramkę datasetu, nie advisory.

## Out of scope

- Zmiana etykiet, kohort, aktywnego modelu lub istniejącego odrzuconego kandydata.
- Łączenie rodzin źródłowych pomiędzy splitami.
- Zmiana architektury CNN, progów jakości modelu i danych użytkownika.

## Acceptance criteria

- [x] Przypadek 19 rodzin i ośmiu klas daje każdą klasę w czterech splitach.
- [x] Żadna rodzina źródłowa nie występuje w dwóch splitach.
- [x] Brak czterech niezależnych rodzin dla klasy zatrzymuje pracę przed epoką 1.
- [x] Retry historycznej iteracji v2 zachowuje jej przypisania i zachowanie.
- [x] Nowa iteracja na tej samej kohorcie otrzymuje inny fingerprint v3.

## Technical notes

Nowa polityka `source-family-class-stratified-split-v3` przydziela całe rodziny.
Najpierw deterministycznie zapewnia pokrycie klas w każdym splicie, chroniąc
rzadkie klasy, następnie uzupełnia docelowe liczby rodzin według proporcji.
Istniejące przypisania v3 są niezmienne. Brak wykonalnego podziału daje stabilne
`SYMBOL_TRAINING_EVALUATION_CLASS_COVERAGE_INSUFFICIENT` przed treningiem.

## Expected files

- `services/worker/src/game_predictor_worker/symbols/training_dataset.py`
- `services/worker/src/game_predictor_worker/symbols/training_job.py`
- `services/api/src/game_predictor_api/storage/symbol_model_iteration_repository.py`
- testy API i workera oraz dokumentacja właścicielska.

## Test cases

- Regresja bieżącej dystrybucji: 19 rodzin, wszystkie klasy w train/eval.
- Klasa obecna w trzech rodzinach: kontrolowane odrzucenie przed epoką.
- Determinizm, stabilność po rozszerzeniu kohorty i brak source leakage.
- Historyczny v2 zachowuje dotychczasowy wynik 4/1/1/1 dla małej kohorty.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_symbol_training_job.py services/worker/tests/test_verified_training_dataset.py services/api/tests/test_symbol_model_iteration_storage.py
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/symbols services/api/src/game_predictor_api/storage/symbol_model_iteration_repository.py services/worker/tests/test_symbol_training_job.py services/api/tests/test_symbol_model_iteration_storage.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/symbols services/api/src/game_predictor_api/storage/symbol_model_iteration_repository.py
npm run format:check
```

## Risks / open questions

- Zamrożonego odrzuconego kandydata nie wolno aktywować po zmianie metryk; nowy
  podział wymaga nowej iteracji trenowanej od początku.

## Outcome

Dodano deterministyczny split v3 uwzględniający klasy i pełne rodziny źródłowe.
Repozytorium utrwala jego przypisania w konfiguracji nowej iteracji, dataset
blokuje brak przypisania, a manifest oraz worker zatrzymują brak pokrycia klasy
przed treningiem. Historyczny builder v2 i gate kandydata pozostały niezmienne.

Regresja odpowiadająca bieżącej grze rozdziela 19 rodzin jako 12/3/2/2 i
zapewnia wszystkie osiem klas w każdym splicie. Testy datasetu, joba, storage i
candidate gate przeszły. Skoncentrowany mypy nie zgłasza błędów w tym pionie;
pełne śledzenie importów ujawnia wcześniejsze błędy w modułach geometrii i API,
które pozostają poza zakresem zadania.
