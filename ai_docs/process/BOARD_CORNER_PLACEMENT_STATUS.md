# Board Corner Placement - Status

## Zaimplementowany model

Po kliknięciu "Wyznacz 9 plansz osobno" uruchamiany jest tryb osadzania plansz:

1. Stara geometria jest czyszczona (`pageCorners = null`, `boardOverrides = new Map()`, `meshOverrides = new Map()`).
2. Użytkownik wyznacza każdą planszę za pomocą **dwóch kliknięć**:
   - **Pierwsze kliknięcie** — lewy górny narożnik (LT).
   - **Drugie kliknięcie** — prawy dolny narożnik (PD).
3. Algorytm automatycznie wylicza pozostałe dwa narożniki:
   - PT = `{ x: PD.x, y: LT.y }`
   - LD = `{ x: LT.x, y: PD.y }`
4. Prostokąt jest akceptowany, tylko jeśli tworzy poprawny clockwise quad.
5. Po wyznaczeniu wszystkich `expectedBoardCount` plansz następuje przejście do trybu edycji.

## Testy

Testy kontraktu znajdują się w:
- `apps/admin/test/page-geometry-correction-panel-contract.test.mjs`

Uruchomienie:
```powershell
node --test apps/admin/test/page-geometry-correction-panel-contract.test.mjs
```

## Pozostałe kwestie

- Nie ma jeszcze testów jednostkowych logiki dwuklikowego wyznaczania planszy.
- Interakcja nie obejmuje żadnych testów kliknięć w środowisku przeglądarkowym.
