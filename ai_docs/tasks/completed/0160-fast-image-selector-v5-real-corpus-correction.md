---
title: TASK-0160 fast image selector v5 real corpus correction
status: done
release: "0.4"
last_updated: 2026-08-04
---

# TASK-0160 — Fast image selector v5 real-corpus correction

## Status

`done`

## Goal

Usunąć regresję wykrytą w rzeczywistym runie 32 079 zdjęć: nierozpoznawanie
czytelnych zakresów oraz nadmierne scalanie kolejnych stron w jedną grupę.

## Context

Run `e99b58b6-166f-4f9a-978e-bb601f3132d6` zakończył się bez błędu
technicznego, ale tylko 40 z 743 grup wybrał automatycznie. 703 grupy wymagały
review i zostały następnie jawnie oznaczone jako `missing_image`. W 700 grupach
pełna geometria była niekompletna, a w 692 fallback numerów zwrócił
`RANGE_LABEL_LATTICE_MISSING`.

Diagnostyka potwierdziła dwie niezależne przyczyny:

- stałe ROI oraz limit szerokości etykiety odcinają dolny rząd i odrzucają
  wielocyfrowe numery; czytelny zakres `271–279` daje tylko 5 kandydatów przy
  wymaganych 6, mimo że rozszerzony, digit-aware skan rozpoznaje 9/9 z wysokim
  confidence,
- temporalna reguła v3/v4 porównuje nowe zdjęcie ze wszystkimi top-k kotwicami
  i blokuje granicę, gdy pasuje ono do choć jednej starej kotwicy. Po pierwszym
  fałszywym scaleniu zróżnicowane top-k zwiększa ryzyko dalszego scalania.
  W realnym runie 71 grup miało ponad 100 źródeł, 15 ponad 200, a maksimum
  wyniosło 462 przy typowej serii 50–100 zdjęć jednego widoku.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`

## Scope

- dodać niezmienny manifest `fast-image-selector-v5`, zachowując dokładne
  wznowienie runów v2–v4 po ich fingerprintach,
- dodać digit-aware, szerszy i bounded fallback widocznych numerów obsługujący
  dolny rząd oraz numery do co najmniej sześciu cyfr,
- w pełnej weryfikacji v5 dopuścić istniejące guarded grid recovery; tani skan
  pozostaje bez zmian,
- oprzeć granicę v5 na kolejnych obserwacjach i istniejącym dwuklatkowym
  potwierdzeniu, aby stare top-k nie blokowało rzeczywistej zmiany strony,
- zachować soft-quality best available i bounded-gap inference v4 również w v5,
- dodać testy zgodności v2–v4, regresję zatrucia top-k oraz test wielocyfrowego
  dolnego rzędu,
- przed pełnym rerunem wykonać ograniczoną regresję na realnych przypadkach
  odrzuconych przez v4.

## Out of scope

- automatyczne przyjmowanie zdjęcia bez jednoznacznego zakresu,
- zmiana OCR symboli albo pełnego pipeline'u layoutów,
- ponowny run wszystkich 32 079 plików przed przejściem regresji ograniczonej,
- modyfikacja lub usunięcie historycznych decyzji `missing_image`.

## Acceptance criteria

- [x] run v2, v3 i v4 można wznowić z dotychczasowym zachowaniem i fingerprintem,
- [x] v5 rozpoznaje kontrolny rzeczywisty zakres `271–279`,
- [x] v5 nie scala dwóch kolejnych stron w regresji z podobną starą kotwicą,
- [x] jawnie nieczytelny/zasłonięty obraz nadal nie jest wybierany automatycznie,
- [x] liczba pełnych weryfikacji pozostaje bounded przez grupy × top-k,
- [x] skupione testy, Ruff i mypy zmienionych modułów przechodzą,
- [x] raport ograniczonej regresji realnych danych pozwala podjąć decyzję o
      pełnym rerunie albo wskazuje dalszy blocker.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/tests/test_fast_image_selector.py`
- `services/worker/tests/test_image_selection_adapters.py`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`

## Verification

Każda komenda ma limit maksymalnie 120 sekund. Pełny run 32 079 plików nie jest
częścią automatycznej weryfikacji tego zadania.

## Outcome

Dodano niezmienny `fast-image-selector-v5` o fingerprintcie
`ff75216bcd71f7f2484fef2c2868eda639152ba7efd98e00f23e08a89585e3fb`.
Fingerprinty v2, v3 i v4 pozostały bez zmian. Produkcyjny fallback v5 obejmuje
dolny rząd i szerokie numery, ogranicza wejście OCR do 36 kandydatów oraz w
pełnej weryfikacji dopuszcza guarded grid recovery. Grupowanie v5 porównuje
kolejne obserwacje i utrzymuje dwuklatkowe potwierdzenie również podczas
stopniowej zmiany kadru.

Ograniczona regresja rzeczywistych danych:

- kontrolne zdjęcie `271–279`: 9 zgodnych etykiet, confidence `0,98333`,
- próbka 29 grup odrzuconych przez v4: v4 `1/29`, v5 `24/29`,
- pierwsze 160 uporządkowanych zdjęć: sześć automatycznych zakresów `1–9`,
  `10–18`, `19–27`, `28–36`, `37–45`, `46–54`; jeden końcowy niepełny obraz
  pozostał manualny,
- pełny eksperyment 500 zdjęć został przerwany przez jawny timeout 120 s; nie
  pozostał osierocony proces i nie zastępuje on produkcyjnego rerunu.

Pełny rerun 32 079 zdjęć pozostaje świadomym następnym krokiem operatorskim.
Nie modyfikowano historycznego wyniku v4 ani decyzji `missing_image`.
