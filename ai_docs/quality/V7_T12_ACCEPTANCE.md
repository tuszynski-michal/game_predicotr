---
title: V7 T12 holdout acceptance and release-gate audit
status: blocked
last_updated: 2026-09-21
---

# Odbiór V7 T12 — wynik zablokowany

## Werdykt

`blocked`. V7 nie może zostać aktywowane i API musi nadal zwracać
`SEMI_AUTOMATIC_SELECTION_V7_BLOCKED` przed wyborem lokalnego źródła,
utworzeniem runu albo zużyciem tokenu. Wynik nie jest negatywną oceną jakości
OCR; jest fail-closed, ponieważ nie istnieje niezależny, checksum-bound dowód
do obliczenia wymaganych mianowników, a sam runtime V7 nie jest jeszcze
podłączony do handlera joba.

## Przypięte wejście

- Manifest i zamrożony inventory T01 przeszły ponowną kontrolę z fingerprintem
  `604185fbe5d8bbfe071788dd38a9bf6cf764d16561415afcf4e29b70d54ffda9`.
- T05 został ponownie uruchomiony read-only z checksumowanym szkieletem
  anotacji. Nie utworzono runu, katalogu `cut`, outputu JPEG ani aktywacji.
- Aktualny manifest wskazuje `rells_big` jako holdout (1 068 JPEG-ów), ale
  decyzja [D-404](../process/DECISION_LOG.md) wyklucza z niezależnego odbioru
  jego wcześniej oglądany plik `reels 218400_000114.jpg`. Bieżący manifest nie
  wyłącza tego pliku, więc nie jest gotowym, w pełni niezależnym holdoutem.

## Metryki jakości

| Miara | Wynik | Wymaganie | Status |
| --- | ---: | ---: | --- |
| Kalibracja geometrii | brak anotacji | 5 niezależnych źródeł na pozycję, residual p95 ≤ 0,04 | `not_evaluable` |
| Odzysk automatyczny zakresów | 0 / 0 | ≥ 95% | `not_evaluable` |
| Zapisany reprezentant | 0 / 0 | ≥ 95% | `not_evaluable` |
| Błędne automatyczne zakresy | 0 przy pustym zbiorze | 0 przy niepustym zbiorze | `not_evaluable` |
| Warning przycięcia góra | 0 / 0 | 100% | `not_evaluable` |
| Warning przycięcia dół | 0 / 0 | 100% | `not_evaluable` |
| False-positive warnings | 0 przy pustym zbiorze | raportować | `not_evaluable` |
| Manual review | 0 przy pustym zbiorze | raportować | `not_evaluable` |

Zero w licznikach nie oznacza sukcesu. Wszystkie wyniki dotyczą pustego
mianownika, dlatego raport T05 zwraca `productionActivation.status=blocked`.
Pomiar T11 (4 workery, okno 8, CPU-only Paddle) opisuje tylko koszt pięciu
źródeł development/calibration; nie jest dowodem proofu, kalibracji ani jakości
holdoutu.

## Recovery i kompatybilność

- Worker V7/recovery: `113 passed`. Zestaw obejmuje konfigurację, proof,
  occurrence, quality/ranking, kalibrację, checkpoint/finalizację, writer,
  first write, manual first/no-OCR/replace, restart, supersede/cancel,
  generation race i uporządkowany runtime.
- API i migracja: `30 passed` (jedno ostrzeżenie deprecacyjne Starlette).
  Test potwierdza blokadę V7 przed źródłem/jobem oraz zachowanie historycznego
  `selection` i `filename_verification`.
- Admin: `59 passed`, typecheck i lint przeszły. Formularz V7 pozostaje
  zablokowany przez capabilities; legacy output picker, viewer i lokalny output
  zachowują swój workflow.

## Dodatkowy bloker implementacyjny

Moduły T02–T11 są obecnie framework-free i nie są połączone z produkcyjnym
`SemiAutomaticImageSelectionJobHandler`. Handler posiada ścieżki historyczne
`filename_verification` i legacy `selection`, lecz nie wywołuje
`V7ScanRunState`, `V7OutputWriter` ani `run_v7_ordered_runtime`. Zdjęcie twardej
blokady API przed dostarczeniem tego pionu skierowałoby `v7_selection` do
niewłaściwego legacy handlera. To niezależny bloker aktywacji, wykryty podczas
T12, nie wada danych wejściowych.

## Warunki ponownego odbioru

1. Utworzyć nowy, wcześniej nieoglądany holdout albo nowy manifest wykluczający
   plik wskazany w D-404; zamrozić jego inventory przed pierwszym probe'em.
2. Ręcznie oznaczyć co najmniej pięć niezależnych calibration sources na każdą
   pozycję 3×3 oraz zmierzyć geometrię bez przekroczenia residualu p95 `0,04`.
3. Dla holdoutu ręcznie opisać każdy oceniany zakres: jego własne źródła dowodu,
   kwalifikowalność reprezentanta i niezależne oznaczenia przycięcia góra/dół.
   Predykcje automatu należy zamrozić przed ręczną korektą.
4. Dostarczyć osobny pion integracyjny, który po udanym odbiorze łączy worker
   V7, trwały run/checkpoint, writer i kontrolowaną bramkę API. Pion musi mieć
   test end-to-end i zachować historyczny handler.
5. Dopiero po spełnieniu wszystkich progów i review operator może podjąć nową,
   jawną decyzję aktywacji. Ten raport nie jest taką decyzją.
