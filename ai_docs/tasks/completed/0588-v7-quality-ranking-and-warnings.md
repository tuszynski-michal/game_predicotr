---
title: TASK-0588 — V7 quality ranking and warnings
status: done
last_updated: 2026-09-21
---

# TASK-0588 — Ocena jakości, ranking i ostrzeżenia V7

## Status

`done`

## Goal

Udostępnić czysty, deterministyczny ranking wyłącznie lokalnie udowodnionych
kandydatów V7, z oceną najgorszej z dziewięciu plansz i ostrzeżeniami jakości.

## Context

T02 potwierdza numerację lokalnym OCR, a T03 tworzy occurrence i finalizuje je
po EOF. Teraz potrzebna jest niezależna od OCR ocena jakości, aby po pełnym
skanie wybrać jeden najlepszy kwalifikowany JPEG zakresu. T04 nie może zmienić
przypisania numeru, dodać dowodu z sąsiedniego kadru ani zapisywać JPEG-a.

## Dependencies / entry conditions

- T00–T03 są ukończone. T05 nadal jest właścicielem pomiaru i kalibracji
  progów obrazu; T04 przyjmuje już zmierzone, wersjonowane klasy jakości.
- Do rankingu wchodzą tylko `V7ProvenSource` z ukończonych occurrence. Dobry
  wizualnie kadr bez własnego proof nie może zostać automatycznym kandydatem.
- V1 automatu dotyczy pełnej strony 3×3. Ręczne strony 1–8 należą do T09.

## Recommended execution

`gpt-6-astra` z reasoning `high`; wymagany niezależny review
`gpt-6-astra medium` przed commitem. Eskalować, gdy potrzebny byłby nowy OCR,
próg kalibracyjny, API, baza albo zapis JPEG-a — nie należą do T04.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0587-v7-occurrences-cursors-and-finalization.md`
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_occurrences.py`

## Scope

- Typy jakości dziewięciu plansz, agregacja według najgorszej planszy,
  ostrożna obsługa `unknown`, warningi oraz deterministyczny ranking globalny
  po EOF.
- Walidacja, że candidate ma własny proof przypięty do occurrence, i testy
  kontraktowych porównań jakości.

## Out of scope

- Dekodowanie JPEG, lokalizacja plansz i etykiet, kalibracja progów, OCR,
  checkpoint, manifest źródeł, baza/API/UI, output writer i ręczne decyzje.

## Acceptance criteria

- [x] Kadr pełny z lekkim rozmyciem, lecz czytelny, wygrywa z ostrym kadrem z
  potwierdzoną utratą symboli; pełny nieczytelny przegrywa z czytelnym kadrem
  z niewielkim, potwierdzonym przycięciem.
- [x] Agregacja nie ukrywa jednej planszy z istotną utratą symboli w średniej
  dobrych plansz; `unknown` nie jest traktowane jak brak utraty albo pełna
  widoczność.
- [x] Przycięcie od góry albo dołu zawsze jest warningiem. Boczne przycięcie
  pełnej strony zachowuje nazwę całego zakresu i ma stosowny warning jakości.
- [x] Mocny proof i poprawny proof 3+3 przechodzą tę samą bramkę dopuszczenia;
  jakość, a nie rodzaj proof, rozstrzyga ich dalszą kolejność.
- [x] Ranking wszystkich occurrence tego samego zakresu po EOF może wybrać
  późniejsze A, ale w razie remisu używa środka occurrence, potem source index
  i source ID.

## Technical notes

- Nowy moduł `v7_quality.py` będzie czysty: wejściem są opisane klasy jakości
  każdej pozycji 3×3, `V7Occurrence` oraz `V7ProvenSource`; nie przyjmuje
  obrazu, nazwy pliku ani oczekiwanego następnego zakresu.
- T05 mapuje pomiary obrazu na klasy; T04 nie ustala wartości numerycznych.
  Kolejność ryzyka jest jawna i leksykograficzna: utrata symboli najgorszej
  planszy, czytelność najgorszej planszy, widoczność, rozmycie, zasłonięcie,
  dekoracja zależna od stylu, odległość od środka occurrence, stabilny remis.
- Potwierdzona nieczytelność dowolnej planszy jest jedyną bramką poprzedzającą
  tę kolejność: pełny, lecz nieczytelny kadr przegrywa z czytelnym kadrem o
  potwierdzonej niewielkiej utracie. Lekko rozmyty, nadal czytelny kadr nie
  przechodzi przez tę bramkę i nadal wygrywa z utratą symboli.
- Klasa `unknown` jest gorsza od potwierdzonej małej utraty/akceptowalnej
  czytelności, ale lepsza od potwierdzonej istotnej utraty/nieczytelności.
  Pozwala to zachować najlepszy dostępny wynik bez udawania, że brak pomiaru
  oznacza jakość zerowego ryzyka.
- Dekoracja nie może kompensować utraty symboli. Dla
  `irregular_or_none` nieoceniana dekoracja jest neutralna wyłącznie w jej
  własnym stylu; nie tworzy dowodu pełnej widoczności.
- Wyłącznie `V7ProvenSource` powiązany identycznym source ID i source index
  z occurrence jest kandydatem. Brak pasującej próbki jakości jest błędem
  finalizacji, nie podstawą do wyboru innego źródła occurrence.
- Wyniki to propozycje w pamięci; T07 utrwali ranking/checkpoint, T08/T09
  wykonają zapisy, a T10 pokaże warningi i sąsiadów.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_quality.py`.
- Nowe: `services/worker/tests/test_v7_quality.py`.
- Istniejące: `TEMP PLAN V7.md`, `CURRENT_STATE.md`, `DECISION_LOG.md` i
  outcome taska.

## Test cases

- Dziewięć dobrych plansz poza jedną z istotną utratą symboli → kandydat
  przegrywa z równiej dobrym kadrem bez tej utraty.
- Pełny/lekko rozmyty czytelny kontra ostry/bocznie przycięty oraz pełny/
  nieczytelny kontra czytelny/z niewielkim przycięciem.
- `unknown` widoczności kontra potwierdzona mała utrata, top/bottom i boczne
  warningi, style ramki oraz mocny proof kontra 3+3.
- A1 słaby → B → A2 dobry → EOF wybiera A2; candidate bez proofu, niezgodny
  source ID/index i próba rankingu przed EOF są odrzucane.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_quality.py services/worker/tests/test_v7_occurrences.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_quality.py services/worker/tests/test_v7_quality.py
.\.venv\Scripts\python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/semi_automatic_selection/v7_quality.py
```

## Risks / open questions

- T04 definiuje kolejność porównania, nie mierzalne granice ostrości i
  widoczności. Jeżeli T05 pomiar wskaże konieczność zmiany klas albo progu
  jakości, będzie to jawna aktualizacja polityki, a nie cicha zmiana rankingu.

## Outcome

- Dodano `v7_quality.py`: typy jakości planszy 3×3, agregację najgorszego
  przypadku, deterministyczny ranking i warningi jakości bez dekodowania
  obrazu, OCR ani zapisu.
- Po bramce dowodu strong i 3+3 są równorzędne. Możliwy jest wybór pierwszego
  źródła potwierdzenia 3+3, ponieważ T04 wiąże je z przypiętym source ID/index
  odtworzonym przez tracker po restarcie.
- Utrata symboli pozostaje pierwszym zwykłym kryterium. Potwierdzona
  nieczytelność jest celową bramką bezpieczeństwa: pełny nieczytelny kadr
  przegrywa z czytelnym o małej, mierzonej utracie. Nieznana widoczność nie
  może być zapisana jako brak albo mała utrata.
- Weryfikacja: 35 testów T02–T04, Ruff i mypy zmienionych modułów — PASS.
  Self-audyt dodał walidację unknown i warning widoczności. Astra Medium
  zatwierdziła kod oraz testy remisów i JSON round-trip checkpointu 3+3.
