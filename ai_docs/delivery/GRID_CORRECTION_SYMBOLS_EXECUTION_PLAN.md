---
title: Plan — symbole w korekcie cięcia siatki
status: accepted
last_updated: 2026-10-02
---

# Symbole w korekcie cięcia siatki

Polecenie operatora z 2026-10-02 (decyzja D-486). Plan wykonywany w jednym
etapie: TASK-0817 → TASK-0818 → TASK-0819.

## Stan obecny (fakty z kodu)

- Ekran „Korekta cięcia siatki”
  (`apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx::BoardGeometryCorrectionWorkspace`)
  obsługuje dwa cele: planszę odroczoną (`deferredBoardGeometryTarget`) i
  planszę ze zgłoszeniem „Zła siatka” (`reportedBoardGeometryTarget`) w
  `board-geometry-correction-target.ts`. Podgląd jest wyłącznie PNG.
- Zapis: `createImageGridReviewGeometryRevision`
  (`api/image_grid_reviews.py` → `VirtualGridGeometryService.save`) oraz
  `resolvePendingBoardCellGeometryManually`
  (`api/board_cell_geometry_pending.py` →
  `BoardCellGeometryPendingService.resolve_manual` →
  `VirtualGridGeometryService.save_pending_slot`). Oba serwisy pracują w jednej
  sesji SQLAlchemy na żądanie (`main.py`), więc zapis jest jedną transakcją.
- Po zapisie komórki `image_symbol_review_cells` istnieją w tej samej sesji
  (`_replace_current_cells` / `synchronize_after_geometry_change`), o ile
  projekcja gry jest zainicjalizowana i zdjęcie przeszło bramkę D-484.
- Zatwierdzenie symbolu człowieka dla bieżącego cropa już istnieje:
  `SymbolCellReviewAction.REASSIGN` →
  `domain/image_symbol_reviews.py::reassign_symbol_cell_review` (`approved`,
  `assignment_source = human`, idempotentne), wykonywane przez
  `SqlAlchemySymbolCellReviewMutationRepository.apply_mutation`.
- Predykcja modelu dla odroczonego slotu istnieje tylko przy zapisie
  (`VirtualGridGeometryService._predict_pending_slot`); podgląd wywołuje
  `_prepare_source(..., predict=False)`.
- Katalog symboli jest dostępny w Reviewerze: `listSymbols`
  (`GET /admin/games/{id}/symbols`, dozwolone w `reviewer-proxy-policy.ts`).

## Cel

Operator na ekranie korekty widzi symbole ustalone dla bieżącego cięcia, może
kliknąć kafelek i narzucić symbol, a zapis siatki zapisuje narzucone symbole
jako zatwierdzone — w tej samej transakcji co geometrię.

## Decyzje

1. **Atomowość:** narzucone symbole są zapisywane w transakcji zapisu siatki.
   Błąd przypisania wycofuje także geometrię; operator może zapisać siatkę bez
   symboli.
2. **Mechanizm:** wyłącznie istniejąca akcja `REASSIGN` na bieżących komórkach
   planszy; bez nowej logiki stanów, bez migracji.
3. **Zakres pól:** pola niekliknięte zachowują dotychczasowy przepływ
   (Weryfikacja symboli z predykcją/podpowiedzią). Pola częściowo widoczne
   można oznaczyć ręcznie (`partial_visibility` pozostaje flagą piksela). Pola
   bez pikseli nie są klikalne.
4. **Podpowiedzi:** plansza zgłoszona pokazuje symbole zapisane w bazie
   (przypisany, w razie braku predykcja); plansza odroczona pokazuje predykcję
   przypiętego modelu dla bieżącego cięcia. Podpowiedź niczego nie zapisuje.
5. **Idempotencja:** powtórzenie zapisu tym samym kluczem zwraca istniejącą
   rewizję i ponownie stosuje przypisania (`REASSIGN` jest idempotentne).
6. **Poza zakresem:** dialog korekty w przeglądzie operacyjnym
   (`operationalBoardGeometryTarget`), skróty klawiszowe, obrazy symboli w
   palecie, predykcja modelu dla plansz zgłoszonych.

## Błędy

| Warunek | Kod | HTTP | Skutek |
| --- | --- | --- | --- |
| Zdublowany indeks pola | `IMAGE_GRID_REVIEW_CELL_SYMBOLS_INVALID` | 422 | nic nie zapisano |
| Pole nie ma bieżącej komórki weryfikacji (projekcja niezainicjalizowana, bramka D-484, pole bez pikseli) | `IMAGE_GRID_REVIEW_SYMBOL_CELL_UNAVAILABLE` | 422 | rollback całego zapisu |
| Symbol nieaktywny w grze | `SYMBOL_CELL_REVIEW_TARGET_SYMBOL_INVALID` | 422 | rollback całego zapisu |

## Mapa wymaganie → zadanie → test

| Wymaganie | Zadanie | Test |
| --- | --- | --- |
| Narzucone symbole trafiają do bazy przy zapisie siatki | 0817 | testy serwisu, test SQL repozytorium |
| Podgląd symboli dla cięcia | 0818 | testy serwisu i polityki proxy |
| Klikalne kafelki i paleta | 0819 | test interakcji Reviewera |
| Jeden widok cropów, podgląd niepełnych plansz | 0816 (wykonane) | — |

## Odbiór całości

Na żywym Reviewerze: plansza odroczona i zgłoszona — podpowiedzi widoczne,
kliknięcie kafelka + symbol, zapis, pole widoczne jako zatwierdzone w
Weryfikacji symboli. Wymaga restartu API i przebudowy Reviewera.

## Ryzyka

- Komórki mogą nie istnieć po zapisie (D-484, brak backfillu) — jawny błąd
  zamiast cichego pominięcia.
- Narzucone etykiety pozostają przy indeksach pól po dalszym przesunięciu
  siatki; operator widzi je na kafelkach przed zapisem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0817 | claude-fable-5-1 | poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa) | Zapis w transakcji geometrii i kontrakt API; ryzyko danych. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
| TASK-0818 | claude-fable-5-1 | poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa) | Dwa nowe endpointy tylko do odczytu i klient. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
| TASK-0819 | claude-fable-5-1 | poziom bieżącej sesji (nazwy poziomu nie da się odczytać ze środowiska — rekomendacja warunkowa) | Zmiana UI edytora z testem interakcji. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
