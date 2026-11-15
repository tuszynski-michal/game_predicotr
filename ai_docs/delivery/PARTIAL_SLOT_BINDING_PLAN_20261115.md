---
title: Przypisanie plansz po pozycji 3×3 dla zdjęć z niepełnym wykryciem
status: accepted
last_updated: 2026-11-15
---

# Przypisanie plansz po pozycji 3×3 (zdjęcia z niepełnym wykryciem)

## Stan obecny (fakty z kodu i danych)

- Preflight V3 wiąże wykrycia sieci z numerami plansz funkcją
  `services/api/src/game_predictor_api/domain/neural_grid_proposal.py`
  `associate_expected_slots` → `associate_quad_slots`. Wiązanie powstaje tylko
  przy dokładnej inwentaryzacji: liczba wykryć == liczba numerów z nazwy pliku,
  wszystkie wykrycia strukturalnie poprawne, rzędy 3/3/3 (lub krótsze dla
  końcówki zakresu). Inaczej źródło dostaje `slot_binding_required` i import
  pomija całe zdjęcie (`NEURAL_GRID_SLOT_BINDING_REQUIRED`).
- Kontrakt wiązania (`validate_neural_source_binding`) już dopuszcza
  `missingPositionIndexes` (używa go ręczne przypisanie), a worker
  (`services/worker/src/game_predictor_worker/images/neural_pending_geometry.py`
  `neural_pending_payload`) zachowuje brakujące pozycje jako odroczone.
- Bramka cięcia `services/api/src/game_predictor_api/domain/neural_crop_policy.py`
  `neural_auto_crop_blockers` wymaga `missingPositionIndexes == []` i kompletu
  pozycji, więc przy jednej brakującej planszy żadna plansza zdjęcia nie
  dostaje automatycznego cięcia.
- Akceptacja `services/api/src/game_predictor_api/domain/v3_engine_acceptance.py`
  `qualify_v3_engine_acceptance` wymaga kompletu pozycji, braku
  `missingPositionIndexes` i braku odroczonej geometrii (`deferred`).
  Dane Mumie A2 (ostatnie 30 h): rewizje `accepted` mają komórki symboli dla
  170 424/170 424 plansz, `needs_review` tylko dla 94/733 — akceptacja
  decyduje o rozpoznaniu symboli.
- Import Mumie A2 (13 folderów, 2026-11-14/15): 8 zdjęć `slot_binding_required`.
  Przegląd obrazów: 246592-246600 (8 wykryć, przeoczona plansza w rogu),
  431191-431199 i 439435-439443 (9 wykryć, jedno strukturalnie błędne),
  499996-500000 (zakres 5, 5 plansz + 3 fałszywe wykrycia w pustych slotach
  strony), 442972-442980 (8, górny rząd przycięty kadrem), 304732-304740
  i 304741-304749 (10, fałszywe wykrycie w tabeli wypłat), 305785-305793
  (6, prawa kolumna poza kadrem).

## Cel

Zdjęcie, na którym sieć wykryła część plansz, ale położenie każdej wykrytej
planszy w siatce strony 3×3 jest jednoznaczne, wchodzi do importu jak każde
inne: przypisane plansze dostają automatyczne cięcie, akceptację V3 i
rozpoznanie symboli, a nieprzypisane pozycje zostają brakami w ręcznej
kolejce geometrii.

## Decyzja (D-614, proponowana)

Wiązanie częściowe jest dozwolone tylko, gdy cała siatka strony jest
zakotwiczona przez wykrycia; nie zgadujemy przesunięcia strony.

Reguła `associate_expected_slots` (po nieudanym dokładnym wiązaniu, które
pozostaje bez zmian):

1. Bierz tylko wykrycia `structurallyValid`.
2. Osie strony i rzuty środków jak w `associate_quad_slots` (mediany wektorów
   krawędzi; te same warunki odrzucenia).
3. Klasteryzuj rzuty na rzędy (tolerancja: połowa mediany wysokości planszy)
   i kolumny (tolerancja: połowa mediany szerokości planszy).
4. Wymagaj dokładnie 3 rzędów i 3 kolumn. Mniej → brak wiązania
   (np. cała kolumna poza kadrem: nie wiadomo, które to kolumny). Więcej →
   brak wiązania (np. fałszywe wykrycie w tabeli wypłat tworzy 4. rząd).
5. Pozycja = `rząd * 3 + kolumna`. Dwa wykrycia w jednej komórce → brak wiązania.
   Brak nakładania się obrysów (ten sam test SAT co dziś).
6. Wykrycia na pozycjach `>= board_count` (puste sloty końca zakresu) są
   ignorowane (`ignoredDetectionIds`), nie przypisywane.
7. Wymagaj co najmniej `board_count - 2` przypisań (najwyżej dwie brakujące
   plansze na stronę); inaczej brak wiązania.

Tabela przykładów (oczekiwane wyniki na prawdziwych zdjęciach):

| Zdjęcie | Wynik |
|---|---|
| 246592-246600 | wiązanie, brak pozycji 2 |
| 431191-431199, 439435-439443 | wiązanie, brak pozycji błędnego wykrycia |
| 499996-500000 | wiązanie 0–4, wykrycia 5–7 ignorowane |
| 442972-442980 | wynik wg testu (rzędy kompletne → wiązanie) |
| 304732-304740, 304741-304749 | brak (4 rzędy) |
| 305785-305793 | brak (2 kolumny) |

Bramka cięcia i akceptacja: pozycja przypisana w wiązaniu z
`missingPositionIndexes` jest oceniana jak pozycja w wiązaniu pełnym.
Pozycje z `missingPositionIndexes` są pomijane w ocenie kompletności, a
odroczona geometria (`deferred`) blokuje akceptację tylko wtedy, gdy dotyczy
pozycji przypisanej. Wiązanie ręczne z brakami podlega tej samej regule.

## Zakres

- TASK-1208: wiązanie częściowe w domenie + złagodzenie bramki cięcia, testy
  jednostkowe i test na zapisanych wykryciach 8 zdjęć.
- TASK-1209: akceptacja V3 i jej repozytoria (`v3_engine_acceptance_repository`,
  `virtual_grid_geometry_repository`, `grid_engine_acceptance_repository`)
  dla wiązań z brakami; test integracyjny PostgreSQL importu zdjęcia z jedną
  brakującą planszą.

## Poza zakresem

- Zmiana modelu siatki (przeoczenia sieci) i reguły dla 4 rzędów / 2 kolumn
  (zostają ręczne).
- Ponowny preflight i import 8 zdjęć na bazie operatora — osobny krok po
  scaleniu, za zgodą.
- `associate_quad_slots` (używane też przez `grid_rescue_strategy`) zostaje
  bez zmian; reinferencja (`grid_reinference_handler`) dostaje nową regułę
  automatycznie przez `associate_expected_slots` (odnotować w D-614).

## TASK-1208 — wiązanie częściowe i bramka cięcia

- Pliki: `domain/neural_grid_proposal.py` (`associate_expected_slots`, nowa
  funkcja `associate_partial_slots`), `domain/neural_crop_policy.py`
  (`neural_auto_crop_blockers`: zamiast `missingPositionIndexes == []` i
  kompletu — przypisana pozycja + spójny podział zakresu na przypisane i
  brakujące), testy `services/api/tests/test_neural_grid_proposal.py`,
  `services/api/tests/test_neural_auto_crop_v2.py`, nowy
  `services/api/tests/test_partial_slot_binding.py` (proponowany) z fixture
  węzłów siatek 8 zdjęć (tylko `latticeNodes`/`structurallyValid`, bez pikseli).
- Kryteria: wyniki z tabeli D-614; dotychczasowe testy dokładnego wiązania i
  bramki bez zmian asercji; pozycja brakująca nadal zablokowana
  (`NEURAL_GRID_SLOT_DETECTION_MISSING`).
- Weryfikacja: `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_neural_grid_proposal.py services/api/tests/test_neural_auto_crop_v2.py services/api/tests/test_partial_slot_binding.py services/worker/tests/test_neural_page_geometry_preflight.py`, `npm run python:lint`, `npm run python:typecheck`.

## TASK-1209 — akceptacja V3 dla wiązań z brakami

- Pliki: `domain/v3_engine_acceptance.py` (`qualify_v3_engine_acceptance`:
  oczekiwane pozycje = zakres minus `missingPositionIndexes`; plansze
  brakujących pozycji nie wchodzą do `positions`), wywołujące repozytoria
  (budowa `positions` i `deferred` z pominięciem brakujących pozycji),
  testy `services/api/tests/test_v3_engine_acceptance*.py` i integracyjny
  `services/api/tests/integration/test_neural_page_geometry_postgres.py`.
- Kryteria: zdjęcie z jedną brakującą pozycją → rewizja `accepted`,
  przypisane plansze z automatyczną geometrią, brakująca pozycja jako
  `pending` w `image_board_geometry_pending`; zdjęcie z odroczoną pozycją
  przypisaną → nadal `V3_ACCEPTANCE_DEFERRED`; pełne wiązania bez zmian.
- Weryfikacja: testy jednostkowe akceptacji + integracyjne z
  `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'` (bazy `*_test`).

## Ryzyka

- Błędne wiązanie przesuwa numery sekwencji (inwariant domeny). Ograniczenie:
  wymóg pełnych 3 rzędów i 3 kolumn, brak duplikatów w komórce, limit dwóch
  braków; każda plansza nadal przechodzi przegląd symboli człowieka.
- Szersza zmiana bramek bezpieczeństwa → niezależny audyt TASK-1209.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1208 | Claude Opus 5.5 | high | Czysta logika geometryczna z testami na prawdziwych danych; średnie ryzyko. | Nie; eskalacja do audytu, jeśli wyniki odbiegną od tabeli D-614. |
| TASK-1209 | Claude Opus 5.5 | high | Zmiana bramki akceptacji w kilku repozytoriach i test PostgreSQL; wysokie ryzyko danych. | Tak: Codex (domyślny model CLI `codex`, warunkowo), reasoning high, skill `audit-task`. |
