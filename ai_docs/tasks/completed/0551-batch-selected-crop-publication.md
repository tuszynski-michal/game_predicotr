---
title: Paczkowa trwała publikacja cropów
status: done
last_updated: 2026-09-15
---

# TASK-0551 — Paczkowa trwała publikacja cropów

## Status

`done`

## Goal

Skrócić zapis automatycznie przygotowanych cropów przez jeden odporny na restart journal i jeden zapis każdego zmienionego sharda na paczkę, zachowując kontrolę SHA-256 każdego JPEG-a.

## Context

Pomiar katalogu `248176 - 272016 cut` wykazał około 12 zdjęć/min przy czterech równoległych analizach. Analiza paczki trwa kilka sekund, natomiast publikacja każdego wyniku osobno wykonuje dwa zapisy session journalu i zapis całego sharda, przez co trwa około 4–5 sekund na zdjęcie.

## Dependencies / entry conditions

- TASK-0547 zapewnia równoległą analizę paczek po cztery i uporządkowaną publikację.
- Snapshot v2, checksumy, shardy oraz blokada jednego writera pozostają źródłem prawdy.
- Otwarta sesja użytkownika nie jest przeładowywana ani modyfikowana przez testy.

## Recommended execution

`gpt-6-astra` z reasoning `high`, ponieważ zmiana dotyczy journalu odpornego na restart i musi poprawnie odtworzyć częściowo zapisaną paczkę.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/tasks/completed/0547-parallel-selected-crop-preparation.md`

## Scope

- Rozszerzyć zgodny wstecz journal sesji v2 o opcjonalną paczkę operacji oczekujących.
- Przygotować checksumy i decyzje zapisu całej paczki przed jednym zapisem intencji.
- Zapisać i zweryfikować każdy JPEG, następnie zapisać każdy dotknięty shard raz i zakończyć paczkę jednym zapisem sesji.
- Odtwarzać po restarcie osobno brakujące, zgodne i konfliktowe wyniki paczki.
- Zachować pojedynczy journal dla ręcznej korekty i pozostałych istniejących konsumentów.
- Dodać pomiar fazy publikacji paczki do istniejącej telemetrii oraz testy regresyjne.

## Out of scope

- Zwiększenie liczby workerów ponad cztery.
- Zmiana detektora, cropów, JPEG quality, fingerprintu albo zasad review.
- Zmiana plików w katalogu użytkownika podczas implementacji i testów.

## Acceptance criteria

- [x] Paczka czterech poprawnych wyników zapisuje session journal dwa razy łącznie, a nie osiem razy.
- [x] Każdy JPEG jest nadal odczytany po zapisie i zweryfikowany SHA-256.
- [x] Shard obejmujący kilka wyników jest zapisany raz na paczkę.
- [x] Restart po zapisaniu części JPEG-ów finalizuje zgodne wyniki, pozostawia brakujące w kolejce i kieruje konflikt do poprawy.
- [x] Pojedynczy zapis ręczny zachowuje dotychczasowy kontrakt.
- [x] Testy core i Admina, typecheck, lint oraz build przechodzą.

## Technical notes

Pole `pendingBatch` jest zgodnym rozszerzeniem schema v2: historyczny brak pola jest normalizowany do `null`. Intencja zawiera istniejące, checksumowane `SelectedImageCropPendingOperation`. Wyniki są publikowane w kolejności inwentarza, a `pendingOperation` pozostaje wyłącznie dla pojedynczych zapisów. Recovery nie ufa samemu istnieniu JPEG-a: porównuje jego SHA-256 z intencją i dopiero wtedy materializuje wynik w shardzie.

## Expected files

- Istniejący: `packages/manual-image-selection-core/src/crop-session.ts` — stan paczki i projekcja statusu.
- Istniejący: `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts` — zapis i recovery paczki.
- Istniejące testy core i Admina dotyczące sesji, storage oraz równoległości.
- Dokumentacja wymagań, architektury i bieżącego stanu.

## Test cases

- Cztery wyniki w jednym shardzie → dwa zapisy session i jeden zapis sharda.
- Paczka przecina granicę shardów → po jednym zapisie każdego z dwóch shardów.
- Restart: dwa zgodne JPEG-i, jeden brakujący i jeden obcy → zgodne sfinalizowane, brakujący ponawialny, obcy zaznaczony do poprawy.
- Historyczna sesja bez `pendingBatch` → normalizacja do `null` bez reprocessu.
- Ręczna korekta → nadal pojedyncza intencja i kontrolny odczyt SHA-256.

## Verification

```powershell
node --experimental-strip-types --test --test-isolation=none packages/manual-image-selection-core/test/selected-image-crop-session.test.mjs apps/admin/test/selected-image-crop-storage-contract.test.mjs apps/admin/test/selected-image-crop-parallelism.test.mjs
npm test --workspace @game-predictor/manual-image-selection-core
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

## Risks / open questions

- Awaria między zapisami shardów a finalnym session musi być idempotentna; recovery pomija już zgodnie sfinalizowany wynik zamiast traktować go jako stale replacement.
- Równoległy zapis JPEG-ów pozostaje ograniczony wielkością bieżącej paczki czterech.

## Outcome

### Changed

- Session v2 otrzymała zgodne wstecz pole `pendingBatch`; historyczny brak pola
  jest normalizowany do `null`.
- Automatyczne wyniki jednej paczki są renderowane i hashowane przed wspólną
  intencją, po czym JPEG-i są zapisywane równolegle, a każdy dotknięty shard i
  końcowa sesja tylko raz.
- Czyste recovery finalizuje zgodne JPEG-i, zostawia brakujące w kolejce i
  kieruje zmienione bajty do review. Ponowienie po zapisaniu sharda jest
  idempotentne.
- Automatyczne przygotowanie używa paczkowego writera; pojedyncza ręczna
  korekta zachowuje dotychczasowy journal.

### Verification results

- Testy skoncentrowane: 39/39.
- Pełne testy `manual-image-selection-core`: 102/102.
- Pełne testy Admina: 487/487.
- Typecheck core i Admina, lint Admina oraz build core przeszły.
- Produkcyjny build Admina przeszedł; po kompilacji piaskownica blokowała
  proces pomocniczy Next.js (`spawn EPERM`), więc ten sam build został
  powtórzony poza piaskownicą i zakończył się poprawnie.

### Not completed

- Nie uruchamiano zapisu ani benchmarku na aktywnym katalogu użytkownika, aby
  nie ingerować w trwającą sesję. Pomiar rzeczywistego tempa można wykonać po
  przeładowaniu karty, gdy zacznie ona korzystać z nowego kodu.

### Documentation updates

- Zaktualizowano wymagania, architekturę i `CURRENT_STATE.md` o kontrakt
  publikacji oraz recovery paczki.

### Recommended next task

- Ograniczony pomiar tempa i czasu zapisu na istniejącym katalogu po
  przeładowaniu Admina, bez zwiększania liczby workerów.

## Plan implementacji

1. Rozszerzyć snapshot sesji i czystą logikę stanu o zgodną wstecz intencję paczki.
2. Dodać paczkowy writer oraz idempotentne recovery bez osłabienia checksum i blokady jednego writera.
3. Podłączyć writer do istniejącej paczki czterech analiz i uzupełnić telemetrię.
4. Dodać regresje restartu oraz liczby zapisów, wykonać pełne kontrole i zamknąć zadanie osobnym commitem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0551 — paczkowa trwała publikacja cropów | gpt-6-astra | high | Journal paczki musi zachować kolejność, checksumy i idempotentne recovery po awarii w dowolnym kroku. | Nie; o ile pojedynczy writer i kontrolny odczyt każdego JPEG-a pozostają bez zmian. |
