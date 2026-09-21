---
title: TASK-0597 — V7 Reels holdout evaluator
status: done
last_updated: 2026-09-21
---

# TASK-0597 — evaluator odbioru holdoutu Reels dla V7

## Status

`done`

## Goal

Dostarczyć odrębny, checksumowany evaluator odbioru wyłącznie dla splitu
`holdout`, tak aby operator mógł ocenić `reels_test` bez używania tego zbioru do
kalibracji lub strojenia V7.

## Context

`evaluate_v7_calibration.py` jest narzędziem T05 i celowo odrzuca `holdout`.
Nie może zostać rozszerzony kosztem tej ochrony. Użytkownik wskazał lokalny
katalog `reels_test` jako nowy, niezależny materiał odbiorowy. T12 pozostaje
zablokowane także dlatego, że runtime V7 nie jest jeszcze wpięty do job handlera;
ten task nie realizuje tej integracji.

## Dependencies / entry conditions

- T00–T12 są ukończone, a API V7 pozostaje `blocked`.
- `reels_test` zawiera 1 287 JPEG-ów; przed tym taskiem sprawdzono jedynie nazwy
  i liczbę plików, bez OCR, lokalizacji ani oglądania obrazów.
- Operator uznał `reels_test` za nowy holdout. Prawda zakresów i warningów nie
  istnieje jeszcze i nie może być wytworzona z predykcji automatu.

## Recommended execution

`gpt-5.6-terra` z reasoning `xhigh`; po self-audycie wymagany niezależny review
`gpt-6-astra medium`. Eskalować, gdy potrzebne byłoby obniżenie progów,
wykorzystanie holdoutu w kalibracji, aktywacja API albo zapis JPEG-a.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/quality/V7_T12_ACCEPTANCE.md`
- `ai_docs/tasks/completed/0589-v7-calibration-and-acceptance-metrics.md`
- `ai_docs/tasks/completed/0596-v7-holdout-acceptance-and-release-gate.md`

## Scope

- Dodać czysty kontrakt metryk T12 przyjmujący wyłącznie truth, niezależne
  obserwacje zakresu/cropu każdego źródła oraz predykcje ze splitu `holdout`,
  bez zmiany kontraktu T05.
- Dodać read-only skrypt, który wiąże pełny manifest, zamrożony inventory,
  zaliczoną kalibrację, ręczny truth i zamrożoną predykcję przez fingerprinty i
  SHA źródeł.
- Udostępnić przykładowe lokalne pliki wejściowe dla operatora, bez ścieżki
  zewnętrznego katalogu w kodzie wersjonowanym.
- Utworzyć lokalny manifest i inventory dla `reels_test` wyłącznie pod
  `.runtime`; nie dodawać ich do Git.

## Out of scope

- OCR, lokalizacja, tuning, ręczne oznaczanie w imieniu operatora, uruchomienie
  joba V7, zapis do katalogu `cut`, aktywacja API/UI i integracja z handlerem.
- Zmiana `evaluate_v7_calibration.py` tak, aby pozwalał na holdout.

## Acceptance criteria

- [x] T12 evaluator odrzuca brak lub zmianę manifestu, inventory, SHA źródła,
  kalibracji, truthu albo snapshotu predykcji.
- [x] Akceptuje wyłącznie jeden jawnie wskazany case `holdout`; kalibracja musi
  pochodzić z tego samego manifestu i mieć status `passed`.
- [x] Truth i predykcja mają identyczne case IDs, każdy truth ma split `holdout`,
  a predykcja nie może zastąpić nieobecnego truthu ani wskazać źródła bez
  niezależnej obserwacji jego zakresu i cropu.
- [x] Pusty mianownik pozostaje `not_evaluable`; raport nigdy nie zmienia
  `productionActivation` na stan inny niż `blocked`.
- [x] T05 nadal odrzuca holdout, a test regresyjny to potwierdza.
- [x] Nie ma procesu OCR, podglądu zdjęć, outputu JPEG ani zmiany API.

## Technical notes

- Nowa funkcja domenowa `evaluate_v7_holdout_acceptance` ma użyć tych samych
  progów T05, lecz walidować truth `HOLDOUT` oraz niezależną obserwację
  rzeczywistego zakresu i cropu każdego źródła. Poprawny zakres wymaga zgodności
  deklaracji automatu z prawdą wybranego JPEG-a. Crop/warning są mierzone tylko
  dla wybranego JPEG-a; brak wyboru nie ma mianownika warningu i nie może
  emitować warningu. Obecne `evaluate_v7_acceptance` zachowuje kontrakt T05.
- Skrypt ma przyjąć osobno: manifest, inventory, raport kalibracji, truth,
  snapshot predykcji i output. Weryfikuje pełny inventory przed odczytem SHA
  źródeł holdoutu. Nie uruchamia V7 ani OCR.
- Snapshot predykcji zawiera fingerprint manifestu, inventory, kalibracji i
  algorytmu oraz rzeczywiście przewidziany zakres i wybrane źródło dla każdego
  ręcznie oznaczonego przypadku. Evaluator sam wyprowadza `correct`, `incorrect`
  lub `not_selected`; plik snapshotu nie może zadeklarować tych wyników.
  Ponowne przetworzenie lub ręczna korekta nie zmienia istniejącego snapshotu.
- Raport zawiera tylko metadane i wyniki bramki. `productionActivation` pozostaje
  `blocked`, ponieważ świadoma aktywacja jest późniejszą decyzją po T13b i T12.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py`.
- Nowe: `scripts/evaluate_v7_holdout.py`.
- Nowe: `services/worker/tests/test_evaluate_v7_holdout_script.py`.
- Istniejące: `services/worker/tests/test_v7_calibration.py`.
- Nowe: `ai_docs/quality/v7-holdout-truth.example.json`.
- Nowe: `ai_docs/quality/v7-holdout-predictions.example.json`.
- Istniejące: `TEMP PLAN V7.md`, `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/process/DECISION_LOG.md`.

## Test cases

- Zgodny manifest, inventory, kalibracja, jeden truth i jedna predykcja holdout
  → mierzalny raport pozostający `blocked`.
- Pusty truth/predykcja → `not_evaluable`, bez sukcesu.
- Case validation albo calibration, zły SHA, inny fingerprint, brak kalibracji,
  niezaliczona kalibracja, różne case IDs lub drift inventory → błąd fail-closed.
- Aktualny evaluator T05 z truth holdout → nadal błąd.
- Snapshot deklaruje `1–9`, ale wybiera ręcznie oznaczone źródło `10–18` →
  błędny automatyczny zakres, niezależnie od jakości reprezentanta.
- Ten sam case wybiera pełne źródło A albo przycięte od góry źródło B → mianownik
  i recall warningu pochodzą z faktycznie wybranego źródła, nie z case'u.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, maks. 120 s na krok
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_calibration.py services/worker/tests/test_evaluate_v7_calibration_script.py services/worker/tests/test_evaluate_v7_holdout_script.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py services/worker/tests/test_v7_calibration.py services/worker/tests/test_evaluate_v7_holdout_script.py scripts/evaluate_v7_holdout.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py scripts/evaluate_v7_holdout.py
```

## Risks / open questions

- Zakresy, kierunek i ręczny truth `reels_test` pozostają pracą operatora po
  zamrożeniu manifestu. Nie można ich bezpiecznie wyprowadzić z nazw plików.
- Sam evaluator nie odblokowuje V7: nadal konieczna jest integracja handlera,
  realna kalibracja i niezależny odbiór.

## Outcome

Zrealizowano osobny evaluator T12 i zamrożono lokalny korpus `reels_test` jako
wyłączny holdout. Inventory obejmuje 1 287 JPEG-ów; manifest, inventory i
checksumy są lokalne pod `.runtime`, bez wersjonowania ścieżki zewnętrznego
katalogu. `rells_big` pozostał poza holdoutem zgodnie z D-404.

`evaluate_v7_holdout.py` fail-closed wiąże zamrożony manifest i inventory,
zaliczoną kalibrację, ręczny truth, snapshot i SHA dowodów oraz reprezentantów.
Sprawdza inventory przed i po kontroli źródeł. Snapshot przechowuje tylko surowe
obserwacje; evaluator sam wyprowadza wynik zakresu i reprezentanta. Poprawny
zakres wymaga zgodności snapshotu z niezależnie opisanym zakresem wybranego
JPEG-a, a crop/warning są rozliczane per wybrane źródło. Nie akceptuje legacy
pól verdictu. Raport ma zapis idempotentny bez nadpisania i zawsze zwraca
`productionActivation=blocked`.

Self-audyt wykrył, że pierwsza wersja formatu mogłaby dopuścić deklarowanie
wyników przez snapshot; usunięto to z kontraktu i dodano regresję. Astra Medium
wykryła możliwość przekazania truthu holdoutu do publicznego evaluatora T05;
dodano kontrolę typów na granicach obu evaluatorów oraz test regresyjny. Końcowy
audyt wykrył też brak związania deklarowanego zakresu i warningu z wybranym
JPEG-em; dodano globalny katalog obserwacji źródeł oraz regresje źródła innej
grupy i wyboru pełny/przycięty.

Weryfikacja: 24 testy worker/skryptu przeszły; Ruff i Mypy z
`--follow-imports=skip` przeszły. Zweryfikowano także pomoc CLI oraz składnię
obu przykładów JSON. Nie uruchamiano OCR, joba, API ani zapisu JPEG-a.

Nieukończone i świadomie poza zakresem: ręczna kalibracja, ręczny truth
holdoutu, snapshot z produkcyjnego handlera i integracja T13b. Następny task
może podłączyć V7 do handlera przy nadal twardo zablokowanym API; dopiero potem
ponowny T12 może dostarczyć materiał do decyzji aktywacyjnej.
