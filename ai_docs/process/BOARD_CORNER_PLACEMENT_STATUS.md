# Board Corner Placement - Status

## Aktualne zachowanie

Po kliknięciu "Wyznacz 9 plansz osobno":

1. Jeśli brak geometrii (`pageCorners === null`):
   - Użytkownik musi ustawić 4 narożniki strony (LT, PT, PD, LD)
   - Klikanie dodaje punkty do `cornerPlacement`
   - Po 4 punktach wchodzi w tryb edycji

2. Jeśli jest geometria (`pageCorners !== null`):
   - Wchodzi w tryb edycji pierwszej planszy (`correctionMode = 0`)
   - Widzi automatyczną geometrię
   - Może przeciągać narożniki tej planszy (drag-hold)

## Dostępne mechanizmy

### Drag-hold (obecny)
- Kliknij i trzymaj circle narożnika
- Przeciągnij myszkę → punkt się przesuwa
- Puść → koniec

### Wybór planszy
- Selektor "Zakres korekty" pozwala przełączać między:
  - `page` - cała strona (4 główne uchwyty)
  - `curve` - wszystkie plansze (36 narożników)
  - `0, 1, 2, ...` - konkretne plansze

## Planowane ulepszenia

### click-release-move-click (do zaimplementowania)
- Kliknij LT → punkt zaznaczony (nie przeciągany)
- Puść → punkt utwierdzony, siatka preview
- Przesuń myszkę → preview się porusza
- Kliknij PD → drugi punkt + automatyczne obliczenie reszty
- Wszystkie 4 kąty można przeciągać

## Testy

Brak testów jednostkowych dla tej interakcji. Należy dodać testy zgodnie z wymaganiami użytkownika.

## Uwagi

Użytkownik zgłosił, że obecny drag-hold nie działa poprawnie i chce model click-release-move-click. To wymaga refaktoryzacji całego mechanizmu.
