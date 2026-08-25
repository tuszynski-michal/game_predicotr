---
title: Board cell geometry v19 and symbol model rollout closure
status: accepted
last_updated: 2026-08-23
---

# Zamknięcie rollout'u geometrii v19 i adaptera v20

## Decyzja końcowa

Rollout zostaje zamknięty jako **kontrolowany opt-in**, a nie aktywacja
domyślna:

- `historical_v18` pozostaje domyślnym trybem nowych importów,
- `verified_v19` uruchamia pełny adapter
  `board-cell-processing-v20-verified-v19-v1` wyłącznie po jawnym potwierdzeniu
  operatora dla konkretnego stagingu,
- kandydat modelu symboli wytrenowany na cropach v19 pozostaje `rejected`,
- aktywny model symboli i jego fingerprint nie zostały zmienione.

## Łańcuch dowodowy

| Etap | Niezmienny wynik | Checksum / fingerprint | Decyzja |
| --- | --- | --- | --- |
| A/B v18 kontra ręczne v19 | 81 plansz, `71,03% → 95,80%` symbol accuracy | `e7f09e594d4013aee49362d7c22b0a0916acf47361f6ca742f15895a163e14eb` | geometria jest główną przyczyną błędów |
| Shadow v19 | 300 stron, 2700 plansz, `93,78%` pokrycia | `8640084933f74586e2a429120ac29835c7e7fa20d9ac52d91c9c2f271c22473f` | brak domyślnego rollout'u przy bramce `98%` |
| Residuale symboli v19 | 321 plansz, 4815 cropów, 41 rodzin źródeł | kohorta `eaa368b5fd6671103c1e2e65ff06ada082a08da0d47a09ea48f629791523ab88`; raport `c617fdf461fa4e9a56d5bebc96a01f01ab3e3b3348c46670a731613c5d07d3cc` | osobny retraining uzasadniony przez M2 `plum → grapes` |
| Kandydat modelu | `+5,8824 pp` whole-board accuracy, jeden błąd ≥`0,99` | decyzja `4e6ace22cc4d90ee230cc66ae4a3a306afa54c6b19f9e8d96544dbebee421578` | `rejected`, bez aktywacji |

Aktywny fingerprint modelu przed i po eksperymencie wynosi
`19e15e92591a3e1692a329e7c2fc9f4f3fe0f102bf623bebc20184615e48db64`.

## Aktywny pipeline

### Domyślny v18

Brak jawnego wyboru operatora przypina `historical_v18`. Historyczne joby,
checkpointy i manifesty pozostają odtwarzalne. Nie korzystają z trwałego
deferred geometrii komórek v20.

### Jawny v20

Tryb `verified_v19` przypina estymator wielopunktowej siatki 5 × 3, cropper v19,
progi i manifest benchmarku. Dla każdej pozycji planszy dopuszcza wyłącznie:

1. kompletną geometrię i dokładnie 15 source-direct cropów row-major, albo
2. trwały `image_board_geometry_pending` bez cropów i bez inferencji.

Nie istnieje fallback v19 → v18. Udane pozycje tej samej strony mogą przejść
dalej, a deferred pozostają częścią granicy `waiting_for_review`.

### Ręczny fallback

Reviewer pokazuje deferred w osobnym, bounded trybie. Operator ustawia cztery
narożniki zewnętrznej siatki symboli 5 × 3 i musi wygenerować aktualny podgląd
wszystkich 15 finalnych cropów. Dopiero zapis kompletnego wyniku używa modelu
przypiętego do źródłowego joba i atomowo tworzy zwykłą planszę oraz element
istniejącej kolejki review. Exact retry jest idempotentny, a późniejsza decyzja
człowieka lub istniejąca plansza zawsze wygrywa jako `superseded`.

## Rollback

- Nie przełączać trybu istniejącego joba w locie.
- Dla kolejnego joba wybrać `historical_v18`; tworzy to osobny snapshot i
  fingerprint bez mutowania wyników v20.
- Nie usuwać deferrals, cropów ani odrzuconego kandydata. Są audytowalnymi
  dowodami i nie wpływają na aktywny model.
- Odrzucony kandydat nie wymaga rollbacku aktywacji, ponieważ zdarzenie
  aktywacji nigdy nie powstało.

## Ograniczenia i następne warunki

- Automatyczne pokrycie v19 jest o `4,22 pp` niższe od bramki rollout'u.
- Dwanaście plansz z konfliktem ręcznej etykiety lub slotu pozostaje `OPEN` i
  nie może wejść do metryk ani treningu bez osobnej korekty danych.
- Kandydat modelu pozostaje nieaktywny mimo poprawy metryk globalnych, ponieważ
  bramka błędów wysokiej pewności jest fail-closed.
- Zmiana domyślnego trybu wymaga nowego, niezależnego benchmarku osiągającego
  co najmniej `98%` pokrycia bez regresji jakości i osobnej decyzji właściciela.
- Kolejna iteracja modelu wymaga osobnego zadania, nowej niezmiennej kohorty i
  przejścia pełnej bramki; nie wolno osłabiać progu po wyniku TASK 9.

## Dokumenty źródłowe

- `GRID_CROPPING_VS_SYMBOL_MODEL_DIAGNOSIS.md`
- `BOARD_CELL_GEOMETRY_V19_SHADOW_BENCHMARK.md`
- `V19_SYMBOL_RESIDUAL_COHORT.md`
- `V19_SYMBOL_MODEL_CANDIDATE.md`
