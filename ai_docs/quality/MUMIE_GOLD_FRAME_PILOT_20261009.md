# Pilot wykrywania złotej ramki super symbolu (TASK-0937)

Wersja narzędzia: `gold-frame-pilot-v1`. Skrypt: `scripts/m8_gold_frame_pilot.py` (tylko odczyt). Etykiety: `C:/Users/tuszy/Documents/game_predicotr/worktrees/mumie-super-game/artifacts/gold-frame-pilot/pilot-20261009b/labels.csv`.

## Metoda

- Komórki: wycinek ciasny (kwadrat komórki V3, 96 px) oraz wycinek z marginesem 8% z obrazu źródłowego.
- Prawda odniesienia: niezależne ręczne etykiety operatora, osobno dla każdego wycinka (`frame_label_tight`, `frame_label_margin`: `tak` / `nie` / `częściowo`), nadane bez widoku klasy symbolu.
- Trzy grupy próby: (1) super symbol w planszach serii, (2) inne komórki plansz serii, (3) komórki z plansz poza seriami (`in_series=false`). W trybie zastępczym (brak serii z super symbolem) próba zawiera tylko grupę (3).
- Metryka: udział „złotych” pikseli na obwodzie (zewnętrzne 12% krótszego boku wycinka); każdy wariant oceniany względem własnych etykiet.
- Zakres „złota” (HSV OpenCV): odcień 15..35, nasycenie >= 90, jasność >= 120.
- Decyzja: udział >= próg. Próg przeszukiwany od 0 do 1; `częściowo` liczone jako pozytyw, a osobno z pominięciem tych komórek.

## Próba

- Komórek w arkuszu: 50; grupy: super symbol w serii 0, inne komórki serii 0, poza seriami 50.
- Wariant `tight`: z etykietą 0 (wymagane co najmniej 30); tak 0, nie 0, częściowo 0.
- Wariant `margin`: z etykietą 0 (wymagane co najmniej 30); tak 0, nie 0, częściowo 0.

## Wyniki

Brak wystarczającej liczby etykiet dla obu wariantów; metryki nie są raportowane.

- Rozkład udziału złota na obwodzie, wariant `tight`: min 0.000, mediana 0.090, maks 0.622.
- Rozkład udziału złota na obwodzie, wariant `margin`: min 0.000, mediana 0.106, maks 0.754.

## Rekomendacja

do uzupełnienia po etykietach operatora
