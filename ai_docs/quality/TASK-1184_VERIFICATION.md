---
title: TASK-1184 — pełne uczenie i odbiór zawartości
status: active
last_updated: 2026-11-11
---

# TASK-1184 — weryfikacja

## Zakres i potwierdzona przyczyna

Istniejący eksperyment `full-symbol-content-experiment-v1` miał już R0–R3,
ranking A i trwałe4800kroków/7200s. Brakowało przepuszczenia legalnych partial
TRAIN do uczenia punktów: runner wybierał `full_only=True`, a czytnik
`screen+grid` odrzucał te zdjęcia. Ponadto kontrola content export sprawdzała
tylko pierwsze zdjęcie/pierwszą planszę. Nie utworzono drugiego trenera ani ledger.

Nowy adapter wymaga zamrożonego `geometryOnlyTraining` z T2. Partial nie trafia
do forward detektora, BatchNorm ani jego loss; zatwierdzone punkty zachowują
wagę4, dobre przykłady wagę1, unknown15 jest maskowane. Batch zachowuje liczbę
zdjęć; losowanie samych partial zastępuje jeden slot pełnym zdjęciem bez
dodatkowego kroku. Istniejące1200steps/arm, ocena200, rezerwy1500/1500/2100/2100s
i wspólny budżet nie zmieniają się.

Nowe plany przypinają `cropPolicyVersion=full-cell-v2`,
`r3AdmissionPolicy=human-labels-conditional-v1` oraz
`exportEvaluationPolicy=full-a-content-v1`. Stare plany bez pól zachowują
semantykę. Warunkowy R3 zapisuje `skipped_not_ready` i konkretny brak etykiet,
bez kroków lub odnowienia budżetu. Zakończone ramiona są nadal oceniane według A;
niezaliczony A pozostaje propozycją, a dotychczasowe bramki publikacji/automatu
nie są osłabione.

## Pełny A i eksport

`ContentSelectionEvaluator.measure` używa tego samego bazowego modelu, źródeł,
human GT, dopasowania i15produkcyjnych cropów dla Torch oraz ONNX. Każde
rzeczywiste wejście ONNX dostaje surowe porównanie przez istniejący
`parity_verdict`; R3 obejmuje również wyjścia głowicy content. Prócz tolerancji
1e-4 porównywane są wszystkie dyskretne decyzje dopasowania/pól, usable boards,
full-photo correctness, bramka NME każdej gry i kolejność wyboru checkpointu
oraz ramienia. Druga gra/zdjęcie nie może pozostać poza sprawdzeniem.

Nowy `content-runtime-parity-v2.fullA` wiąże dokładny istniejący roster A,
manifesty, historię sześciu ocen i wybory ramion. API weryfikuje pełność i
spójność tego dowodu. Błąd blokuje instalację eksportu i zostawia
`content-evaluation-consistency-failed.json`. Rzeczywisty koszt pełnej kontroli
eksportu wchodzi do preflight i dotychczasowego trwałego budżetu.

## Wyniki testów

| Kontrola | Wynik |
|---|---|
| `test_effective_content_training.py` + `test_content_conditional_r3.py`, pierwsza wersja testu workflow | 10 PASS,73.04s |
| Warunkowy R3 + nowa kontrola preflight/final export + utrata odpowiedzi i odtworzenie | 1 PASS,69.25s |
| Pełny A dwóch gier, realny renderer, druga gra z raw błędem lub zmianą decyzji mimo raw PASS; walidacja API dowodu; istniejące partial A | 14 PASS,14.05s |
| Istniejące `test_grid_content_experiment.py`, `test_grid_content_mixed_batch.py`, `test_grid_visibility_contract.py` | 36 PASS,22.88s;2 ostrzeżenia przestarzałego eksportera TorchScript |
| Istniejące API `test_grid_content_experiment_evidence.py` | 16 PASS |
| Mypy dziewięciu modułów, `--follow-imports=silent`; końcowy eksport/runner po rozszerzeniu preflight | PASS9modułów + PASS2modułów |
| Ruff zmienionych modułów i testów | PASS |
| Końcowa grupa nowych testów full A, dowodów API, mixed TRAIN i pomiaru pełnego kosztu eksportu | 19 PASS,11.46s |
| Realny R3 ONNX export/install/cold replay po utracie odpowiedzi | 1 PASS,65.84s;3 ostrzeżenia bibliotek eksportera |
| Legacy wymagane R3 z gotowymi etykietami, pełne4800kroków fixture | 1 PASS,100.24s |

Testy z małymi fixture CPU dowodzą integracji kodu, niezależności splitu i
trwałości; nie są treningiem ani kwalifikacją danych operatora. W teście
pełnego A wykonanie grafu ma jawny adapter fixture, natomiast źródła, ludzka
referencja, dopasowanie i produkcyjne rastry są rzeczywiste. Osobny istniejący
test ONNX sprawdza rzeczywiste eksportowane24/15wyjść.

## Polecenia i ograniczenia środowiska

W katalogu worktree używano `D:/game_predicotr/.venv/Scripts/python.exe` i
bezpośrednio `-m pytest <wskazane wyżej ścieżki> -q --tb=short
--basetemp=D:/game_predicotr/.tmp/t3-<unikalny-sufiks>`. Każde wywołanie
uruchamia `subprocess.run(..., timeout=120)`. Typecheck: `-m mypy
--follow-imports=silent` na dziewięciu modułach T3. Format/lint: `-m ruff format`
i `-m ruff check` na modułach i testach T3.

Pierwszy zbiorczy przebieg przekroczył120s i został przerwany przez limit;
podzielono go na mniejsze grupy. Również dwie parametryzacje długiego legacy
R3 przekroczyły wspólny120s limit; wymagane pełne R3 powtórzono osobno z PASS.
Domyślny TEMP był niezapisywalny, a długi
worktree TEMP przekraczał Windows MAX_PATH w istniejącym writerze. Powtórzenie
na krótkiej ścieżce w repo rozwiązało ograniczenie środowiska. Istniejący test
eksportu miał porównanie list zawierających tablice NumPy operatorem`==`;
zmieniono je na dokładne porównanie źródeł, wag i `assert_array_equal`, bez
osłabienia sprawdzanej równości.

Preflight nowych planów mierzy zarówno legacy kontrolę ośmiu cropów, oba
rzeczywiste warianty wejścia, jak i pełny A wszystkich gier. Właśnie ta suma
stanowi `exportSeconds` w rezerwie przed treningiem. Final sprawdza bieżącą
rezerwę oraz limit ramienia i globalnego procesu przed kolejnymi zdjęciami.
Content recovery nie powtarza inference: weryfikuje niezmienne bytes grafów,
pełny proof, roster i historię. Nie przenosi pomiaru czasu z13zdjęć T1 na
content pipeline i nie zakłada stałego czasu dla wielu gier.

## Niezależny przegląd odziedziczonego kodu (claude-opus-5-5/high)

Wykonawca zmienił się na polecenie operatora (limit Codex). Przed integracją
przeczytano wszystkie zmiany T3 (Codex/Astra): `grid_cohort_dataset`,
`grid_training_data`, `grid_training`, `grid_content_experiment_run/data/export`,
`training_core/grid_content_experiment`, oba moduły `grid_content_consistency`,
`grid_training_child`, API `grid_content_experiment_evidence` i piny w
`grid_correction_learning`. To przegląd wykonawcy przejmującego, nie niezależny audyt.

- Brak znalezisk P0/P1. Partial nie trafia do forward/BatchNorm/straty detektora
  (maska przed inferencją); nieopisane plansze nie tworzą cropów; slot pełnego
  zdjęcia zastępuje wyłącznie losowanie bez pełnego zdjęcia, deterministycznie.
- Stare plany: v4 content wcześniej odrzucał każde nie-screenEligible TRAIN
  (`GRID_TRAINING_FULL_DATA_DRIFT`), więc nowa ścieżka bez partial daje te same
  batch i maski; `measurementSha256` pochodzi z ludzkiej referencji, nie z kandydata.
- Warunkowe R3: `skipped_not_ready` tylko po ukończonych R0–R2 i niezaliczonym R2;
  brak kroków i budżetu; zmiana gotowości po pominięciu kończy się błędem.
  Wybór zwycięzcy bez zaliczonego A pozostaje propozycją (istniejąca ścieżka).
- P2 (bez zmian): czas weryfikacji eksportu jest liczony zegarem ramienia i
  księgowany przy finalize; przerwanie w trakcie nie zapisuje go wcześniej
  (istniejący model księgowania). Dowód pełnego A nie wiąże każdej pozycji
  historii z ledgerem poza wybranym krokiem i krokami 200–1200.

## Wyniki na delivery po integracji T2 R1

Pliki T3 przeniesiono do `effective-grid-delivery` (pliki własne bajtowo równe
zapisanym SHA, łatka wspólna `task1184-shared.patch` SHA 18ee4de3… nałożona bez
konfliktów) na commit T2 `e4bba0bd`. Każde polecenie pod `timeout 120`.

| Kontrola | Wynik |
|---|---|
| Nowe testy T3 + dowody API (`test_effective_content_training`, `test_content_full_a_*`, API evidence) | 35 PASS, 12.80s |
| Istniejące content experiment/mixed batch/visibility/export | 37 PASS, 74.97s |
| Warunkowe R3 z utratą odpowiedzi | 3 PASS, 59.83s |
| Workflow (bez legacy R3) | 6 PASS, 118.06s (blisko limitu) |
| Legacy wymagane R3, dwie parametryzacje osobno | 1 PASS 61.97s; 1 PASS 91.80s |
| Powiązane testy workera (child, consistency, handler, recovery, R3 readiness, rescue proof) | 79 PASS + 27 PASS |
| Ruff format/check 18 plików | PASS |
| mypy strict (normalne importy) 12 plików produkcyjnych | 0 błędów w nich; 14 zastanych w 8 nietkniętych modułach, identyczne z HEAD |
| Zastane: `test_vision_lab_neural_grid_finetune` 2 FAIL (`NeuralGridEngine.detect`) | identyczne na czystym HEAD |

Audyt Codex niewykonany — kontynuacja na polecenie operatora po wyczerpaniu
limitu. To nie jest PASS audytu.

## Porównanie z T3 planu i granice dowodu

- Wersja bazy, checksumy wag, rewizja defaultu i rewizje kohort korzystają z
  istniejących pinów i kontroli aktualności. Kontekst operatora wskazuje
  bazę3ed60010/revision2; T3 nie tworzył żądania treningu ani nie zmieniał jej.
- Full-cell0% jest jawnie przypięte; brak/8% jest odrzucane przed siecią i bankiem.
- Detector+partial geometry, human24/15, ranking wyłącznie A oraz budżet mają
  testy; B pozostaje kalibracją, REG końcowym testem, bez odczytu ich pikseli
  w selekcji A. Caps u=.02/delta=.002 i content-v6 pozostają bez zmian.
- Poprawa modelu i gotowość danych operatora: **niezmierzone**. Brak labels
  nie stanowi preserved/PASS; brak kalibracji automatu nie daje uprawnień.
- Historyczny REVISE run39ddc3a3/1be01f29 pozostaje bez zmian. Nie wykonano
  treningu GPU, migracji operatora, restartu, publikacji/defaultu, merge ani push.
- Zamknięcie/commit po T2 wykonał Claude; audyt Codex niewykonany (waiver operatora).
