---
title: Propozycja silnika wyznaczania siatek v3 (model ekranu 3 × 3)
status: proposed
last_updated: 2026-09-24
---

# Silnik siatek v3 — propozycja

Status: **propozycja / prototyp** (TASK-0648). Nie jest używany przez import,
workera ani API. Kod: `services/worker/src/game_predictor_worker/images/screen_layout_v3/`,
podgląd: `scripts/preview_screen_layout_v3.py`.

## Problem

Zdjęcia ekranu wyników (3 × 3 plansze, każda 5 × 3 symbole) są robione z ręki,
kamerą szerokokątną: różna perspektywa, obrót, rozmazanie, odblaski, ręce na
ekranie, zakrzywienie (beczka obiektywu i/lub wygięty ekran). Ramki plansz są
w jednych grach wyraźne (GANG, Blazing), w innych prawie niewidoczne
(Treasure, Reels). Dotychczasowe silniki (V1.x, structured OpenCV, V1.2)
wymagały per-grę wzorca/profilu kalibrowanego na ręcznych zaznaczeniach.
TASK-0644 wykazał, że silnik 777 ma widoczne przesunięcia siatek, a lokalny
estymator nie jest od niego niezależny, więc nie nadaje się na weryfikator.

## Obserwacje (analiza 45 zdjęć z 12 katalogów, 6 gier)

- Wspólny jest **układ ekranu**: nasycone niebiesko-zielone tło, 9 paneli
  w siatce 3 × 3, numer sekwencji pod każdym panelem, pasek „Powrót” u dołu.
- Gra rysuje ekran zawsze identycznie: w układzie ekranu położenia paneli
  i siatek są stałe; zmienia się tylko przekształcenie ekran → zdjęcie.
- Jedna płaska perspektywa nie wystarcza — potrzebny jest człon zakrzywienia.
- Część zdjęć ma obrót zapisany w EXIF (katalog `reels_test`) — silnik
  zakłada wejście po `exif_transpose`, jak reszta repozytorium.

## Algorytm

1. **Panele** — „dziury” w masce tła ekranu (HSV: niebieski + zielony),
   obrys ekranu z grubych obszarów tła (paski LED odrzucone otwarciem
   morfologicznym), czworokąt panelu z otoczki wypukłej, filtr wypełnienia,
   proporcji i spójności rozmiarów. Przy < 6 panelach: dodatkowe kandydaty
   przez dopasowanie wzorca krawędzi wykrytego panelu (tylko wewnątrz
   ekranu, z teksturą planszy), oznaczone jako niepotwierdzone.
2. **Układ i model ekranu** — pozycje (kolumna, rząd) z przesunięć między
   panelami mierzonych w układzie każdego panelu; okno 3 × 3 wybierane
   przede wszystkim według liczby potwierdzonych paneli. Model: homografia +
   jeden człon radialny wokół środka zdjęcia + parametry układu (odstęp
   kolumn, odstęp rzędów, proporcja panelu) — 12 parametrów, dopasowanie
   Levenberga–Marquardta (numpy). Gdy wykryty blok nie wypełnia 3 × 3,
   hipotezy przesunięcia ocenia korelacja ECC przewidzianych paneli
   z medianą paneli wykrytych.
3. **Siatka bez wzorca** — 9 paneli prostowanych modelem, wzajemnie
   dopasowanych do bieżącej mediany (ECC, homografia, 3 iteracje).
   Stałe elementy (ramki, separatory bębnów, tło) są na wszystkich planszach
   takie same, symbole różne, więc **rozrzut między planszami** wskazuje
   komórki. Siatka 5 × 3 = maksymalny kontrast rozrzutu w środkach komórek
   względem linii siatki + krawędzie mediany na liniach; niejednoznaczność
   ±1 komórki rozstrzyga spójność wyglądu kolumn/wierszy mediany.
   To automatycznie wyznaczone „przesunięcia od rogów” w układzie panelu,
   więc same uwzględniają pochylenie, skalę i zakrzywienie.
4. **Dopasowanie do siatki** — punkty siatki każdej planszy (4 × 6) stają się
   pomiarami, model ekranu jest dopasowany ponownie (odporne odrzucanie
   plansz > 3 × mediany odchylenia); cykl 3–4 wykonywany dwukrotnie.
5. **Wynik** — siatka każdej planszy z modelu (także planszy zasłoniętej
   lub przyciętej) + klasyfikacja.

## Klasyfikacja planszy

Siatka planszy zmierzonej (w kadrze, ECC ≥ 0,6) pochodzi z jej własnego
dopasowania do mediany — lokalnie dokładniejszego niż gładki model; siatka
planszy niezmierzonej (zasłoniętej, przyciętej) pochodzi z modelu ekranu.

| Warunek | Status | Kod |
|---|---|---|
| plansza w kadrze, odchylenie od modelu ≤ 25% komórki, ECC ≥ 0,6 | `complete` | — |
| jak wyżej, ale całe skrajne kolumny poza kadrem (< 75% komórki widoczne) | `partial` + `unavailable_cell_indices` | — |
| komórka ucięta górą/dołem kadru | `needs_review` | `BOARD_CROPPED_VERTICALLY` |
| brakujące komórki nie tworzą całych skrajnych kolumn | `needs_review` | `BOARD_CROP_NOT_LATERAL` |
| niezgodna z modelem / słabe dopasowanie | `needs_review` | `BOARD_DISAGREES_WITH_SCREEN_MODEL`, `BOARD_ALIGNMENT_LOW`, `BOARD_NOT_ALIGNED` |
| model ekranu z < 5 zgodnych plansz | `needs_review` | `SCREEN_MODEL_WEAK` (+ `SCREEN_MODEL_TOO_WEAK_FOR_CROPPED_BOARD`) |
| > 3 plansze niezgodne geometrycznie | całe zdjęcie `needs_review` | `SCREEN_CONSENSUS_WEAK` |

Numer sekwencji nie jest odczytywany — pozycja planszy wynika z układu.

## Wyniki prototypu (TASK-0648)

Testy (`services/worker/tests/test_screen_layout_v3.py`, 7/7): syntetyczny
ekran w perspektywie — 9 siatek w granicach 12% komórki od prawdy;
przycięcie boczne → `partial` z całymi kolumnami; przycięcie góry →
`needs_review`; bramka konsensusu ekranu.

Zdjęcia rzeczywiste: 36 zdjęć (po 3 z każdego z 11 katalogów
`dane testowe do planu automatycznego wyboru zdjec` + 6 z `test folder`),
324 plansze; każda nakładka obejrzana przez agenta. Podgląd:
`artifacts/screen-layout-v3/<czas>/index.html` (lokalny, ignorowany).
Wynik ostatecznego przebiegu — patrz Outcome TASK-0648.

## Znane ograniczenia i dalsze kroki

- Progi pewności (25% komórki, ECC 0,6, > 3 niezgodne plansze) są ustalone
  na oko z 36 zdjęć — przed użyciem produkcyjnym potrzebna jest ocena
  użytkownika na większej próbce (fałszywa pewność jest groźniejsza niż
  nadmiarowe „do poprawy”).
- Zdjęcia z bardzo słabo widocznym ekranem (np. Reels z ręką i odblaskiem)
  dają słaby model — wtedy całe zdjęcie trafia do poprawy.
- Pewność nie wykrywa ręki/odblasku na pojedynczej komórce (plansza jest
  oceniana jako całość).
- Czas: 7–25 s na zdjęcie (szerokość robocza 1200 px); wyszukiwanie siatki
  i ECC są do przyspieszenia (wspólna siatka dla wielu klatek tej samej gry,
  mniejsza rozdzielczość robocza, wektoryzacja).
- Profil gry (opcjonalny): wyznaczone automatycznie przesunięcia siatki
  w panelu można uśredniać po wielu zdjęciach jednej gry i używać jako
  podpowiedzi — bez ręcznego wzorca.
- Integracja z importem/workerem, kontrakt geometrii i reweryfikacja 777
  wymagają osobnych tasków po akceptacji użytkownika.
