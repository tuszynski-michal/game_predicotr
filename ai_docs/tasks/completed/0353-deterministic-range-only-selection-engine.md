# TASK-0353 — Deterministyczny silnik wyboru wyłącznie po zakresie

Status: `done`

## Cel

Dodać trwały, strumieniowy silnik O(N), który grupuje wyłącznie dokładne lokalne
dowody zakresu, chroni przed izolowanym OCR i wybiera reprezentanta najbliższego
środkowi grupy bez oceny wyglądu plansz.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `.tmp/TASK-0350-0357-semi-automatic-selection-plan.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Zakres

- accumulator grup `EXACT_RANGE` z obsługą A/B/A, A/B/B, singletonów i
  skalibrowanych przerw bez dowodu;
- deterministyczny wybór dokładnego dowodu najbliższego środkowi grupy;
- JSONL obserwacji i grup, atomowy checkpoint i raport końcowy;
- trwałe zapisy wyników zakresów i wznowienie bez ponownego OCR zakończonych
  źródeł;
- handler `SEMI_AUTOMATIC_IMAGE_SELECTION` w istniejącym lane selekcji;
- pauza, wznowienie, anulowanie oraz diagnostyka konfliktów i duplikatów.

## Poza zakresem

- lokalny writer i manifest outputu (TASK-0354);
- UI (TASK-0355+);
- scoring geometrii, ostrości, ekspozycji, okluzji lub symboli;
- wnioskowanie zakresu z sąsiednich grup;
- zmiany schematu PostgreSQL.

## Invarianty

- OCR jest wykonywany co najwyżej raz na JPEG w jednym runie;
- tylko `EXACT_RANGE` dla zakresu grupy może zostać wybrany;
- brak dowodu może rozszerzyć granice grupy, ale nigdy nie staje się kandydatem;
- pierwszy zapisany wybór oczekiwanego zakresu jest chroniony przed późniejszym
  duplikatem;
- kolejność i wynik są deterministyczne po restarcie;
- geometria, cropper i symbol inference nie są dostępne przez port silnika.

## Weryfikacja

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_semi_automatic_selection_engine.py -q
.venv\Scripts\python.exe -m pytest services/worker/tests/test_worker_cli.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_semi_automatic_selection_engine.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection
```

## Outcome

- Dodano strumieniowy `RangeGroupingAccumulator` z polityką A/B/A, A/B/B,
  singletonów, duplikatów, kolejności niemonotonicznej i skalibrowanej przerwy
  `160` bez proof.
- Selektor wybiera wyłącznie `EXACT_RANGE` najbliższy środkowi grupy, ze
  stabilnymi tie-breakami; geometria, jakość obrazu i symbole nie są wejściami.
- Handler istniejącego lane selekcji weryfikuje niezmienność stagingu, wykonuje
  OCR raz na JPEG i zapisuje `observations.jsonl`, `groups.jsonl`, atomowy
  checkpoint oraz checksummowany raport.
- Pauza/restart wznawiają zatwierdzony prefiks bez powtórnego OCR. Fingerprint
  rzeczywiście załadowanego recognizera jest przypięty przy pierwszym
  checkpointcie i jego zmiana blokuje wznowienie.
- Pierwszy wybór expected range jest trwały; duplikat nie zastępuje źródła.
  Zakończona analiza przechodzi do `waiting_for_review`, pozostawiając lokalny
  writer dla TASK-0354.
- Konflikt utraty lease'u zachowuje stabilny kod `JOB_LEASE_LOST` i nie jest
  błędnie mapowany na problem checkpointu.
- Weryfikacja: 52 testy półautomatycznego pionu przeszły; skoncentrowany Ruff
  i format nowych modułów przeszły; pełny repozytoryjny mypy został przerwany
  zgodnie z limitem po 60 s bez wyniku, natomiast skoncentrowany mypy nowych
  modułów przeszedł.
