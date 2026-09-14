# TASK-0535 — podglądy korekt cropów dla wszystkich zakończonych katalogów

## Status

`done`

## Goal

Wszystkie zakończone, niezaakceptowane sesje cropów pod `D:\777`, które mają
automatyczne zdjęcia do poprawki i dostępny katalog źródłowy, otrzymują osobny,
wznawialny katalog `v12 board-buffer preview` bez zmiany bieżących katalogów
`cut`.

## Context

TASK-0534 potwierdził regułę pełnego 3×3 z dolnym buforem na 177 korektach
serii `248176 - 272016`. Operator zlecił zastosowanie tego samego przebiegu do
pozostałych skończonych, lecz niezaakceptowanych katalogów, wskazując
`128269 - 149634` jako przykład.

## Dependencies / entry conditions

- Commit `v0.10.267` udostępnia wersjonowany v12, wybór automatycznych korekt i
  niedestrukcyjny runner pojedynczego katalogu.
- Katalog `D:\777` jest dostępny do audytu, a nowe katalogi podglądowe mogą być
  tworzone obok istniejących `cut`.
- Istniejące źródła, katalogi `cut`, review i shardy pozostają tylko do odczytu.

## Recommended execution

`gpt-6-astra` z poziomem `high`, ponieważ zadanie wykonuje wielokatalogową
operację na rzeczywistych danych, wymaga jednoznacznej kwalifikacji stanu i
bezpiecznego wznowienia częściowego sukcesu. Dodatkowy review nie jest wymagany,
jeżeli używany jest bez zmian fingerprint i runner odebrany w TASK-0534.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0534-selected-crop-required-corrections-v12.md`

## Scope

- Dodać czysty audyt bezpośrednich katalogów `* cut` pod wskazanym katalogiem
  nadrzędnym.
- Zakwalifikować tylko sesje z kompletem wyników, bez pending/failures, bez
  końcowej akceptacji i z co najmniej jedną automatyczną korektą.
- Wymagać dokładnego katalogu źródłowego o nazwie powstałej przez usunięcie
  końcowego ` cut`.
- Dla każdej zakwalifikowanej sesji uruchomić istniejący runner do osobnego
  `<nazwa cut> v12 board-buffer preview`, sekwencyjnie i ze wznowieniem.
- Zapisać zbiorczy raport kwalifikacji i wyników bez mutowania źródeł.

## Out of scope

- Podmiana plików w katalogach `cut` albo zatwierdzenie review.
- Przetwarzanie sesji nieukończonych, zaakceptowanych, bez źródła lub mających
  wyłącznie ręczne wybory operatora.
- Zmiana detektora, fingerprintu, UI, API lub bazy danych.

## Acceptance criteria

- [x] Audyt raportuje każdą sesję `* cut` z jawnym statusem kwalifikacji i
      licznością wyników/korekt.
- [x] Przebieg nie zapisuje nic do źródła ani katalogu `cut`.
- [x] Każdy zakwalifikowany katalog ma osobny podgląd, raport i HTML.
- [x] Częściowy przebieg można wznowić bez przeliczenia lub nadpisania
      zweryfikowanych JPEG-ów.
- [x] Raport zbiorczy wskazuje per katalog liczbę automatów, wyników ręcznych i
      błędów; błąd jednej sesji nie ukrywa stanu pozostałych.
- [x] Test odtwarza kwalifikację accepted/incomplete/manual-only/eligible oraz
      deterministyczną kolejność katalogów.

## Technical notes

Źródłem prawdy są `inventory-v2.json`, `session-v2.json`, `review-v2.json` i
shardy `results/*.json`. Sesja jest przygotowana, gdy liczba unikalnych wyników
równa się liczbie wpisów inventory, `pendingOperation` jest puste i lista
`failures` jest pusta. Brak `review.completedAt` oznacza brak końcowej
akceptacji. Zakres algorytmu wyznacza
`selectedImageCropAutomaticCorrectionRecalculationFileNames`, więc operator-only
nie jest automatycznie przeliczany.

Runner zbiorczy wywołuje `runSelectedCropCorrectionPreview` dla jednej sesji na
raz. Istniejący katalog podglądu może zostać wyłącznie wznowiony po zgodności
meta i fingerprintu. Zbiorczy raport jest pochodną i nie zastępuje raportów
per katalog.

## Expected files

- Nowy: `scripts/preview_selected_crop_correction_directories.mjs` — audyt,
  kwalifikacja, sekwencyjny przebieg i raport zbiorczy.
- Nowy: `scripts/test/selected-crop-correction-directories.test.mjs` — test
  kwalifikacji i kolejności.
- Istniejący: `scripts/preview_selected_crop_corrections.mjs` — eksport
  bezpiecznego odczytu wejścia, jeżeli jest potrzebny bez dublowania logiki.
- Dokumentacja bieżącego stanu i wynik rzeczywistego przebiegu.

## Test cases

- Pełna sesja, `completedAt: null`, automatyczne ostrzeżenia i źródło → eligible.
- `completedAt` ustawione → accepted, bez uruchomienia.
- Brak wyników, pending albo failures → incomplete, bez uruchomienia.
- Tylko ręczny wpis w `correctionFileNames` → manual-only, bez uruchomienia.
- Brak dokładnego katalogu źródłowego → source-missing, bez uruchomienia.
- Dwa katalogi eligible → naturalna, deterministyczna kolejność i dwa odrębne
  outputy.
- Ponowienie → zgodne wyniki są weryfikowane i pomijane.

## Verification

```powershell
node --experimental-strip-types scripts/test/selected-crop-correction-directories.test.mjs
node --experimental-strip-types scripts/test/selected-crop-correction-preview.test.mjs
node --experimental-strip-types scripts/preview_selected_crop_correction_directories.mjs "D:\777"
```

Wynik rzeczywisty musi zawierać pełną tabelę kwalifikacji, katalog podglądu dla
każdej pozycji eligible, brak zmian checksum wejściowych i jawne błędy, jeżeli
którykolwiek przebieg nie osiągnie kompletności.

## Risks / open questions

- Łączna liczba korekt i czas są nieznane przed audytem; przebieg jest
  sekwencyjny, wznawialny i raportuje postęp per katalog.
- Katalogi bez źródłowego odpowiednika nie mogą być bezpiecznie odtworzone i
  pozostaną jawnie pominięte.
- Brak pytań blokujących: użytkownik wskazał regułę wyboru katalogów, a operacja
  tworzy tylko nowe, odseparowane wyniki.

## Outcome

### Changed

- Dodano bezpieczny audyt wszystkich bezpośrednich katalogów `* cut`, pełną
  klasyfikację stanu oraz sekwencyjne wywołanie odebranego runnera TASK-0534.
- Raport zbiorczy zapisuje wynik po każdej sesji, a CLI nie powtarza komunikatu
  postępu dla każdego już zweryfikowanego pliku przy wznowieniu.

### Verification results

- Testy kwalifikacji, naturalnej kolejności i osobnych outputów przeszły.
- `149626 - 177561`: 67/67, 63 automatyczne, 4 ręczne, 0 błędów; checksum
  wejścia `0443aca6c58baef683abbe7a949049ec83842959de24160f0a0bbe57957e75b3`.
- `248176 - 272016`: wznowione 177/177 automatycznych, 0 ręcznych, 0 błędów;
  checksum wejścia pozostał zgodny z TASK-0534.
- Oględziny czterech ręcznych wyników nowej serii potwierdziły pełne obrazy bez
  odcięcia plansz; nie przeszły bramek automatycznych.

### Not completed

- Nie przeliczono `128269 - 149634`, ponieważ zapis ma końcową akceptację,
  25 ręcznie poprawionych cropów i 0 nierozstrzygniętych korekt. Nie odtworzono
  też 26 sekwencji usuniętych późniejszym repair.
- Nieukończone sesje nie otrzymały przedwcześnie katalogów podglądu.

### Documentation updates

- Zaktualizowano wymagania, architekturę, raport jakości i `CURRENT_STATE.md`.

### Recommended next task

- Po zakończeniu kolejnych sesji ten sam batch można wznowić; utworzy podglądy
  wyłącznie dla nowo zakwalifikowanych katalogów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0535 — podglądy korekt cropów dla wszystkich zakończonych katalogów | gpt-6-astra | high | Wielokatalogowy przebieg na danych użytkownika wymaga deterministycznej kwalifikacji, wznowienia i weryfikacji braku mutacji wejścia. | Nie; o ile używany jest bez zmian odebrany fingerprint v12 i runner TASK-0534. |
