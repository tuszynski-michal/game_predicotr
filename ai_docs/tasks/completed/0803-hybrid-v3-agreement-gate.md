---
title: TASK-0803 — hybrid_v3: bramka zgodności silnika produkcyjnego i neural_grid
status: done
last_updated: 2026-10-02
---

# TASK-0803 — hybrid_v3: bramka zgodności dwóch silników

## Status

`done`

## Goal

Silnik `hybrid_v3` pod kontraktem `GeometryEngine` łączy siatki odniesienia
(silnik produkcyjny) z siatkami `neural_grid`: plansza jest „pewna” tylko
przy zgodności obu, każda inna dostaje `needs_review` z jawnym powodem;
progi są skalibrowane na zbiorze development i opisane krzywą
pokrycie–błąd.

## Context

Etap V3-B planu (D-461: wynik tylko jako review/shadow). Run 1 `neural_grid`
(preset A, `43933ac8…e2e6`, eksport `exports\2cd19738…-round3`): na
development 92,3% zdjęć kompletnych i poprawnych, 100% plansz wykrytych, 0
fałszywych; z 51 plansz „błędnych” większość to błędy etykiet S (etykieta
przesunięta albo przechylona), co potwierdził przegląd wizualny. Wniosek dla
bramki: niezgodność sieci z odniesieniem jest sygnałem do przeglądu, a nie
dowodem błędu sieci.

## Dependencies / entry conditions

- TASK-0802 w repo (`v1.7.158`+): `neural_grid_inference.py` zwraca dla
  planszy węzły, resztę dopasowania siatki i liczbę inlierów (`analyse()`).
- Snapshot v2 `production-geometry-snapshots\286f2e37…df59`; role `training`
  i `development`. Rola `gold` i holdouty D-456 nietknięte (TASK-0804).
- Fakt: w snapshocie etykieta planszy poziomu B **jest** wynikiem silnika
  produkcyjnego; dla poziomu S etykieta jest korektą, a pierwotny wynik
  silnika produkcyjnego nie jest zapisany. Uruchomienie silnika
  produkcyjnego w labie nie jest dostępne (lab nie importuje kodu
  aplikacji; D-447).
- Run 2 treningu może trwać równolegle na GPU — to zadanie używa wyłącznie
  ONNX na CPU i nie uruchamia treningu.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Reguły bramki i kalibracja bez
przecieku z development do oceny końcowej. Audyt zawieszony decyzją
operatora (2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/delivery/GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md` (etap V3-B,
  błędy i przypadki brzegowe)
- `ai_docs/process/DECISION_LOG.md` (D-461, D-483, D-484, D-485)
- `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`
- `ai_docs/tasks/0802-neural-grid-whole-screen-network.md`

## Scope

- Czysta logika bramki (porównanie dwóch zbiorów siatek jednego zdjęcia) i
  silnik `hybrid_v3` w pakiecie labu; odniesienie jest wejściem
  („reference grids”), nie wywołaniem silnika produkcyjnego.
- Kalibracja progów na development, krzywa pokrycie–błąd, raport.
- Testy; wpis w przewodniku.

## Out of scope

- Trening, zmiany `neural_grid`, odczyt `gold`/holdoutów, integracja z
  aplikacją (TASK-0805), uruchamianie silnika produkcyjnego w labie.

## Acceptance criteria

- [x] Dla każdej planszy zdjęcia wynik albo powód — brak cichych odrzuceń:
      stany `confident` | `needs_review`, powody z zamkniętej listy
      (niezgodność quadów, niezgodność węzłów, plansza tylko z sieci,
      plansza tylko z odniesienia, słabe dopasowanie siatki sieci, plansza
      nieważna).
- [x] Zdjęcie jest `confident` tylko wtedy, gdy wszystkie jego plansze są
      `confident` i liczba plansz obu źródeł jest równa (jednostką jest
      zdjęcie, D-484).
- [x] Reguła wyboru węzłów przy zgodzie zapisana przed pomiarem: węzły
      sieci, gdy reszta dopasowania < próg, inaczej węzły odniesienia.
- [x] Progi (IoU quadów, tolerancja węzłów, reszta dopasowania) wybrane
      wyłącznie na development według zapisanej z góry reguły; raport z
      krzywą pokrycie–błąd i tabelą powodów `needs_review`.
- [x] Miara błędu w raporcie liczona osobno dla B (odniesienie = etykieta,
      więc mierzy się zgodność i pokrycie) i dla S (odniesienie nieznane —
      patrz „Technical notes”), z jasnym opisem, co wynik znaczy.
- [x] Test zamiany silnika bez zmiany odbiorcy; ONNX na CPU.
- [x] Strażnik ról: `gold` i holdouty niedostępne.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

### Odniesienie w labie

`hybrid_v3` przyjmuje siatki odniesienia jako dane wejściowe zdjęcia
(interfejs: lista plansz z 24 węzłami i pozycją), bo w aplikacji (TASK-0805)
odniesieniem będzie wynik silnika produkcyjnego dla tego samego zdjęcia. W
labie:

- zdjęcia B development: odniesienie = etykieta (to jest wynik silnika
  produkcyjnego) — realistyczna symulacja trybu shadow;
- zdjęcia S development: pierwotny wynik silnika nie istnieje w snapshocie.
  Mierz tam bramkę w trybie „sieć kontra etykieta-korekta” i raportuj jako
  osobny, opisany przypadek (ile plansz bramka skierowałaby do przeglądu i
  czy to te same, które metryka uznała za błędne); nie udawaj, że to
  porównanie z silnikiem produkcyjnym. Zaproponuj w raporcie, jak TASK-0804
  albo TASK-0805 ma zdobyć pierwotne wyniki silnika dla zdjęć S (są w bazie
  jako starsze rewizje geometrii źródła — eksporter TASK-0800 może je
  dopisać), bez wykonywania tego.

### Kalibracja

Reguła wyboru progów zapisana przed pomiarem: najwyższe pokrycie zdjęć
`confident` przy warunku, że wśród plansz `confident` odsetek błędnych
względem etykiety nie przekracza 0,5% na development (dla B i S osobno
raportowane). Siatka progów skończona i zapisana (np. IoU 0,80–0,95, węzły
0,005–0,02 przekątnej, reszta dopasowania 3 poziomy). Wynik: wybrane progi,
krzywa, tabela. Development jest tu zbiorem kalibracyjnym — raport ma to
mówić wprost; niezależny pomiar należy do TASK-0804.

### Niedozwolone skróty

- Plansza tylko z sieci nigdy nie jest `confident`.
- Nie zakładaj 9 plansz.
- Nie zmieniaj metryk D-483 ani kodu `neural_grid`.

## Expected files

- Nowe (proponowane) w `vision_lab/`: `hybrid_v3_gate.py`,
  `hybrid_v3_engine.py`, skrypt kalibracji w `scripts/` albo podkomenda
  `neural_grid_runs`, testy, raport
  `ai_docs/quality/GRID_V3_HYBRID_GATE_20261002.md`.

## Test cases

- Zgodne siatki → `confident`; quad przesunięty o kolumnę → `needs_review`
  z powodem niezgodności; plansza tylko z sieci; plansza tylko z
  odniesienia; słaba reszta dopasowania; różna liczba plansz → zdjęcie
  `needs_review`; determinizm kalibracji.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "hybrid_v3 or neural_grid or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Limit 120 s na testy; kalibracja na 600 zdjęciach (ONNX CPU, ok. 0,2 s na
zdjęcie) do 600 s.

## Risks / open questions

- Bez pierwotnych wyników silnika dla zdjęć S bramka jest zmierzona
  realistycznie tylko na B, gdzie niezgodności prawie nie ma.

## Outcome

Stan na 2026-10-02 (wykonawca claude-opus-5-5, worktree `grid-engine-v3`, bez
commita — commit, `CURRENT_STATE.md`, ewentualny wpis `DECISION_LOG.md` i
przeniesienie taska należą do orkiestratora). Wszystkie kryteria poza
„Osobny commit, `Outcome`, `CURRENT_STATE.md`” spełnione.

### Changed

- Nowe w `services/worker/src/game_predictor_worker/vision_lab/`:
  - `hybrid_v3_gate.py` — czysta bramka (`compare` bez progów: parowanie
    węgierskie po IoU quadów ≥ 0,5, błędy węzłów, poprawność strukturalna;
    `decide` z progami; `gate_photo`), zamknięte listy powodów planszy
    (`HYBRID_V3_QUAD_DISAGREEMENT`, `_NODE_DISAGREEMENT`, `_NETWORK_ONLY`,
    `_REFERENCE_ONLY`, `_NETWORK_FIT_WEAK`, `_BOARD_INVALID`) i zdjęcia
    (`_BOARD_COUNT_MISMATCH`, `_BOARD_NEEDS_REVIEW`, `_NO_BOARDS`);
  - `hybrid_v3_engine.py` — `HybridV3Engine` pod `GeometryEngine`; odniesienie
    jako `ReferenceSource` (wejście zdjęcia), adapter `reference_from_engine`
    dla dowolnego silnika labu, `network_boards` z `BoardDetection`;
    `RUN1_DEVELOPMENT_THRESHOLDS` (0,90; 0,04; 0,005);
  - `hybrid_v3_calibration.py` — siatka 84 progów i reguła wyboru zapisane
    przed pomiarem, wczytanie tylko roli `development` za strażnikiem,
    inferencja ONNX CPU z zapisem wyjścia sieci, deterministyczny przegląd
    siatki, routing plansz „błędnych” według metryki, CLI
    (`python -m …hybrid_v3_calibration`).
- Testy: `services/worker/tests/test_vision_lab_hybrid_v3.py` (22 testy, w tym
  parametryzacje).
- Bez zmian w kodzie `neural_grid_*`, metrykach D-483 i `runs.py`.
- Raport `ai_docs/quality/GRID_V3_HYBRID_GATE_20261002.md`; sekcja w
  `ai_docs/guides/VISION_LAB_LOCAL.md`.
- Wyniki kalibracji (poza repo):
  `neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\hybrid-v3-calibration\`
  (`network-development.json`, `calibration.json`).

### Verification results

- `pytest services/worker/tests -k "hybrid_v3 or neural_grid or no_production_storage_imports"`:
  41 passed (w tym test ONNX CPU na eksporcie runu 1 i test zgodności
  `RUN1_DEVELOPMENT_THRESHOLDS` z `calibration.json`).
- `ruff check` i `ruff format --check` nowych plików: czysto. `ruff check services
  scripts`: 1 błąd E501 w niezwiązanym, zacommitowanym
  `services/worker/tests/test_page_geometry_preflight.py:345` (sprzed taska).
- `mypy --strict` nowych modułów: brak błędów w `vision_lab` (zgłoszenia tylko
  w niezwiązanych modułach `images/` z braku `game_predictor_api` w cienkim venv).
- Kalibracja: 600 zdjęć development, ONNX CPU 4 wątki, 146,9 s; wszystkie 84
  punkty spełniają warunek 0,5%; wybór IoU 0,90, węzły 0,04, reszta 0,005:
  90,3% zdjęć `confident` (B 98,0%, S 82,7%), błędne plansze `confident`
  0,13% (B 0, S 7 = 0,27%), zdjęcia `confident` z błędną planszą 1,3%
  (S 2,8%). Z 49 „błędnych” plansz S bramka kieruje 42 do przeglądu, 7
  przepuszcza. Ponowne przeliczenie z zapisanego wyjścia sieci: bajtowo
  identyczny wynik. Szczegóły w raporcie.

### Not completed

- Commit, `CURRENT_STATE.md`, przeniesienie taska (orkiestrator).
- Pomiar bramki względem pierwotnego wyniku silnika produkcyjnego na S —
  dane nie istnieją w snapshocie; propozycja w raporcie (TASK-0804/0805).
- Próg reszty dopasowania praktycznie nieaktywny (reszta sieci ≤ 0,0027);
  lab nie rozstrzyga, które węzły są dokładniejsze.
- Powody „tylko z sieci/odniesienia”, „słabe dopasowanie”, „nieważna” nie
  wystąpiły na developmencie — sprawdzone tylko testami syntetycznymi.
- 7 plansz S przepuszczonych jako `confident` nie było oglądanych.

### Documentation updates

- `ai_docs/quality/GRID_V3_HYBRID_GATE_20261002.md` (reguły, siatka i reguła
  wyboru zapisane przed pomiarem, wynik, krzywa, powody, B/S, znaczenie,
  propozycja pierwotnych wyników S), `ai_docs/guides/VISION_LAB_LOCAL.md`.

### Recommended next task

- Ocenić wizualnie 7 przepuszczonych plansz S; po runach 2/3 powtórzyć
  kalibrację dla wybranego modelu (`--bundle` nowego eksportu); TASK-0804 z
  zamrożonymi progami i, jeśli możliwe, eksporterem pierwotnych wyników S.
