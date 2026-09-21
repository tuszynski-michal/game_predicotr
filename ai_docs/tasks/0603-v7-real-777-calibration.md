---
title: TASK-0603 — Rzeczywista kalibracja geometrii etykiet 777 V7
status: blocked
---

# TASK-0603 — Rzeczywista kalibracja geometrii etykiet 777 V7

## Status

`blocked`

## Goal

Przygotować trwały, bezpieczny przepływ do ręcznej kalibracji etykiet liczbowych 3×3 na rzeczywistych danych `777`, a profil utworzyć wyłącznie po przejściu mierzalnych bramek różnorodności, pełnego cropa i residualu.

## Context

TASK-0602 udostępnił trwały ekran anotacji, lecz rzeczywisty korpus nie był jeszcze gotowy do użycia jako źródło jednej rodziny geometrii. Profil nie może być tworzony z punktów odgadniętych przez implementację ani z danych holdoutu.

## Dependencies / entry conditions

- TASK-0599–0602 są ukończone; V7 start pozostaje backendowo `blocked`.
- Lokalny manifest `v7-corpus-manifest.local.json` jest w schemacie V1: `small_777` jest `development`, a `occluded_777` jest `calibration`. API prawidłowo odrzuca źródło `development` w sesji kalibracyjnej oraz V1 nie może zadeklarować rodziny geometrii.
- Przyjęte założenie D-415: nowy, ignorowany przez Git manifest T0603 klasyfikuje tylko `small_777` i `occluded_777` jako `calibration` oraz przypina je do `standard_3x3_numeric_labels_v1`; nie zmienia historycznego manifestu, danych obrazowych, danych holdoutu ani aktywacji V7.
- Precyzyjne centra i ocena `contained` są danymi operatora. Nie wolno ich tworzyć syntetycznie, automatycznie lub na podstawie sąsiednich klatek.

## Recommended execution

`gpt-5.6-terra`, reasoning `xhigh`. Wymaga pracy z rzeczywistymi danymi lokalnymi, ale nie wolno zgadywać anotacji. Po zmianach wymagany jest niezależny końcowy review `gpt-6-astra`, reasoning `medium`; wykryte błędy P0–P2 trzeba poprawić i ponownie sprawdzić.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` (D-411–D-415)
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/architecture/API_CONTRACT.md` — V7 Label Geometry Calibration
- `.tmp/V7_LABEL_GEOMETRY_CALIBRATION_UI_PLAN.md` — TASK-0603
- `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_calibration.py`
- `services/api/src/game_predictor_api/application/v7_label_geometry_calibration.py`
- `apps/admin/src/features/v7-label-geometry/v7-label-geometry-calibration-workspace.tsx`

## Scope

- Utworzyć osobny lokalny manifest V2 dla sesji T0603, bez modyfikacji obrazów ani istniejącego manifestu V1.
- Dodać widoczną na ekranie kontrolę gotowości per pozycja: liczba niezależnych SHA, liczba grup ujęć i liczba `contained` oraz stan bramki profilowania.
- Udokumentować prostą procedurę operatora: wybór tylko czytelnych pełnych numerów, dwie rzeczywiste grupy ujęć, zaznaczanie `unavailable`, sprawdzenie zawartości cropa oraz profile tylko po zielonych bramkach.
- Zweryfikować na lokalnym API, że manifest przyjmuje oba case’y 777, odrzuca holdout/development i że ekran nie eksponuje nieuprawnionych danych.
- Jeżeli operator dostarczy wystarczające, rzeczywiste punkty, zweryfikować snapshot i utworzyć profil tylko po przejściu wszystkich bramek. Brak takich danych pozostaje stanem `not_ready`, nie błędem ani sukcesem.

## Out of scope

- Automatyczne lub syntetyczne klikanie środków etykiet.
- OCR, rozpoznawanie symboli, ramki plansz, payouty, adopcja innej gry, runtime observer, selekcja V7, zapis `cut`, prawda Reels, T12 i aktywacja.
- Zmiana progów pięciu SHA, dwóch capture groups, `contained` i p95 `<= 0.04`.

## Acceptance criteria

- [ ] Nowy lokalny manifest V2 wybiera oba case’y 777 jako `calibration` tej samej rodziny, zachowuje wszystkie pozostałe case’y i nie dotyka `reels_test`.
- [ ] UI pokazuje na bieżąco postęp każdej z dziewięciu pozycji względem 5 różnych SHA, 2 capture groups i `contained`; `unavailable`, `clipped` i `uncertain` nie zwiększają liczników, ale wpis diagnostyczny nie blokuje już istniejącego kompletu kwalifikujących się punktów.
- [ ] Instrukcja operatora rozdziela wybór źródła, capture group, punkt centralny, `unavailable`, ocenę cropa i końcowy profil.
- [ ] Kontrola lokalna potwierdza split/family dla obu case’ów oraz odrzucenie przypadków niedozwolonych.
- [ ] Wszelkie rzeczywiste profile są tylko immutable, checksum-bound i `passed`; bez takiego wyniku V7 pozostaje zablokowane.

## Technical notes

Serwer pozostaje właścicielem inwentarza i sesji. Ekran może wyłącznie obliczać diagnostykę z odpowiedzi sesji: dla każdej pozycji liczy unikalne `sourceChecksumSha256` i `captureGroupId` wyłącznie dla slotów `annotated` z `cropAssessment=contained` oraz niepustą grupą ujęć. Karta postępu nie jest autoryzacją — endpoint profilu nadal przeprowadza całą walidację pod własną blokadą.

Manifest T0603 ma być nowym plikiem w `.runtime/`, nie edycją `v7-corpus-manifest.local.json`; start API dostaje go jawnie przez `GAME_PREDICTOR_V7_LABEL_GEOMETRY_CORPUS_MANIFEST`. Wersja 2 deklaruje `geometryFamilyId` i `sourceGameRef` dla wyłącznie obu case’ów użytych przez pierwszą rodzinę. Wszystkie pozostałe case’y zachowują role/splity i mają puste pola V2.

Dla źródeł z jednego przejścia ustaw ten sam `captureGroupId`; dla drugiego, odrębnego przejścia inny. Nazwa grupy opisuje pochodzenie, nie kolejny numer kliknięcia. Niewidoczny, zasłonięty, przycięty lub nieczytelny numer oznacza się `unavailable`; nie wolno klikać przybliżonego środka. Punkt uznany za użyteczny do profilu ma `contained` tylko, gdy proponowany crop obejmie pełny czytelny numer.

## Expected files

- Istniejące: `apps/admin/src/features/v7-label-geometry/v7-label-geometry-calibration-workspace.tsx` — diagnostyka gotowości bez zmiany kontraktu HTTP.
- Istniejące: `apps/admin/test-interactions/v7-label-geometry-calibration-workspace.test.mjs` — regresje diagnostyki i bezpieczeństwa UI.
- Istniejące: `ai_docs/guides/LOCAL_OPERATION_GUIDE.md` — procedura lokalna dla T0603.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`, `ai_docs/process/DECISION_LOG.md`.
- Nowe: `.runtime/v7-label-geometry-calibration-t0603.local.json` — ignorowany lokalny manifest operatora.

## Test cases

- Manifest V2 z `small_777` i `occluded_777` → obie pozycje mają split `calibration`, rodzinę `standard_3x3_numeric_labels_v1`, a `reels_test` nie jest wybieralny.
- Mniej niż pięć SHA lub mniej niż dwie grupy → postęp pokazuje brak gotowości; profil pozostaje niedozwolony przez serwer.
- Pięć różnych SHA z dwoma grupami i pełnymi cropami dla pozycji → UI pokazuje gotowość diagnostyczną; endpoint nadal jest źródłem prawdy dla p95 i finalnej decyzji.
- `unavailable` / `clipped` / `uncertain` → nie zwiększa liczników kwalifikujących się punktów i nie blokuje istniejącego kompletu `contained`.
- Holdout lub development → API kończy się stabilnym błędem splitu, bez utworzenia sesji.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr; timeout <= 120 s
npm run test --workspace @game-predictor/admin -- v7-label-geometry-calibration
npm run lint --workspace @game-predictor/admin
npm run typecheck --workspace @game-predictor/admin
.venv\Scripts\python.exe -m pytest services\api\tests\test_v7_label_geometry_calibration_api.py services\worker\tests\test_v7_calibration.py -q
```

Zadanie kończy się po testach, self-audycie, review Astra Medium, poprawie każdego niekrytycznego błędu i osobnym commicie. Rzeczywiste punkty pozostają jawnym stanem operatora; brak ich liczby nie jest podstawą do utworzenia profilu.

## Risks / open questions

- Samo przygotowanie UI nie zastępuje rzeczywistej oceny człowieka; model nie będzie wytwarzał danych kalibracyjnych bez potwierdzonego odczytu.
- Przy zbyt dużym p95 należy zebrać lepsze, bardziej reprezentatywne punkty. Progu nie obniżamy.
- Zmiana dowolnego pliku po utworzeniu sesji blokuje ją przez drift; wtedy należy zachować istniejący stan do audytu i stworzyć nową sesję na niezmienionym korpusie.

## Outcome

### Wykonane przygotowanie

- Dodano niezależny, ignorowany manifest V2
  `.runtime/v7-label-geometry-calibration-t0603.local.json`. Obejmuje on
  `small_777` i `occluded_777` jako `calibration` dla
  `standard_3x3_numeric_labels_v1`, zachowuje pozostałe case'y oraz
  `reels_test` jako holdout.
- Ekran Admina pokazuje diagnozę dziewięciu pozycji: unikalne źródła SHA,
  rzeczywiste grupy ujęć, pełne cropy, anotacje niepełne i niedostępne.
  Przycisk profilowania wymaga lokalnego spełnienia wszystkich bramek;
  eksport snapshotu pozostaje możliwy, aby operator mógł sprawdzić dane.
- Dodano instrukcję lokalnego uruchomienia i świadomego oznaczania w
  `LOCAL_OPERATION_GUIDE.md`. D-415 dokumentuje oddzielny manifest i jego
  nieingerencję w poprzedni korpus V1.

### Kontrola wykonana

- Resolver rzeczywistego manifestu odnalazł 374 źródła w obu case'ach 777 i
  prawidłowo odrzucił `rells_big` jako `development`.
- Z lokalnym API sprawdzono żądanie `rells_big`; zakończyło się ono
  `422 V7_CALIBRATION_CASE_SPLIT_FORBIDDEN` bez utworzenia sesji.
- Przeszły: 13 testów skoncentrowanych Admina, 2 testy interakcyjne, lint,
  typecheck i build Admina oraz 19 testów API/worker kalibracji. Lint zgłasza
  wyłącznie istniejące wcześniej ostrzeżenie `<img>` poza zakresem taska, a
  pytest jedno ostrzeżenie deprecacji Starlette.
- Końcowy review Astra Medium nie znalazł uwag P0–P2.

### Poprzednia blokada i wznowienie

Rzeczywisty przegląd obu katalogów wykazał, że wiele kadrów w `777` ma stale
zasłonięty dolny lewy obszar, zaś drugi katalog zawiera mieszankę pełnych i
zasłoniętych ujęć. Nie istnieje potwierdzona informacja, które pięć pełnych
kadrów na każdą pozycję należą do dwóch rzeczywiście niezależnych grup ujęć.
Nie wolno tworzyć takich grup ani centrów etykiet przez zgadywanie. Bez
świadomych anotacji operatora serwer poprawnie nie utworzy profilu, a bez
profilu nie wolno przejść do TASK-0604.

Operator wznowił istniejącą sesję i dostarczył sześć–siedem pełnych punktów na
pozycję. Wykryto, że lokalna gotowość i warstwa aplikacji błędnie traktowały
pojedyncze wpisy diagnostyczne `clipped`/`uncertain` jako blokadę całego
profilu. D-418 rozdziela teraz diagnostykę od wejścia profilu.

Pomiar po tej poprawce potwierdza liczbę źródeł i grup, lecz kończy się
`p95=0,225547` przy limicie `0,04`. Jedno pełne źródło
`302200 777_000656.jpg` ma prawidłowo zaznaczoną, ale przesuniętą w prawo
siatkę (`x≈0,26…0,72`); pięć ujęć częściowo zasłoniętych ma tę samą siatkę
po lewej (`x≈0,06…0,50`). Statyczny profil pojedynczych współrzędnych nie może
uczciwie obsłużyć obu legalnych framings. Nie obniżono progu i nie zmieniono
anotacji operatora. TASK-0603 jest ponownie `blocked` na decyzji architektonicznej:
oddzielne profile dla framingów albo nowy lokalizator dynamicznie normalizujący
viewport plansz.
