---
title: TASK-0831 — audyt cichych błędów siatek 777 siecią neural_grid
status: todo
last_updated: 2026-10-04
---

# TASK-0831 — audyt cichych błędów siatek 777

## Status

`todo`

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

- [ ] Przebieg obejmuje wszystkie zdjęcia `geometry_complete`; pominięte z
      powodem; wznowienie po przerwaniu.
- [ ] Zero zapisów do bazy (transakcje `READ ONLY`, sprawdzone).
- [ ] Lista podejrzanych z klasyfikacją, poziomem, liczbą decyzji
      symboli i odnośnikiem do korekty.
- [ ] Obrazy porównawcze i sposób przeglądu dla operatora (komenda, adres).
- [ ] Raport z licznościami i oszacowaniem.
- [ ] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "silent_grid or production_geometry or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

## Outcome

Wypełnia agent po pracy.

### Changed

- Do uzupełnienia po wykonaniu.

### Verification results

- Do uzupełnienia po wykonaniu.

### Not completed

- Do uzupełnienia po wykonaniu.

### Documentation updates

- Do uzupełnienia po wykonaniu.

### Recommended next task

- Do uzupełnienia po wykonaniu.
