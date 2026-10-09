# TASK-0937 — Pilot wykrywania złotej ramki super symbolu (pomiar)

## Status

`blocked` (narzędzie gotowe; pomiar czeka na migrację 0152 u operatora, przeliczenie serii, co najmniej 5 zdefiniowanych super symboli i etykiety operatora — co najmniej 30 komórek na wariant)

## Goal

Raport mierzący, czy obecne wycinki komórek V3 gry Mumie obejmują złotą
ramkę super symbolu i czy prosta heurystyka koloru wykrywa ją z precyzją i
czułością wystarczającą do automatycznego proponowania super symbolu serii.

## Context

Operator rozważa oznaczanie złotej ramki w weryfikacji symboli i
automatyczne rozpoznawanie. D-489 zostawił margines wycinka jako otwarte
pytanie. Plan: etap S-D (warunkowy).

## Dependencies / entry conditions

- Co najmniej 5 serii ze zdefiniowanym super symbolem (TASK-0934) do doboru
  próby. Prawdą odniesienia są **niezależne ręczne etykiety obecności ramki**
  (`tak` / `nie` / `częściowo`) nadane przez operatora na próbie, osobno od
  klasy symbolu; sam fakt „komórka X w serii” nie jest etykietą.
- Tylko odczyt danych i plików; żadnych zmian w bazie ani modelach.

## Recommended execution

claude-sonnet-5-5 / medium. Skrypt pomiarowy i raport. Eskalacja
niepotrzebna. Audyt: gpt-6.1-sol / medium; do czasu CLI zamiennik claude-opus-5-5 / medium.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/MUMIE_SUPER_GAME_EXECUTION_PLAN_20261008.md`
- `ai_docs/delivery/MUMIE_SYMBOLS_PREMIUM_EXECUTION_PLAN.md` (margines 8 %, kontekst)

## Scope

- Skrypt `scripts/m8_gold_frame_pilot.py` (proponowany, tylko odczyt):
  dla 30–50 komórek z plansz serii (symbol X i inne) pobiera wycinek V3 i
  wycinek z marginesem 8 % z obrazu źródłowego; generuje arkusz
  kontaktowy do ręcznego etykietowania (CSV: komórka, ramka tak/nie/częściowo);
  liczy udział „złotych” pikseli na obwodzie; raportuje precyzję/czułość
  względem ręcznych etykiet, a dodatkowo zgodność etykiet z „komórka X w
  serii” jako kontrolę założenia.
- Raport `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_<data>.md`: widoczność
  ramki w wycinkach V3 (tak/nie/częściowo), wynik heurystyki, rekomendacja:
  cecha komórki + propozycja automatyczna albo rezygnacja.

## Out of scope

- Zmiany w weryfikacji symboli, modelach, wycinkach.

## Acceptance criteria

- [ ] Co najmniej 30 komórek z ręcznymi etykietami ramki (operator, ok.
      10 minut) i raport z liczbami oraz decyzją „dalej / nie”.
- [ ] Skrypt uruchamialny ponownie bez zapisu do bazy.

## Expected files

- Nowe: `scripts/m8_gold_frame_pilot.py`, `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_<data>.md`.

## Verification

```powershell
# katalog worktree, timeout 120 s
.\.venv\Scripts\python.exe scripts/m8_gold_frame_pilot.py --game mumie --limit 50 --out artifacts/gold-frame-pilot
```

## Risks / open questions

- Odblaski i rozmycie mogą ukrywać ramkę; klatki animacji z ramą całej
  planszy mogą zawyżać wynik.

## Outcome

Dostarczone: narzędzie pomiarowe, przepływ etykietowania, testy i szkic raportu. Pomiar końcowy i decyzja „dalej / nie” NIE są wykonane: wymagają etykiet operatora na próbie z prawdziwych serii.

### Changed

- `scripts/m8_gold_frame_pilot.py` (nowy, tylko odczyt bazy i plików; wyniki wyłącznie w `artifacts/gold-frame-pilot/`):
  - `--prepare` dobiera do 50 komórek w trzech grupach (po 1/3): (1) super symbol w planszach serii, (2) inne komórki plansz serii, (3) komórki z plansz poza seriami (`in_series=false`). Dla każdej zapisuje wycinek ciasny (96 px z `sourceQuad`) i wycinek z marginesem 8 %, arkusz `index.html` i `labels.csv`. Arkusz zadaje dwa niezależne pytania na komórkę („Ramka widoczna na wycinku V3 (ciasnym)?” i „…na wycinku z marginesem 8 %?”), każde z przyciskami tak/nie/częściowo, nie pokazuje klasy symbolu i ma eksport CSV. `labels.csv` ma kolumny `cell_id, board_sequence_number, cell_index, symbol_code, in_series, is_super_symbol, frame_label_tight, frame_label_margin`.
  - `--prepare` odmawia zapisu do istniejącego katalogu przebiegu (kod wyjścia 1, komunikat z `--run <new name>`); nigdy nie nadpisuje etykiet ani obrazów.
  - Bez serii z super symbolem (lub bez tabeli `super_game_series`) tryb zastępczy bierze komórki z 50 ostatnich pociętych plansz (`in_series=false`).
  - `--evaluate --labels` liczy udział złota na obwodzie 12 % dla obu wariantów, ocenia każdy wariant względem własnych etykiet (przeszukanie progu, precyzja / czułość / F1, `częściowo` jako pozytyw i pominięte), raportuje osobno, jak często ramka jest widoczna tylko na wycinku z marginesem (główne pytanie pilota: czy wycinek V3 zawiera ramkę), zgodność z proxy „super symbol w serii” oraz odsetek ramek wg trzech grup. Zakres złota (HSV OpenCV): odcień 15..35, nasycenie >= 90, jasność >= 120; wszystko jako parametry CLI.
- `services/worker/tests/test_m8_gold_frame_pilot.py` (nowy, 8 testów): obwódka vs brak na obrazach syntetycznych, złoty symbol w środku, przeszukanie progu, margines, normalizacja etykiet, raport z przebiegu syntetycznego, ramka widoczna tylko na wycinku z marginesem (niezależne etykiety i raport), odmowa ponownego `--prepare` na istniejącym przebiegu bez zmiany plików.
- `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_20261009.md`: szkic raportu (metoda, trzy grupy, parametry, rozkład udziału złota); rekomendacja „do uzupełnienia po etykietach operatora”.

### Verification results

- `ruff format`, `ruff check`, `mypy --strict` na skrypcie i teście: czysto.
- `pytest services/worker/tests/test_m8_gold_frame_pilot.py -q`: 8 passed.
- `--prepare --game mumie --run pilot-20261009b --artifact-root <główny katalog artifacts>` na bazie operatora (odczyt): tabela `game_data_v2.super_game_series` nie istnieje (migracja 0152 niezastosowana), 0 serii z super symbolem, tryb zastępczy: 50 komórek, 0 błędów; `labels.csv` ma nowe kolumny `frame_label_tight` i `frame_label_margin`. Ponowne uruchomienie z tym samym `--run` zakończyło się kodem 1 i komunikatem o nowej nazwie; pliki bez zmian. `--evaluate` na pustych etykietach odtworzył szkic raportu.
- Grupy (2) i (3) w prawdziwych seriach nie były jeszcze uruchomione na bazie (brak serii); ich selekcja jest zaimplementowana, ale niezweryfikowana na danych.
- Obserwacja z próby zastępczej: mediana udziału złota na obwodzie 0,09, maks 0,62; złote ramy kolumn gry mogą zawyżać wynik.

### Not completed

- Etykiety operatora (>= 30 na wariant) i raport końcowy z liczbami oraz decyzją „dalej / nie”.
- Warunki odblokowania: (1) migracja 0152 zastosowana na bazie operatora, (2) wykonana derywacja serii, (3) zdefiniowane super symbole w co najmniej 5 seriach, (4) etykiety operatora na próbie z tych serii. Próba zastępcza nie zawiera komórek super symbolu i nie nadaje się do pomiaru końcowego.

### Documentation updates

- Brak zmian w `CURRENT_STATE.md` i `DECISION_LOG.md`; wpis w `CURRENT_STATE.md` i ustawienie `Status` wykonuje prowadzący.

### Instrukcja dla operatora

1. Po spełnieniu warunków z „Not completed” uruchom z katalogu repozytorium (timeout 120 s), podając główny katalog `artifacts` z `data\originals` (w kopii roboczej jest pusty):
   `.\.venv\Scripts\python.exe scripts/m8_gold_frame_pilot.py --prepare --game mumie --limit 50 --run <nowa nazwa> --artifact-root <ścieżka do artifacts z data\originals>`
   Istniejącego przebiegu nie da się nadpisać; użyj nowej nazwy.
2. Otwórz `artifacts/gold-frame-pilot/<nowa nazwa>/index.html` (dwuklik). Dla każdej komórki odpowiedz osobno dla lewego (wycinek V3) i prawego obrazu (z marginesem 8 %): `tak`, `nie` albo `częściowo`. Postęp zapisuje się w przeglądarce.
3. Kliknij „Pobierz labels.csv” i zapisz plik w katalogu przebiegu jako `labels.csv` (po skopiowaniu nad starym), albo wypełnij kolumny `frame_label_tight` i `frame_label_margin` ręcznie.
4. Uruchom fazę B:
   `.\.venv\Scripts\python.exe scripts/m8_gold_frame_pilot.py --evaluate --labels artifacts/gold-frame-pilot/<nowa nazwa>/labels.csv`
   Raport `ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_20261009.md` i `scores.csv` służą do uzupełnienia rekomendacji.

### Recommended next task

Po etykietach: uzupełnić rekomendację raportu i zdecydować „dalej / nie” dla automatycznego proponowania super symbolu; przy „dalej” osobny task cechy komórki w weryfikacji symboli.
