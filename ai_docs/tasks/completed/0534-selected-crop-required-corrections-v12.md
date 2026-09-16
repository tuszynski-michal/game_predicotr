# TASK-0534 — przeliczenie automatycznych korekt cropów przez v12

## Status

`done`

## Goal

Jawna akcja ponownego przeliczenia kieruje automatycznie wymagane korekty przez
detektor v12, a odseparowany przebieg na 177 pozycjach katalogu
`248176 - 272016 cut` tworzy bezpieczny do obejrzenia wynik bez nadpisania
dotychczasowych plików.

## Context

Sesja v10 przygotowała 2648 cropów i zakwalifikowała 177 do korekty: 111 przez
niepotwierdzoną dolną granicę `crop_too_short`, 47 przez zachowawczą rozbieżność
detektorów oraz 19 przez `safe_wide`. Kod v12 potrafi wyznaczyć pełny pas 3×3
strukturalnie albo przenieść czteropunktowy obrys z pobliskiej silnej kotwicy,
lecz obecna akcja przeliczenia zachowuje przypięte v10 i wyklucza wszystkie
automatycznie wymagane korekty. To jest sprzeczne z nazwą akcji i opisem trybu
testowego w wymaganiach.

## Dependencies / entry conditions

- Warianty v11/v12 i ich walidacja fail-closed z TASK-0472/TASK-0479 są obecne.
- Użytkownik jawnie zlecił poprawę algorytmu i przeliczenie dokładnie zapisanej
  kolejki 177 zdjęć.
- Katalog źródłowy i stan sesji są dostępne na `D:\777`; istniejący katalog
  `cut` pozostaje źródłem prawdy i nie będzie nadpisywany przez odbiór.

## Recommended execution

`gpt-6-astra` z poziomem `high`, ponieważ zmiana dotyczy trwałego journalu,
ochrony ręcznych decyzji i jakości obrazu na rzeczywistym zbiorze. Dodatkowy
review jest wymagany tylko wtedy, gdy poprawka miałaby osłabić bramki v12 albo
aktywować v12 dla wszystkich nowych katalogów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/quality/SELECTED_CROP_V11_REGRESSIONS.md`
- `ai_docs/tasks/0472-crop-v11-acceptance.md`

## Scope

- Rozdzielić automatycznie wymagane korekty od pozycji oznaczonych wyłącznie
  ręcznie i dopuścić pierwszą grupę do jawnego przeliczenia.
- Przy jawnej akcji przypiąć v12, zachowując ręcznie poprawione, przejrzane i
  zaakceptowane wyniki.
- Udoskonalić dobór pobliskiej silnej kotwicy lub bezpieczny fallback v12 na
  podstawie zmierzonych przyczyn z tej serii, bez osłabiania walidacji.
- Uznać kompletne 3×3 za wystarczający dowód cropa i przy braku pełnych pasów
  numerów dodać wersjonowany dolny bufor; taki wynik nie może być kotwicą.
- Dodać ograniczony, wznawialny runner podglądu dla zamkniętej listy korekt.
- Przetworzyć 177 źródeł do nowego katalogu odbiorczego i zapisać raport z
  metodą, granicami, błędami i pozycjami nadal wymagającymi ręcznej korekty.

## Out of scope

- Nadpisywanie obecnego katalogu `248176 - 272016 cut` lub jego manifestów.
- Automatyczne uznanie wyników za zaakceptowane przez operatora.
- Włączenie v12 jako domyślnej polityki nowych sesji przed osobną bramką jakości.
- Zmiany importu, geometrii plansz, OCR, API i bazy danych.

## Acceptance criteria

- [x] Jawne przeliczenie zmienia przypiętą politykę v10 na v12.
- [x] Przelicza automatyczne obowiązkowe korekty i nie rusza cropów oznaczonych
      wyłącznie ręcznie, ręcznie poprawionych, przejrzanych ani zaakceptowanych.
- [x] Słaba rejestracja nadal daje obowiązek korekty zamiast ciasnego cropa.
- [x] Dziewięć wykrytych plansz daje automatyczny crop z dolnym buforem także
      bez osobnego potwierdzenia numerów; niepełny układ nadal kończy szeroko.
- [x] Crop oparty na buforze nie jest używany jako kotwica dla innego zdjęcia.
- [x] Dokładnie 177 zapisanych nazw zostaje odczytanych z istniejącego review i
      każda otrzymuje wynik albo jawny izolowany błąd.
- [x] Wyniki są zapisane poza istniejącym katalogiem `cut`, z raportem i
      checksumami umożliwiającymi wznowienie oraz przegląd.
- [x] Testy core i Admina odtwarzają migrację v10→v12, zakres kandydatów i
      ochronę ręcznych decyzji.

## Technical notes

Źródłem zamkniętej listy jest `review-v2.json` wraz z shardami wyników. Nowa
czysta selekcja domenowa wybiera wyłącznie nierozstrzygnięte wyniki, dla których
`selectedImageCropReviewReason(...)` zwraca powód. Sam wpis w
`correctionFileNames` bez takiego dowodu pozostaje decyzją operatora i jest
chroniony. Recalculator wyznacza listę przed zmianą polityki, przypina v12,
zapisuje każdy JPEG przez istniejący journal i ponownie synchronizuje obowiązek
korekty z nową proweniencją.

Runner odbiorczy czyta 177 nazw, skanuje sąsiadujące źródła tylko w celu
znalezienia zwalidowanej kotwicy strukturalnej i zapisuje wyłącznie wyniki tej
listy. Rejestracja musi przejść dotychczasowe limity dopasowań, ćwiartek,
residualu, skali i konfliktu ze strukturą. Brak dowodu zapisuje szeroki wynik
oznaczony jako manualny. Katalog odbiorczy ma nową nazwę i nie jest wejściem
bieżącego importu.

Decyzja D-381 zastępuje osobną bramkę dziewięciu etykiet dla bezpośredniego
układu 3×3. `complete_layout_board_buffer` używa 65% mediany wysokości planszy
poniżej dolnego rzędu. Fingerprint v12 zawiera fingerprint v11, dlatego zmiana
reguły strukturalnej wymusza zgodny replay. Kotwice zachowują ostrzejszy wymóg
dziewięciu plansz i dziewięciu etykiet.

## Expected files

- Istniejący: `packages/manual-image-selection-core/src/crop-session.ts` —
  selekcja automatycznych korekt do przeliczenia.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts`
  — jawne przypięcie v12 i przeliczenie zamkniętej listy.
- Istniejący: `packages/manual-image-selection-core/src/auto-crop-v12-registration.ts`
  lub `crop-preparation.ts` — tylko jeżeli pomiar wykaże konkretną lukę.
- Istniejący: `packages/manual-image-selection-core/src/auto-crop-v11-boundaries.ts`
  — reguła pełnego 3×3 i wersjonowany dolny bufor.
- Nowy: `scripts/preview_selected_crop_corrections.mjs` — wznawialny,
  niedestrukcyjny przebieg i raport.
- Istniejące testy core/Admin oraz dokumentacja wskazana wyżej.

## Test cases

- Sesja v10 z automatycznym `crop_too_short` → nazwa jest kandydatem, polityka
  po jawnej akcji to v12.
- Crop oznaczony przez operatora bez automatycznego powodu → brak na liście.
- Crop przejrzany, ręcznie poprawiony lub jawnie zaakceptowany → brak na liście.
- Rejestracja o zbyt małej liczbie inlierów albo konflikcie ze strukturą → pełny
  obraz i trwały obowiązek korekty.
- Pełne 3×3 bez kompletu pasów numerów → automatyczny crop z buforem, lecz brak
  kwalifikacji jako kotwica dla innych źródeł.
- Restart runnera po częściowym zapisie → istniejący zgodny wynik jest
  zweryfikowany i pominięty; obcy wynik blokuje nadpisanie.
- Rzeczywista lista → 177 unikalnych nazw, 177 wyników lub jawnych błędów,
  brak zmian w checksumach dotychczasowego katalogu `cut`.

## Verification

```powershell
pnpm --filter @game-predictor/manual-image-selection-core test
pnpm --filter @game-predictor/manual-image-selection-core typecheck
node --experimental-strip-types --test apps/admin/test/selected-image-crop-storage-contract.test.mjs
pnpm --filter @game-predictor/admin typecheck
node --experimental-strip-types scripts/preview_selected_crop_corrections.mjs "D:\777\248176 - 272016" "D:\777\248176 - 272016 cut" "D:\777\248176 - 272016 cut v12 board-buffer preview"
```

Zaliczenie wymaga zgodności liczby 177, braku izolowanych błędów zapisu,
raportu metod oraz ręcznej listy przypadków nierozwiązanych. Wynik jakości na
tym ujawnionym zbiorze jest materiałem rozwojowym, nie niezależnym holdoutem.

## Risks / open questions

- Seria zawiera skoki kadru; kotwica musi być dobierana po dowodzie obrazu, a
  nie tylko po numerze pliku.
- Rzeczywiste uruchomienie może trwać dłużej niż 120 sekund; runner ma trwałe
  checkpointy i będzie uruchomiony jako kontrolowany proces z ograniczonym
  pollingiem.
- Brak otwartych pytań blokujących: nowy katalog podglądu zachowuje dane
  użytkownika i umożliwia ocenę przed jakąkolwiek podmianą.

## Outcome

### Changed

- Dodano odrębną selekcję automatycznych ostrzeżeń, akcję UI i jawne przejście
  rozpoczętej sesji z v10 na v12.
- Drugi przebieg v12 próbuje deterministycznie najwyżej trzy najbliższe silne
  kotwice zamiast kończyć po jednej niedopasowanej.
- Pełne 3×3 bez kompletu wykrytych numerów kończy się automatycznym cropem z
  buforem 65% mediany wysokości planszy. Wynik nie jest kotwicą rejestracji.
- Fingerprint v12 zależy od fingerprintu v11 i unieważnia zapis po zmianie
  reguły strukturalnej.
- Dodano wznawialny runner z journalem, checksumami, shardami, raportem i
  lokalną stroną przeglądu.

### Verification results

- Pełny zestaw testów core, test wznowienia runnera, 20 kontraktów Admina,
  typecheck core/Admin, właściwy lint oraz produkcyjny build Admina przeszły.
- Rzeczywisty przebieg: 177/177 automatycznych, 166 strukturalnych (35 z
  buforem), 11 rejestrowanych, 0 ręcznych i 0 błędów. Stan wejściowy pozostał
  zgodny z checksumą
  `79e622a48ef681014a273e2731507c1cd3e951f7ff59514fc1763c0592557f57`.
- Oględziny obu wcześniejszych wyjątków i skrajnych wysokości cropów z buforem
  potwierdziły zachowanie wszystkich plansz i numerów.

### Not completed

- Nie aktywowano v12 jako domyślnej polityki nowych sesji i nie podmieniono
  obecnego katalogu `cut`.
- Nie uznano 177 wyników za decyzje operatora; są osobnym podglądem odbiorczym.

### Documentation updates

- Zaktualizowano wymagania, architekturę, raport jakości i `CURRENT_STATE.md`.

### Recommended next task

- Po wizualnym odbiorze podglądu operator może osobno zlecić podmianę 177
  zaakceptowanych cropów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0534 — przeliczenie automatycznych korekt cropów przez v12 | gpt-6-astra | high | Zmiana łączy selekcję trwałego stanu, bezpieczny zapis plików i ocenę algorytmu na rzeczywistym zbiorze. | Nie; wymagany gpt-6-astra/high przed osłabieniem bramek albo domyślną aktywacją v12. |
