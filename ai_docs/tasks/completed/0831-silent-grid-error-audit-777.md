---
title: TASK-0831 — audyt cichych błędów siatek 777 siecią neural_grid
status: done
last_updated: 2026-10-04
---

# TASK-0831 — audyt cichych błędów siatek 777

## Status

`done`

## Goal

Lista plansz gry 777, których zapisana (zaakceptowana) siatka wyraźnie
różni się od siatki `neural_grid`, posortowana od największej różnicy, z
obrazem porównawczym i odnośnikiem do istniejącej korekty siatki, gotowa do
przeglądu operatora — bez żadnego zapisu do bazy.

## Context

Raport V3-C (`ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md`):
na zbiorze złotym sieć wskazała 7 zatwierdzonych siatek przesuniętych o rząd
albo kolumnę (ciche błędy silnika produkcyjnego), których nikt nie zauważył.
Złe siatki dają złe wycinki symboli; operator właśnie przypisuje symbole,
więc wczesne wykrycie ma bezpośrednią wartość. Operator polecił audyt
2026-10-04.

## Dependencies / entry conditions

- Model profilu 777 v2 = run 1: eksport
  `neural-grid-runs\43933ac8d7d443c8b9079630a83de2e6\exports\2cd19738367121e6-round3`
  (ONNX; CPU 0,17 s/zdjęcie, GPU szybciej).
- Eksporter TASK-0800 (`scripts/vision_lab_geometry_export.py`,
  `vision_lab/production_geometry.py`) i manifest kandydatów
  `production-geometry\production-geometry-777-20261004`? — użyj
  najświeższego eksportu albo wykonaj nowy tylko do odczytu, jeżeli dane
  zmieniły się od 2026-10-02 (operator poprawia siatki i symbole).
- Baza deweloperska: wyłącznie odczyt, transakcje `READ ONLY`. Operator
  równolegle przypisuje symbole — odczyt krótkimi transakcjami, bez
  długich blokad.
- GPU wolne; żaden trening nie trwa.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Duży przebieg na danych produkcyjnych
tylko do odczytu, dobór miary rozbieżności tak, by wychwycić przesunięcia
okresu bez zalewu fałszywych alarmów. Audyt zawieszony decyzją operatora
(2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/quality/GRID_V3_COMPARISON_REPORT_20261004.md` (taksonomia,
  przesunięte etykiety U)
- `ai_docs/quality/GRID_V3_PRODUCTION_GEOMETRY_INVENTORY_20261002.md`
- `ai_docs/guides/VISION_LAB_EXPORT.md`
- `ai_docs/process/DECISION_LOG.md` (D-484, D-485, D-489)

## Scope

1. Przebieg sieci (ONNX, GPU jeżeli dostępny w środowisku
   `.venv-vision-lab`, inaczej CPU) na wszystkich zdjęciach 777 o stanie
   `geometry_complete` (ok. 55 500), wznawialny, z zapisem wyników per
   zdjęcie w nowym katalogu danych labu.
2. Porównanie z zapisaną siatką każdej żywej planszy (ta sama, z której
   powstał manifest renderu): parowanie po IoU, miary NME i maksymalny błąd
   węzła, klasyfikacja rozbieżności: przesunięcie o kolumnę, o rząd, inna
   skala/obrót, plansza tylko w sieci, plansza tylko w zapisie, drobna
   (w tolerancji D-483).
3. Ranking podejrzanych plansz (od największej rozbieżności) z poziomem
   etykiety (G/S/B z TASK-0800), stanem komórek symboli (ile komórek ma
   decyzję człowieka — przy przesuniętej siatce te decyzje dotyczą złych
   wycinków), odnośnikiem do korekty siatki w Adminie/Reviewerze
   (identyfikatory, które przyjmują istniejące narzędzia korekty).
4. Obrazy porównawcze (zapis na czerwono, sieć na zielono, jak w
   przeglądzie runu 1) dla co najmniej 200 najwyższych pozycji i dla
   wszystkich przesunięć okresu; strona przeglądu: jeżeli istniejące
   narzędzie `label_review` da się użyć bez przebudowy (ocena „sieć ma
   rację / zapis ma rację / nie wiem”), użyj go na osobnym porcie (8107);
   inaczej plik HTML z miniaturami.
5. Raport w `ai_docs/quality/` z licznościami per typ rozbieżności i
   poziom, oszacowaniem liczby cichych błędów w 777 i liczbą komórek
   symboli z decyzją człowieka na podejrzanych planszach.

## Out of scope

- Jakikolwiek zapis do bazy (korekty robi operator istniejącymi
  narzędziami), migracje, trening, zmiany pipeline.

## Acceptance criteria

- [x] Przebieg obejmuje wszystkie zdjęcia `geometry_complete`; pominięte z
      powodem; wznowienie po przerwaniu. (55 499 / 55 499, 0 pominiętych;
      wznowienie: obcięcie urwanej linii i pominięcie gotowych zdjęć, test
      jednostkowy; w przebiegu nie było potrzebne.)
- [x] Zero zapisów do bazy (transakcje `READ ONLY`, sprawdzone).
- [x] Lista podejrzanych z klasyfikacją, poziomem, liczbą decyzji
      symboli i odnośnikiem do korekty.
- [x] Obrazy porównawcze i sposób przeglądu dla operatora (komenda, adres).
- [x] Raport z licznościami i oszacowaniem.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`. (`Outcome` wypełniony;
      commit i `CURRENT_STATE.md` należą do orkiestratora.)

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "silent_grid or production_geometry or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

## Outcome

Raport: `ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md`. Wyniki:
`C:\Users\tuszy\Documents\game_predictor_vision_data\silent-grid-audit\777-20261004\`.

- Nowy eksport tylko do odczytu (928 s, 2 transakcje równoległe,
  `transactionReadOnlyVerified = true`, head `0139`): 55 499 zdjęć, 499 460
  plansz, 0 wykluczeń.
- Sieć run 1 (wagi eksportu `2cd19738…-round3`, PyTorch CUDA, bo ONNX Runtime
  w `.venv-vision-lab` ma tylko CPU; zgodność z ONNX CPU 0,012 px): 55 499
  zdjęć w ok. 30 min (2 shardy), 0 błędów.
- Poza tolerancją D-483: 3 629 plansz z parą (958 przesunięć okresu: 613
  kolumn, 344 rzędy, 1 przekątna; 2 671 `scale_rotation`, w tym 2 483 tuż za
  tolerancją), 5 `saved_only`, 28 `network_only`.
- Obejrzane 136 obrazów: 104 potwierdzone błędy zapisu, 17 błędów sieci, 9
  niejasnych/drobnych, 6 `network_only` bez złej siatki. Grupa 231 przesunięć
  o kolumnę na prawej górnej planszy (zapis na prawo od sieci) to błąd sieci
  (13/13); pozostałe 727 przesunięć — błąd zapisu (89/89).
- Oszacowanie cichych błędów: ok. 700–730 plansz z przesunięciem okresu i
  91–144 z dużym przekrzywieniem, razem ok. 790–870 plansz na ok. 740
  zdjęciach; na 727 przesunięciach 253 komórki z decyzją człowieka (130
  plansz), na 154 dużych `scale_rotation` 148 (60 plansz).
- Przegląd operatora: `http://127.0.0.1:8107/` (1 233 pozycje; oceny „sieć
  ma rację / zapis ma rację / nie wiem” w `review\history.jsonl`).

### Changed

- `services/worker/src/game_predictor_worker/vision_lab/silent_grid_audit.py`
  (nowy: `saved`, `infer`, `parity`, `compare`, `render`, `board-ids`, `refs`).
- `services/worker/src/game_predictor_worker/vision_lab/silent_grid_review.py`
  (nowy: strona przeglądu, port 8107, tylko pętla zwrotna).
- `services/worker/tests/test_silent_grid_audit.py` (11 testów).
- `ai_docs/quality/SILENT_GRID_AUDIT_777_20261004.md` (raport).

### Verification results

- `pytest services/worker/tests -k "silent_grid or production_geometry or
  no_production_storage_imports"`: 51 passed.
- `ruff check services scripts`: 1 wcześniejsze E501 w
  `services/worker/tests/test_page_geometry_preflight.py` (poza zakresem);
  nowe pliki czyste, `ruff format --check` czyste.
- `mypy --strict` dla dwóch nowych modułów: 0 błędów w nich (35 błędów w 7
  innych, istniejących modułach importowanych przez mypy).
- Odczyt bazy: eksporter (transakcje `REPEATABLE READ READ ONLY`, sprawdzone
  `SHOW transaction_read_only`) i jedno zapytanie o identyfikatory komórek
  (`SET default_transaction_read_only = on`, `BEGIN … READ ONLY`,
  `transaction_read_only = on`). Brak zapisów.

### Not completed

- Commit i `CURRENT_STATE.md` (poza zakresem wykonawcy).
- Nie obejrzano pojedynczo ok. 1 100 z 1 233 obrazów; oszacowania z próbek.
- Brak bezpośredniego linku do korekty konkretnej planszy (istniejące
  narzędzia przyjmują kolejkę importu i zgłoszenie „Zła siatka” na komórce).

### Documentation updates

- Nowy raport jakości `SILENT_GRID_AUDIT_777_20261004.md`.

### Recommended next task

- Przegląd operatora na 8107 (najpierw przesunięcia poza grupą prawej górnej
  planszy), potem korekty istniejącymi narzędziami.
- Osobno: błąd sieci run 1 na prawej górnej planszy z ciemną skrajną kolumną
  (231 przypadków) jako dane do doszkalania / bramki shadow.
- Osobno: 7 zdjęć `geometry_complete` z mniejszą liczbą żywych plansz niż
  oczekiwana (`network_only`).
