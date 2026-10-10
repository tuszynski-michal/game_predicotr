---
title: Silnik siatek v3 oparty na sieci neuronowej — plan wdrożenia
status: superseded
last_updated: 2026-09-25
---

# Silnik siatek v3 na sieci neuronowej

> **Zastąpiony.** Obowiązujący plan to
> [VISION_LAB_EXECUTION_PLAN.md](VISION_LAB_EXECUTION_PLAN.md), D-447.
> Niewykonane taski wskazane poniżej rozpoznaje się po pełnych ścieżkach
> `0649-grid-nn-candidate-pool.md` … `0653-grid-nn-777-slot-fill.md`, gdyż
> numery 0649–0653 zostały niezależnie użyte przez serię „Przybliżona wygrana”.
> Stary kierunek uzupełniania slotów historycznego 777 siecią jest wycofany.
> D-446 dotyczy wyłącznie „Przybliżonej wygranej” i nigdy nie zatwierdzał
> niniejszego planu.

## Wymaganie użytkownika

Silnik wyznaczania siatek, który uczy się rozpoznawać zdjęcia ekranu różnej
jakości i wyznacza siatki 5 × 3 tam, gdzie faktycznie są symbole — także przy
pochyleniu, zakrzywieniu, rozmazaniu, odblaskach, ręce na ekranie i strzałkach.
Dane uczące **przegląda i wybiera użytkownik** (najlepsze przykłady). Start po
zakończeniu dry-runu i zapisu reweryfikacji 777 (plan
`GAME_777_GRID_REVERIFICATION_EXECUTION_PLAN.md`).

## Stan obecny (fakty z repo i pomiarów)

- Ogólny silnik v3 bez sieci (`images/screen_layout_v3`, TASK-0648) szuka plansz
  po kolorze tła; na 777 myli rzędy (plansze na zielonym tle niewykrywane) i jest
  mniej precyzyjny niż obecny silnik 777 (`GRID_ENGINE_V3_PROPOSAL.md`).
- Hybryda 777 (`scripts/reverify_777_grids.py`, v0.10.416–0.10.422) bierze siatki
  obecnego silnika i dorysowuje brakujące z modelu ekranu + ECC do mediany
  sąsiadów. Na próbce 200 zdjęć zielone siatki były bezbłędne w przeglądzie
  użytkownika, ale dorysowanie jest pewne tylko w ~32–69% slotów. Powtarzalne
  błędy: wspólny przechył prawej kolumny (ekstrapolacja modelu), przeskok
  o kolumnę/rząd (okresowość symboli), brak zaczepienia przy ręce/odblasku.
  Hybryda **nie widzi planszy** — wnioskuje o niej z sąsiadów.
- Istniejący eksperyment `images/keypoint_geometry` (TASK-0319, D-262):
  `KeypointGeometryHeatmapNetwork` (3 warstwy conv, wejście 128 px, heatmapy
  `9 × 4` narożników + obecność 9 slotów), dataset tylko z ręcznie zatwierdzonych
  quadów, split według `source_family_id`, eksport ONNX opset 18, adapter
  `CPUExecutionProvider`, manifest `shadowOnly=true`, `activationAllowed=false`.
  **Nigdy nie trenowany na prawdziwych danych** (za mało zatwierdzonych źródeł).
- D-261: domyślny rollout geometrii tylko po holdoucie ≥ 100 źródeł / 500 plansz
  z poprawnością board-level ≥ 98%. D-262: keypoint pozostaje shadow-only;
  aktywacja wymaga osobnego zadania, raportu i jawnej akceptacji.
- Środowisko: PyTorch 2.12 **CPU** (brak CUDA), onnxruntime 1.28. Infrastruktura
  treningu/wydań modelu symboli istnieje (`symbols/training_job.py`,
  `images/symbol_model_release.py`) — wzorzec do naśladowania.
- Dostępne dane 777: ~474 tys. plansz z siatką obecnego silnika (przeważająca
  część potwierdzana przez hybrydę), decyzje użytkownika z przeglądu dry-runu,
  22 zdjęcia zaakceptowane w całości (`accepted-by-user-2026-09-24.json`).

## Cel i zakres

Sieć, która dla zdjęcia ekranu 3 × 3 zwraca dla każdej z 9 plansz **24 punkty
przecięcia siatki 5 × 3** (4 × 6) oraz obecność/widoczność planszy, działająca na
CPU, z oceną jakości na stałym zbiorze testowym i z tymi samymi kontrolami
geometrycznymi co hybryda. Pierwszy odbiorca: brakujące sloty 777 (zastąpienie
kroku „dorysowania” w hybrydzie). Później: ogólny silnik dla innych gier.

Poza zakresem tego planu: zmiany API/UI Admina i Reviewera, produkcyjny import,
rollout geometrii innych gier, GPU.

## Kluczowe decyzje

1. **Dane uczą się tylko na przykładach zatwierdzonych przez użytkownika.**
   Kandydaci pochodzą automatycznie (siatki potwierdzone przez hybrydę, decyzje
   z dry-runu, później wyniki v3 dla innych gier), ale do zbioru trafia tylko
   to, co użytkownik zaakceptował w narzędziu kuracji. Zgodne z życzeniem
   użytkownika i z D-262 („tylko ręcznie zatwierdzone”) — rozszerzamy znaczenie
   „ręcznie zatwierdzone” na „przejrzane i zaakceptowane przez użytkownika
   w narzędziu kuracji” — historyczna propozycja; obowiązujące źródło to D-447.
2. **Punkty siatki, nie tylko narożniki.** 24 punkty na planszę dają lokalne
   pochylenie i zakrzywienie bez ekstrapolacji modelu (przyczyna przechyłu prawej
   kolumny). Etykietę 24 punktów wyznaczamy z zatwierdzonego quada przez
   interpolację biliniową wewnątrz planszy (plansza lokalnie ~płaska); kolumny
   i rzędy ekranu zakrzywia sieć, bo każda plansza ma własne punkty.
3. **Dwa etapy.**
   - A — lokalizacja 9 plansz na całym zdjęciu (heatmapy środków + 4 narożników,
     obecność); rozszerzenie istniejącego kontraktu `9 × 4`.
   - B — dokładne punkty siatki na wycinku wokół planszy wskazanej przez A (albo
     przez hybrydę), wejście ~256 × 160 px, 24 heatmapy + widoczność każdej
     komórki. Etap B jest niezależny od położenia planszy na ekranie i uczy się
     na setkach tysięcy wycinków.
4. **Pewność = zgodność geometryczna, nie sama pewność sieci.** Z 777 wiemy, że
   wygląd nie rozdziela dobrych i złych siatek, a geometria tak. Wynik sieci
   przechodzi: zgodność z modelem ekranu z pozostałych plansz, test połówek,
   kształt, plus pewność heatmap (szerokość piku). Zielone tylko gdy wszystko
   zgodne.
5. **Split według rodziny źródła** (import/nagranie) — zdjęcia z tego samego
   nagrania nie trafiają jednocześnie do treningu i testu.
6. **CPU-first.** Mała sieć (np. MobileNet-like / lekki U-Net, własna implementacja
   w PyTorch bez nowych zależności), trening wznawialny z checkpointami,
   ograniczony czas epoki; GPU opcjonalnie później.
7. **Shadow → narzędzie 777 → produkcja.** Najpierw pomiar obok hybrydy, potem
   użycie w narzędziu reweryfikacji 777 (z przeglądem użytkownika), dopiero
   później ewentualny produkcyjny engine (osobny plan wg D-261).

## Dane i narzędzie kuracji

- **Pula kandydatów** (tylko odczyt bazy): per plansza — ścieżka zdjęcia +
  checksum, quad, źródło kandydata (`hybrid_confirmed`, `dry_run_accepted`,
  `v3_proposal`), metryki trudności (plansza pod strzałką, skrajna kolumna,
  ECC, ekstrapolacja, odchylenie). Losowanie warstwowe: nadreprezentacja
  trudnych przypadków (prawa kolumna, strzałki, ręka/odblask), bo łatwych jest
  nadmiar.
- **Narzędzie kuracji** (lokalny plik HTML z JavaScriptem, bez zmian w API):
  siatka 5 × 3 cienką linią na wycinku i miniatura całego zdjęcia; klawisze
  A = akceptuj, R = odrzuć, S = pomiń/niepewne; licznik postępu; przycisk
  „Pobierz decyzje” zapisuje JSON, który skrypt importuje do manifestu. Pakiety
  po 200 plansz. Decyzje są trwałe (plik w `artifacts/`, wersjonowany manifest
  z checksumem), import jest idempotentny.
- **Stały zbiór testowy (złoty)**: 150 zdjęć (≥ 1 000 plansz) z trudnych
  przypadków, przejrzanych przez użytkownika jako pierwsze; nigdy nie trafia do
  treningu. Wymagania D-261 (≥ 100 źródeł, 500 plansz, 5 kategorii trudności).
- **Szacowany nakład użytkownika**: zbiór złoty ~1 000 plansz + trening
  startowy ~3 000–5 000 plansz (A/R ~1–2 s na planszę ≈ 2–3 h łącznie,
  w pakietach). Łatwe przypadki z hybrydy można akceptować hurtem po próbce.

## Taski

1. [TASK-0649](../tasks/0649-grid-nn-candidate-pool.md) — pula kandydatów i kontrakt datasetu (tylko odczyt).
2. [TASK-0650](../tasks/0650-grid-nn-curation-tool.md) — narzędzie kuracji HTML + import decyzji; kuracja zbioru złotego.
3. [TASK-0651](../tasks/0651-grid-nn-training.md) — model (etap A + B), augmentacje, trening CPU, ONNX, manifest wydania.
4. [TASK-0652](../tasks/0652-grid-nn-shadow-evaluation.md) — ocena shadow na zbiorze złotym vs hybryda, kalibracja pewności.
5. [TASK-0653](../tasks/0653-grid-nn-777-slot-fill.md) — wycofana propozycja uzupełniania slotów 777.

Zależność wstępna: zakończone przeglądy dry-runu 777 i zapis (TASK-0645–0647
przepisane na hybrydę) — decyzje z przeglądu zasilają pulę kandydatów.

## Mapa wymaganie → task → kryterium

| Wymaganie | Task | Kryterium |
|---|---|---|
| Użytkownik wybiera dane uczące | T2 | tylko plansze z decyzją `accept` w manifeście; test: odrzucone nie trafiają do eksportu |
| Różna jakość zdjęć | T1, T3 | warstwy trudności w puli; augmentacje (rozmazanie, odblask, zasłonięcie, perspektywa, zakrzywienie) |
| Siatka tam, gdzie symbole | T3, T4 | błąd 24 punktów na zbiorze złotym (mediana ≤ 0,05 komórki, p95 ≤ 0,15) |
| Brak fałszywie pewnych siatek | T4 | 0 fałszywie zielonych na zbiorze złotym; ≥ 98% poprawności board-level (D-261) |
| Lepiej niż hybryda na trudnych | T4 | pokrycie pewnych slotów ≥ 1,5 × hybryda przy zerze fałszywie zielonych |
| Bezpieczne wdrożenie | T5 | wycofane; obowiązuje nowy plan i D-447 |

## Ryzyka

- Kandydaci z hybrydy dziedziczą drobne błędy obecnego silnika — mitygacja:
  kuracja użytkownika + nadreprezentacja trudnych przypadków + etykiety tylko
  zaakceptowane.
- CPU: trening etapu B na dziesiątkach tysięcy wycinków to godziny — mitygacja:
  mała sieć, wycinki w pamięci podręcznej na dysku (artefakty, nie baza),
  checkpointy, ograniczony budżet epok.
- Przeniesienie na inne gry wymaga kuracji kilkuset plansz na grę.
- Punkty 24 z interpolacji quada nie oddają zakrzywienia wewnątrz planszy —
  akceptowalne (plansza mała); w razie potrzeby etykiety punktowe z narzędzia
  kuracji (przeciąganie punktów) jako rozszerzenie T2.
- Historyczna propozycja zmiany D-262 dla uzupełniania slotów 777 została
  wycofana; D-447 dotyczy wyłącznie nowego planu laboratoryjnego.

## Otwarte pytania (do użytkownika)

1. Czy „rodzina źródła” = import (nagranie)? Domyślnie tak.
2. Czy dostępny będzie komputer z GPU? Plan zakłada, że nie.
3. Tolerancja cięcia: ile błędu siatki (w szerokościach komórki) jest jeszcze
   akceptowalne dla odczytu symbolu? Domyślnie 0,1 komórki.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0649 | claude-sonnet-5 | high | Zapytania read-only i manifest wg istniejących wzorców datasetu keypoint; umiarkowane ryzyko. | Nie. |
| TASK-0650 | claude-sonnet-5 | high | Lokalny HTML/JS i import JSON; ważna idempotencja i brak utraty decyzji użytkownika. | Tak: claude-opus-5-5, reasoning medium — review importu decyzji. |
| TASK-0651 | claude-opus-5-5 | high | Projekt architektury sieci, augmentacji i treningu CPU; decyzje wpływają na jakość całego silnika. | Tak: claude-opus-5-5, reasoning high — review kontraktu ONNX i splitu. |
| TASK-0652 | claude-opus-5-5 | high | Kalibracja pewności i interpretacja wyników decyduje o bezpieczeństwie danych. | Nie. |
| TASK-0653 | claude-opus-5-5 | high | Historyczna, wycofana propozycja integracji z narzędziem 777. | Tak: claude-opus-5-5, reasoning high — historyczny wpis. |
