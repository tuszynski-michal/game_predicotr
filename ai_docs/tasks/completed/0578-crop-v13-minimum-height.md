---
title: V13 minimalnej wysokości cropa siatki
status: done
last_updated: 2026-09-17
---

# TASK-0578 — V13 minimalnej wysokości cropa siatki

## Status

`in_progress`

## Goal

Nowy aktywny silnik v13 rozszerza propozycję v12 tak, aby wynikowy pas siatki nigdy nie był niższy od proporcjonalnej, zmierzonej granicy bezpiecznej.

## Context

Referencyjny katalog poprawnych JPEG-ów `200575 - 222912 cut` zawiera 2482 pliki o szerokości 1080 px. Wysokości cropów wynoszą 402–714 px; średnia dolnych 5% (125 plików) to 422,96 px. Zastosowanie 5% bufora daje dolną granicę 401 px przy szerokości 1080 px. Średnia całej populacji (501,38 px) nie może być progiem, ponieważ wykluczałaby poprawne, niższe cropy z katalogu referencyjnego.

## Dependencies / entry conditions

- TASK-0479, TASK-0536 i TASK-0553 dostarczają aktywny pipeline v12 oraz jego wersjonowany fingerprint.
- Pomiar referencyjny wykonano wyłącznie odczytowo 2026-09-17; katalog referencyjny nie jest zależnością runtime ani nie będzie modyfikowany.
- Wymaganie użytkownika jednoznacznie upoważnia do aktywacji v13, ale nie do ponownego przetwarzania istniejących katalogów JPEG.

## Recommended execution

`gpt-5.6-sol`, reasoning `xhigh`. Zmiana dotyka deterministycznej geometrii cropa, trwałej proweniencji i granicy worker–klient, więc wymaga pełnego przeglądu kompatybilności v12/v13. Niezależny review `gpt-6-astra`, reasoning `high` jest wymagany, jeśli testy wykryją rozbieżność między cropem workera a fallbackiem głównego wątku.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Dodać wersjonowaną nakładkę v13 na v12, z fingerprintem obejmującym dane referencyjne, wzór progu i strategię rozszerzania.
- Wyliczać minimum jako `ceil(szerokość × 401 / 1080)`; 401 px to `floor(422,96 × 0,95)`.
- Gdy propozycja jest za niska, rozszerzać ją symetrycznie w granicach źródła; przy krawędzi przesunąć całą wymaganą nadwyżkę na dostępną stronę. Gdy źródło samo jest niższe od progu, zachować całe źródło.
- Aktywować v13 dla nowych pustych sesji i jawnego przeliczenia; sesje v12 zachowują przypiętą politykę aż do jawnego przeliczenia.
- Zachować v12 jako poprawnie odczytywaną politykę historyczną oraz tę samą rejestrację kotwic i retry.

## Out of scope

- Ponowne przycinanie albo nadpisywanie JPEG-ów użytkownika.
- Zmiana wykrywania plansz, cech rejestracji, limitu maksymalnej wysokości lub procedur ręcznej korekty.
- Zmiana katalogu referencyjnego, manifestów istniejących sesji i schematu manifestu.

## Acceptance criteria

- [x] V13 ma własny identyfikator polityki i fingerprint zależny od bieżącego kontraktu v12 oraz pomiaru referencyjnego.
- [x] Crop v13 krótszy niż 401 px przy szerokości 1080 px jest rozszerzany co najmniej do 401 px bez wyjścia poza obraz.
- [x] Próg jest proporcjonalny do szerokości i działa przy krawędzi obrazu oraz przy źródle niższym od progu.
- [x] Walidator propozycji odrzuca utrwalony v13 z nieosiągniętą możliwą granicą.
- [x] Worker i fallback przeglądarkowy publikują ten sam v13; retry kotwic działa dla v12 i v13.
- [x] Nowe puste sesje przypinają v13, zaś rozpoczęte sesje v12 nie są automatycznie przeliczane.
- [x] Testy pakietu core i Admina oraz typecheck przechodzą bez nowych błędów.

## Technical notes

Źródłem prawdy dla progu jest wersjonowana konfiguracja v13, a nie ścieżka lokalnego katalogu. V13 najpierw wykonuje niezmieniony pipeline v12, następnie rozszerza tylko `topY`/`bottomY`; nie zwęża wyniku i nie zmienia szerokości, dowodu strukturalnego ani rejestracji. Rozszerzenie jest deterministyczne: najpierw dzieli brakujące piksele po równo, potem wykorzystuje przeciwną stronę przy krawędzi.

Przykład: crop `topY=600`, `bottomY=950`, `width=1080`, `height=1920` ma 350 px, więc v13 zapisuje 401 px wokół środka. Crop `0–350` rozszerza tylko dół do `0–401`. Crop źródła 1080×380 pozostaje `0–380`, ponieważ nie utracił żadnej części obrazu.

Granica klient–worker wymaga dokładnego fingerprintu v13. Odczyt historii v12 pozostaje zgodny z istniejącymi readerami; jawne przeliczenie przypina aktywny v13.

## Expected files

- Istniejące: `packages/manual-image-selection-core/src/crop-preparation.ts`, `crop.ts`, `auto-crop.ts`, `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-worker.ts`, `selected-image-crop-worker-client.ts`, `selected-image-crop-storage.ts`.
- Nowe: `packages/manual-image-selection-core/src/auto-crop-v13-minimum-height.ts` i test kontraktu v13.
- Istniejące: dokumentacja ręcznej selekcji oraz `CURRENT_STATE.md`.

## Test cases

- Referencyjne 1080 px → minimalna wysokość 401 px.
- Crop poniżej progu pośrodku → symetryczne rozszerzenie bez utraty istniejących pikseli.
- Crop przy górnej/dolnej krawędzi → przesunięte rozszerzenie w granicach źródła.
- Źródło niższe od wymaganego minimum → pełna wysokość źródła bez błędu.
- V13 z niedozwolenie niskim persisted cropem → walidator odrzuca.
- V12 zachowuje fingerprint, możliwość odczytu i retry; nowy snapshot/recalculation używa v13.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr
pnpm --filter @game-predictor/manual-image-selection-core test
pnpm --filter @game-predictor/manual-image-selection-core typecheck
pnpm --filter @game-predictor/admin test
pnpm --filter @game-predictor/admin lint
pnpm --filter @game-predictor/admin typecheck
```

Każda komenda ma limit 120 sekund; zielony wynik oraz ręczny przegląd kontraktów v12/v13 kończą task.

## Risks / open questions

- Próg referencyjny chroni przed nadmiernym zwężeniem, lecz nie jest semantycznym dowodem obecności konkretnego rzędu; rejestracja v12 i ręczny review pozostają bramkami jakości.
- Pełny obraz źródłowy niższy od progu jest jedynym fizycznie możliwym wynikiem; v13 nie skaluje ani nie generuje pikseli.

## Outcome

### Changed

- Dodano v13 jako wersjonowaną nakładkę na v12, z proporcjonalną minimalną
  wysokością cropa i rozszerzaniem tylko w granicach źródła.
- Aktywna polityka nowych sesji oraz jawnego przeliczenia wskazuje v13; v12
  pozostaje obsługiwany dla historii i retry.
- Worker, fallback, walidator trwałej propozycji i testy kontraktowe znają v13.

### Verification results

- Core typecheck — zaliczony.
- Admin typecheck — zaliczony.
- Bezpośrednie uruchomienie testów v13/core — 10/10 zaliczone.
- Bezpośrednie uruchomienie testów worker/storage Admina — 24/24 zaliczone.
- Pełne `node --test` nie jest dostępne w sandboxie, ponieważ środowisko
  blokuje tworzenie procesów potomnych (`spawn EPERM`). Polecenia `pnpm` nie
  wystartowały z powodu odrzuconego pobrania brakującego Prettiera z rejestru.

### Not completed

- Nie uruchamiano v13 na katalogach JPEG użytkownika.

### Documentation updates

- Zaktualizowano wymagania, architekturę i bieżący stan o kontrakt v13.

### Recommended next task

- Osobne, jawne polecenie może uruchomić v13 na wskazanym katalogu albo
  przygotować preview bez nadpisywania istniejących JPEG-ów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0578 — V13 minimalnej wysokości cropa siatki | gpt-5.6-sol | xhigh | Wersjonowana zmiana geometrii obejmuje pipeline core, trwałe dane i worker. | gpt-6-astra / high, jeśli wystąpi rozbieżność workera z fallbackiem lub testy kontraktu nie przejdą. |
