# TASK-0538 — odzyskanie pustej sesji przygotowania cropów

## Status

`done`

## Goal

Automatycznie uruchomić przygotowanie cropów dla pustej sesji bez przypiętej
polityki, zachowując jawne przeliczanie każdej sesji zawierającej wynik,
decyzję operatora, błąd albo operację oczekującą.

## Context

Katalog `348256 - 371007 cut` ma 2528 wpisów inwentarza, 0 wyników, 0 błędów,
pusty review i brak `preparationPolicyVersion`. Workspace klasyfikuje go jako
historyczną sesję, nie wywołuje przygotowania oraz blokuje kafelki wymagające
wyniku. Powtórzenie po usunięciu katalogu ujawniło dodatkowo wyścig inicjalizacji:
o tym, czy zapisać v12, decydowała sama obecność manifestu utworzonego przed
wolniejszym zapisem shardów i inwentarza, więc drugi otwierający mógł zapisać
nową, całkowicie pustą sesję z polityką `null`.

## Dependencies / entry conditions

- `ACTIVE_SELECTED_IMAGE_CROP_POLICY` wskazuje v12.
- Shardy, session journal i review są źródłem prawdy o tym, czy sesja jest
  rzeczywiście pusta.
- Brak wyników sam w sobie nie wystarcza, jeżeli istnieje błąd, pending albo
  decyzja operatora.

## Recommended execution

`gpt-6-astra`, reasoning `high`. Zmiana dotyczy trwałego recovery i granicy
między automatycznym przypięciem polityki a jawnym reprocess. Dodatkowy review
nie jest potrzebny, jeżeli regresje pokryją każdy stan wykluczający pustą
sesję.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`

## Scope

- Dodać czystą klasyfikację sesji bezpiecznej do przypięcia aktywnej polityki.
- Użyć tej klasyfikacji także podczas migracji/inicjalizacji snapshotu, bez
  polegania na podatnej na wyścig obserwacji obecności manifestu.
- Przy `null`/braku polityki i całkowicie pustym stanie trwale przypiąć v12
  przed przygotowaniem pierwszego JPEG-a.
- Pozwolić workspace'owi od razu rozpocząć przygotowanie takiej sesji.
- Zachować dotychczasową blokadę i jawną akcję przeliczenia dla niepustych
  sesji historycznych.
- Dodać regresje domeny, adaptera i kontraktu workspace'u.
- Uzupełnić dokumentację bieżącego zachowania.

## Out of scope

- Usuwanie katalogu, manifestu, shardów albo JPEG-ów.
- Automatyczna zmiana polityki sesji z rozpoznaną wersją v10/v11/v12.
- Automatyczny reprocess istniejących wyników lub decyzji operatora.
- Zmiana detektora v12, progów albo fingerprintu.

## Acceptance criteria

- [x] Pusta sesja z `preparationPolicyVersion=null` przypina aktywny v12 i
      rozpoczyna przygotowanie od pierwszego pliku.
- [x] Licznik aktualizuje się po każdym trwale zapisanym wyniku.
- [x] Kafelki stają się dostępne wraz z pojawieniem się wyników.
- [x] Wynik, decyzja, błąd lub pending wykluczają automatyczne przypięcie.
- [x] Sesje z rozpoznaną polityką zachowują własną wersję.
- [x] Testy core i Admina, typecheck, lint oraz build przechodzą.

## Technical notes

Klasyfikacja ma działać na pełnym snapshotcie v2. Bezpieczny stan wymaga:
polityki `null`/brak, pustych map wyników we wszystkich shardach, braku pending,
braku failures, pustych list review/correction/accepted/corrected i
`completedAt=null`. Adapter przypina aktywną politykę istniejącym journalowym
zapisem przed pierwszym cropem. Workspace pomija komunikat o historycznej
polityce tylko dla tak sklasyfikowanego stanu. Każdy inny stan pozostaje
fail-closed i wymaga istniejącej jawnej akcji przeliczenia.

## Expected files

- Istniejący `packages/manual-image-selection-core/src/crop-session.ts` —
  klasyfikacja pustego snapshotu.
- Istniejący `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-storage.ts`
  — trwałe przypięcie przed przygotowaniem.
- Istniejący `apps/admin/src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx`
  — automatyczny start pustej sesji.
- Istniejące testy core i Admina.
- Dokumentacja wskazana w `Relevant docs`.

## Test cases

- Snapshot bez polityki, wyników i decyzji → bezpieczne przypięcie.
- Ten sam snapshot z pojedynczym wynikiem, failure, pending albo wpisem review
  → brak automatycznego przypięcia.
- Snapshot z v10/v11/v12 → brak automatycznej zmiany wersji.
- Adapter przy pustym legacy snapshotcie zapisuje aktywną politykę przed
  przejściem pętli przygotowania.
- Workspace nie zatrzymuje pustej sesji na komunikacie o starej polityce.

## Verification

```powershell
npm test --workspace @game-predictor/manual-image-selection-core
npm test --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/manual-image-selection-core
npm run typecheck --workspace @game-predictor/admin
npm run lint --workspace @game-predictor/admin
npm run build --workspace @game-predictor/admin
```

Kryterium zaliczenia: wszystkie komendy kończą się kodem 0, a zapisany stan
rzeczywistego katalogu po wznowieniu ma v12 i rosnącą liczbę wyników bez
usunięcia wcześniejszych plików.

## Risks / open questions

- Bieżący katalog jest pusty domenowo, ale zawiera poprawnie utworzone puste
  shardy; kwalifikacja nie może mylić obecności plików shardów z wynikami.
- Brak pytań blokujących. Zmiana metadanej pustej sesji jest odwracalna przez
  brak danych zależnych i nie nadpisuje decyzji operatora.

## Outcome

### Zmieniono

- Core rozpoznaje sesję bez polityki jako bezpieczną do automatycznego
  przypięcia wyłącznie wtedy, gdy cały snapshot nie zawiera wyników, błędów,
  operacji oczekującej ani decyzji review.
- Adapter zapisu przypina aktywną politykę v12 journalowym zapisem przed
  przygotowaniem pierwszego JPEG-a, a workspace nie zatrzymuje takiej pustej
  sesji na komunikacie o wymaganym przeliczeniu.
- Inicjalizacja snapshotu ustala v12 na podstawie kompletnej pustki domenowej,
  a nie na podstawie tego, czy bieżące wywołanie zdążyło utworzyć manifest.
- Sesje z dowolnym trwałym śladem pracy oraz sesje z rozpoznaną wersją nadal
  zachowują dotychczasową ochronę i nie zmieniają polityki automatycznie.

### Weryfikacja

- `npm test --workspace @game-predictor/manual-image-selection-core` — 96/96.
- `npm test --workspace @game-predictor/admin` — 459/459.
- Typecheck core i Admina, lint Admina oraz produkcyjny build Admina — kod 0.
- Bundle serwowany na `127.0.0.1:3000` zawiera klasyfikację recovery oraz
  inicjalizację bez flagi `isNewSession` zależnej od kolejności otwarć.
- Ponowny odczyt `348256 - 371007 cut` po testach potwierdził niezmieniony stan:
  rewizja 0, brak polityki, 0 wyników, 0 błędów, brak pending i pusty review.

### Niewykonane

- Nie wznowiono rzeczywistego katalogu z przeglądarki testowej. Uprawnienie do
  jego uchwytu jest zapisane lokalnie w przeglądarce operatora; ręczna zmiana
  plików stanu ominęłaby journal i nie stanowiłaby miarodajnej weryfikacji.
  Po odświeżeniu panelu i wybraniu `Wznów zapisany katalog` kod przypnie v12 i
  rozpocznie przygotowanie.

### Dokumentacja

- Uzupełniono wymagania, architekturę, stan bieżący i rejestr decyzji o regułę
  odzyskiwania całkowicie pustej sesji.

### Następny krok / ryzyko

- Jedyny krok operatorski to przeładowanie otwartej karty i wznowienie katalogu
  w przeglądarce, która posiada jego uchwyt. Każdy wynik zapisany przed tym
  krokiem zmieni kwalifikację na
  bezpiecznie blokowaną i będzie wymagał jawnego przeliczenia.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0538 — odzyskanie pustej sesji przygotowania cropów | gpt-6-astra | high | Recovery musi rozróżnić całkowicie pusty snapshot od stanu z dowolnym trwałym śladem pracy i zachować historyczne wersje. | Nie; pełna macierz stanów jest objęta regresjami. |
