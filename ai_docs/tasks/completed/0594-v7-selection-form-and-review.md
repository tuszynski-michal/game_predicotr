---
title: V7 selection form and durable neighbour review
status: done
last_updated: 2026-09-21
---

# TASK-0594 — formularz V7 i trwały podgląd sąsiadów

## Status

`done`

## Goal

Nowe uruchomienie z workspace'u półautomatu ma tworzyć wyłącznie kanoniczne
żądanie `v7_selection` z formularza pełnych stron, a interfejs ma trwałe i
niezależne pozycje skanu, sekwencji oraz podglądu operatora.

## Context

T06 zablokował start V7 po stronie API aż do odbioru T12. T10 musi mimo to
zastąpić konfigurator nowych runów bez omijania tej bramki i bez naruszania
historycznego workflowu `selection` oraz jego lokalnego outputu. Formularz ma
usunąć niejednoznaczność pojedynczego numeru/range'u oraz pokazać docelowy
katalog `<źródło> cut`, który jest własnością writera T08/T09, a nie uchwytem
File System Access w przeglądarce.

## Dependencies / entry conditions

- T01 określił pełne strony 3×3, normalizację `10` do `10–18`, rosnący jako
  domyślny kierunek i trzy style obramowania.
- T06 udostępnił addytywny payload `v7` i `capabilities.v7`, obecnie z
  `startEnabled=false`; backend ma odrzucić próbę przed utworzeniem runu.
- T07–T09 dostarczają trwałe kursory/run-state i writer, lecz nie wystawiają
  nowego outputu przez API. T10 nie może udawać, że browserowy writer legacy
  jest writerem V7.
- Zakładam bezpieczny default produktu: `semi_automatic` i `top_and_sides`.
  `automatic` pozostaje jawną opcją, lecz jest tak samo zablokowany do T12.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`. Zadanie wymaga kontrolowanej zmiany
istniejącego React workflowu z historycznym lokalnym outputem oraz
deterministycznej normalizacji formularza. Po implementacji obowiązuje review
`gpt-6-astra`, reasoning `medium`; znaleziony problem musi zostać poprawiony i
ponownie zweryfikowany przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/tasks/0594-v7-selection-form-and-review.md`

## Scope

- Zastąpić konfigurację **nowych** runów w `SemiAutomaticSelectionWorkspace`
  formularzem V7: katalog źródłowy, tryb, kierunek (domyślnie rosnący),
  pierwszy i ostatni zakres, liczbę oczekiwanych grup oraz styl ramki.
- Przyjmować `10` i `10-18`; odrzucić zakres niepełny, odwrócony i kierunek
  sprzeczny z kolejnością pierwszego/ostatniego zakresu. Wysłanie do API ma
  zawsze używać rosnących granic liczbowych, a `direction` tylko kolejności
  stron w nagraniu.
- Budować `mode: 'v7_selection'` z payloadem `v7`; nie przekazywać wariantu
  recognizera legacy jako substytutu lokalizatora/calibracji V7.
- Pokazać `capabilities.v7.reason`, zablokować start, gdy `startEnabled` jest
  fałszem, i nie wywołać select/create API po kliknięciu zablokowanego startu.
- Pokazać wyprowadzony wynik `<źródło> cut`, bez otwierania browserowego
  pickera katalogu docelowego dla V7.
- Rozszerzyć trwały stan UI o `scanSourceIndex`, `sequenceExpectedIndex` i
  `viewSourceIndex`; przywracać konkretny run, aktywny zakres i oglądane
  źródło. Nawigacja w podglądzie nie zmienia zaznaczenia ani kursora workera.
- Zachować historyczne runy i istniejący `SemiAutomaticSelectionReviewWorkspace`
  razem z jego File System Access outputem; nie migrować ich rekordów.

## Out of scope

- Odblokowanie bramki V7, uruchomienie OCR, zmiana worker handlera lub
  publikacja JPEG-a — należą do T11/T12 i pozostają zablokowane do odbioru.
- Endpointy dla ręcznych decyzji T09. Browserowy legacy output nie może zostać
  podłączony do V7 jako obejście wspólnego journalu writera.
- Nowe usługi, Redis/Celery, upload JPEG-ów lub przechowywanie obrazów w
  IndexedDB.

## Acceptance criteria

- [ ] Formularz domyślnie ma `Rosnąco`, `Półautomat` i `Góra oraz boki`.
- [ ] `1–9 → 19–27` rosnąco oraz `19–27 → 1–9` malejąco pokazują trzy grupy
  i wysyłają identyczne rosnące granice `1, 27` z różnym kierunkiem.
- [ ] Samo `10` normalizuje się do pełnej strony `10–18`; `10–17`, `18–10`,
  niecałkowite liczby i niezgodny kierunek nie dają żądania API.
- [ ] V7 request zawiera jedynie `mode=v7_selection`, token źródła, granice,
  kierunek oraz dozwolone `v7.mode`/`v7.borderStyle`; historyczny request
  `selection` pozostaje bez `v7`.
- [ ] Bramka backendu pozostaje widoczna i skuteczna w UI; gdy jest blocked,
  start nie tworzy runu ani nie otwiera katalogu źródłowego/outputu.
- [ ] Local UI state po odświeżeniu odtwarza oddzielnie indeks skanu,
  sekwencji i dokładnego oglądanego źródła; jego zmiana nie zmienia pozostałych.
- [ ] Istniejące testy workflowu legacy nadal przechodzą.

## Technical notes

Dodaj czystą funkcję normalizacji granic formularza, niezależną od Reacta.
Wejście to dwie tekstowe granice i kierunek; wynik jest kanonicznym payloadem
albo stabilnym kodem błędu. Pojedynczy numer jest początkiem strony, a zakres
musi mieć dokładnie dziewięć kolejnych liczb. Przykład: `19-27`, `1-9`,
`descending` → `{ firstSequenceNumber: 1, lastSequenceNumber: 27,
expectedRangeCount: 3 }`; `descending` nie odwraca ani nazwy `seq_*`, ani
liczb w stronie.

Rozszerz istniejący rekord IndexedDB addytywnie: validator ma akceptować
historyczny format i nadawać mu bezpieczne wartości `null`, natomiast nowy
zapis tworzy wszystkie trzy kursory. Nie zapisuj Blobów, JPEG-ów, całego
manifestu ani automatycznej decyzji użytkownika w local storage.

Historyczny review komponent otrzymuje nadal wyłącznie run bez
`workflowMode='v7_selection'`. V7 ma co najwyżej odczytowy status/preview;
żadna kontrolka nie może uruchomić istniejącego browserowego outputu. Gdy API
nie ujawnia jeszcze danych quality/warnings T04, UI ma nie wyświetlać fikcyjnej
listy warningów. T12/T11 będą miały obowiązek podłączyć pełny runtime po
odbiorze.

## Expected files

- Istniejące: `apps/admin/src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx` — nowe runy V7, zachowany historyczny review.
- Istniejące: `apps/admin/src/features/semi-automatic-image-selection/semi-automatic-selection-actions.ts` — kanoniczne utworzenie requestu V7.
- Istniejące: `apps/admin/src/features/semi-automatic-image-selection/semi-automatic-selection-output-storage.ts` — addytywne kursory local UI.
- Istniejące: `apps/admin/test/semi-automatic-selection-workspace-contract.test.mjs` — regresje i kontrakt UI.
- Nowe: `apps/admin/src/features/semi-automatic-image-selection/v7-selection-form.ts` — czysta normalizacja/payload.
- Nowe: `apps/admin/src/features/semi-automatic-image-selection/v7-selection-review-workspace.tsx` — tylko do odczytu, trwały podgląd sąsiadów V7.
- Nowe: `apps/admin/test/v7-selection-form.test.mjs` — pełne granice, kierunki i błędy.

## Test cases

- `1-9 → 19-27`, ascending → trzy grupy, granice `1/27`.
- `19-27 → 1-9`, descending → trzy grupy, granice `1/27`.
- `10`, `28` → strony `10–18`, `28–36`; `10-17`, `19-10`, `1.5` i sprzeczna
  kolejność/kierunek → kod błędu, bez payloadu.
- Włączony V7 capability → request ma v7 mode i border; legacy builder nie ma
  pola `v7`.
- Blocked capability → kliknięcie startu nie wywołuje `create` ani pickera.
- Zapis stanu `scan=7`, `sequence=2`, `view=9` → restore daje te wartości;
  zmiana `view=11` nie zmienia dwóch pierwszych.
- Historyczny zapis IndexedDB bez nowych pól → poprawnie restore'uje się z
  `null`; obecny legacy review nadal wywołuje swój output.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, timeout maks. 120 s na krok
pnpm --dir apps/admin test -- --test-name-pattern "v7|semi-automatic"
pnpm --dir apps/admin lint
pnpm --dir apps/admin typecheck
```

Zadanie kończy się po testach modułu/formularza, lint/typecheck, self-audycie,
review Astra Medium, poprawkach i osobnym commicie.

## Risks / open questions

- V7 celowo nie może zostać uruchomione przed T12. Test interfejsu potwierdza
  payload oraz brak obejścia bramki, nie działanie algorytmu na produkcji.
- API nie wystawia jeszcze quality/warnings oraz decyzji T09; ich UI zostaje
  wyraźnie poza tym zadaniem zamiast używać legacy outputu.

## Outcome

`done` — 2026-09-21. Przyjęte wartości produktu: `semi_automatic`,
`ascending` oraz `top_and_sides`. Zablokowana serwerowo V7 pozwala nadal
sprawdzić formularz, lecz nie wybiera folderu ani nie tworzy runu.

### Changed

- `v7-selection-form.ts` normalizuje pełne strony (`10` → `10–18`), obie
  kolejności nagrania, kanoniczne granice API i payload bez legacy OCR.
- Nowe uruchomienie workspace'u używa wyłącznie `mode=v7_selection`, pokazuje
  trzy style obramowania i target `<źródło> cut`; nie używa browserowego
  output directory. Historyczny review/output działa wyłącznie dla historycznych
  runów.
- Local IndexedDB przechowuje addytywnie scan/sequence/view cursor i dopuszcza
  `outputDirectory=null` tylko dla V7. Podgląd sąsiadów jest read-only oraz
  aktualizuje wyłącznie `viewSourceIndex`.
- Self-audyt naprawił możliwą pętlę renderowania podczas restore'u podglądu:
  odtworzony stan jest stosowany jeden raz, a zapis nie zależy od zmiennego
  obiektu UI rodzica.
- Review Astra Medium wykazał cztery regresje odtwarzania i wszystkie zostały
  poprawione: historyczny run bez uchwytu wyniku odzyskuje wyłącznie legacy
  output, viewer V7 montuje się po restore, jego callback utrwala prawdziwe
  przewinięcie, a wspólny hook stosuje początkowy scroll po załadowaniu obrazu
  zamiast pozostawiać go wyłącznie w refie.

### Verification results

- `node --experimental-strip-types --test test/manual-local-image-selection.test.mjs test/v7-selection-form.test.mjs test/semi-automatic-selection-output.test.mjs test/semi-automatic-selection-workspace-contract.test.mjs` — 59 PASS.
- `npm run typecheck --workspace @game-predictor/admin` — PASS.
- `npm run lint --workspace @game-predictor/admin` — 0 errors; pozostaje
  istniejące ostrzeżenie `img` w niezwiązanym `image-folder-import-panel.tsx`.
- Prettier dla zmienionych plików — PASS.
- Self-audyt: `git diff --check` dla zakresu T10 — PASS.
- Końcowy review Astra Medium: po usunięciu czterech zgłoszonych regresji
  `APPROVED`; poprawki przechodzą testy kontraktu, typecheck, lint i
  formatowanie.

### Not completed

- Runtime V7, warningi quality i endpointy ręcznego outputu nie są dostępne w
  tym tasku; T10 nie podstawia za nie historycznego browserowego writera.
- API pozostaje celowo zablokowane do odbioru T12, więc nie wykonano startu
  produkcyjnego ani zapisu JPEG-a.

### Documentation updates

- Uzupełniono `IMAGE_SELECTION.md` w wymaganiach i architekturze oraz
  `CURRENT_STATE.md`.

### Recommended next task

- T11 — pomiar CPU/GPU/RAM i deterministyczna równoległość.
