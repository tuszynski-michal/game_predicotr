---
title: Plan — braki geometrii zdjęć w lokalnym Reviewerze i odchudzona Diagnostyka siatek
status: accepted
last_updated: 2026-10-10
---

# Braki geometrii zdjęć w lokalnym Reviewerze

Polecenie operatora z 2026-10-10. Plan zaakceptowany przez operatora
2026-10-10 poleceniem „Realizuj cały plan”: oba etapy w jednym przebiegu,
zatrzymanie tylko przy krytycznym błędzie; audyt zadań na modelu niższym niż
wykonawca, a po wyczerpaniu limitu — bez audytu (odnotowane w `Outcome`).
Dwa etapy: **A** (TASK-0961 → TASK-0962 → TASK-0963: API i
Reviewer) oraz **B** (TASK-0964 → TASK-0965: Admin, dokumentacja, odbiór).
Etap B zaczyna się dopiero po odbiorze etapu A, żeby Admin nie stracił listy
zdjęć, zanim Reviewer ją zastąpi.

## Stan obecny (fakty z kodu i z lokalnego API, 2026-10-10)

- Admin → „Korekta cięcia siatki”
  (`apps/admin/src/features/reviewer-access/reviewer-access-launcher.tsx::ReviewerAccessLauncher`)
  ma launcher (wybór gry, **select „Gotowy import plansz”**, „Otwórz lokalnie”)
  oraz pod nim sekcję „Diagnostyka siatek zdjęć”
  (`apps/admin/src/features/imports/geometry-completeness-section.tsx::GeometryCompletenessSection`).
- Reviewer 3001 jest wołany z `importJobId` i pokazuje wyłącznie kolejkę
  `view=correction`: sloty odroczone przez algorytm oraz plansze z bieżącym
  `grid_issue` („Zła siatka”)
  (`apps/reviewer/src/features/operational-reviews/board-geometry-correction-workspace.tsx::BoardGeometryCorrectionWorkspace`,
  `services/api/src/game_predictor_api/storage/image_grid_review_repository.py::_visible_statement`).
  D-462 celowo nie obejmuje w niej walidacji gotowych siatek.
- „Diagnostyka siatek zdjęć” liczy inny zbiór: klasyfikację kompletności
  zdjęcia z D-484
  (`services/api/src/game_predictor_api/domain/image_geometry_completeness.py::classify_position`,
  `classify_image`). Pozycja z planszą, której siatka nie jest zatwierdzona
  przez człowieka ani zaakceptowana przez silnik, to `uncertain`
  („Siatka niepotwierdzona”) i czyni zdjęcie `incomplete_uncertain`.
- Dane (odczyt, `GET .../geometry-completeness/{game_id}` i
  `GET .../games/{game_id}/grid-reviews?view=correction&limit=1`):

  | Gra | Zdjęcia | Kompletne | Niekompletne | w tym niepotwierdzone | Brakuje plansz | Częściowe | Import nieudany | Zastąpione | Kolejka korekty |
  |---|---|---|---|---|---|---|---|---|---|
  | Mumie | 51 749 | 5 | 51 545 | 51 541 (463 816 plansz) | 1 | 0 | 3 | 199 | 0 |
  | 777 | 56 812 | 55 483 | 76 | 0 | 0 | 76 (128 plansz) | 0 | 1 253 | 255 |

  „51 tys. niekompletnych” to więc w praktyce „automatyczna siatka bez
  ręcznego potwierdzenia”, nie błąd cięcia. Realnych braków jest garstka.
- „Czarny ekran”: podgląd w
  `GeometryImageItem` rysuje siatki w SVG na ciemnym tle, a zdjęcie ładuje się
  dopiero po kliknięciu „Pokaż zdjęcie pod siatkami”. Lista ma 25 zdjęć na
  stronę, każde z listą pozycji.
- Wydajność (pomiar pojedynczych odczytów, cały zakres gry): `grid-reviews`
  `view=correction&limit=1` trwa 23 s (Mumie) i 45 s (777), bo każde wywołanie
  liczy komplet liczników
  (`application/image_grid_reviews.py::ImageGridReviewService.list` →
  `grid_review_counts`). `incomplete-images?imageState=…&limit=25` trwa 5–11 s.
  Reviewer wołający `grid-reviews` przy każdej planszy w zakresie całej gry
  byłby nieużywalny.
- Bezpieczeństwo: z origin Reviewera dozwolone są tylko mutacje z
  `_REVIEWER_MUTATION_PATTERNS`
  (`services/api/src/game_predictor_api/security/local_admin.py`). Ustawienie i
  wycofanie wyjątku bramki to operacje wysokiego wpływu tylko z Admina.
  Odczyty (GET) kompletności są dostępne dla Reviewera.
- Zabezpieczenie przed ponownym importem tego samego zakresu to osobny temat
  (propozycja sesji „Blokada ponownego importu tych samych zdjęć”); ten plan go
  nie dotyka.

## Cel

Po „Otwórz lokalnie” operator widzi w Reviewerze, w zakresie całej gry,
wyłącznie realne braki geometrii — po jednej planszy lub jednym zdjęciu naraz,
z prawdziwym zdjęciem pod siatką i filtrami. Admin pokazuje w „Diagnostyce
siatek zdjęć” tylko liczniki i przycisk otwarcia Reviewera.

## Decyzje (z odpowiedzi operatora i rekomendacje planisty)

1. **Zakres kolejki: realne braki.** Do kolejki wchodzą: sloty odroczone i
   „Zła siatka” (jak dziś), `incomplete_missing`, `incomplete_partial`,
   `import_failed`, `no_source_geometry`. `incomplete_uncertain`
   („Siatka niepotwierdzona”) **nie jest kolejką** — wyłącznie licznik w
   Adminie. D-462 w części „bez walidacji gotowych siatek” zostaje.
2. **Zakres gry, nie importu.** Lokalny Reviewer dostaje tylko `gameId`;
   select „Gotowy import plansz” znika z Admina. `importJobId` pozostaje
   opcjonalnym parametrem (inni wołający, zdalny Reviewer bez zmian — D-462 P3).
3. **Dwie zakładki w lokalnym Reviewerze:** „Do korekty” (dotychczasowa
   kolejka planszy) i „Braki zdjęć” (nowa, na poziomie zdjęcia). Filtry nowej
   zakładki: „Wszystkie braki” (domyślny), „Brakuje plansz”, „Plansza
   częściowa”, „Import nieudany”, „Bez geometrii źródła”. Filtry bramki
   („Kolejka siatek”, „Wyjątki operatora”) i „Zastąpione nowszym importem” nie
   są przenoszone (wybór operatora).
4. **Edycja z poziomu zdjęcia** używa istniejącego edytora narożników
   (`BoardGeometryCorrectionEditor`) i istniejących celów
   (`deferredBoardGeometryTarget`, `reportedBoardGeometryTarget`); nie powstaje
   nowa ścieżka zapisu geometrii. Edycja jest dostępna dla każdej pozycji
   zdjęcia, która ma planszę lub slot. To jawna, inicjowana przez operatora
   korekta, nie walidacja kolejki gotowych siatek.
5. **Pozycje bez slotu i bez planszy** (`missing` bez wiersza odroczenia),
   `import_failed` i `no_source_geometry` nie mają czego edytować w edytorze
   narożników: Reviewer pokazuje zdjęcie, stan i wskazówkę (ponowne
   przetworzenie pliku w „Imporcie plansz”).
6. **Wyjątki bramki.** UI „Dopuść wyjątkiem…/Wycofaj wyjątek” znika z Admina
   razem z listą zdjęć; endpointy, audyt i dane zostają. Reviewer ich nie
   przejmuje (zabronione przez politykę origin). Dziś wyjątków jest 0, a
   bramka nie wstrzymuje żadnej planszy (`withheldBoards = 0` w obu grach, V3
   tnie poprawne siatki). Przywrócenie UI wyjątków to osobny task, jeśli
   bramka znów zacznie wstrzymywać plansze.
7. **Liczniki tanie.** `grid-reviews` dostaje tryb liczników `correction`
   (liczony tylko `counts.correction`), a lista niekompletnych zdjęć filtr
   `gapsOnly` (cztery stany braków jednym zapytaniem). Budżety:
   strona korekty ≤ 3 s, strona braków ≤ 12 s na Mumie i 777.
8. **Plansza częściowa nie ma stanu końcowego.** `classify_position` zwraca
   `partial` dla każdego `pending_partial`, także zakwalifikowanego ręcznie
   (D-449). Odpowiedź pozycji dostaje flagę `humanApproved`, a zakładka
   domyślnie ukrywa zdjęcia, w których wszystkie pozycje `partial` są już
   zatwierdzone ręcznie (przełącznik „Pokaż także zatwierdzone ręcznie”).

## Zadania

| Zadanie | Etap | Zakres | Zależy od |
|---|---|---|---|
| TASK-0961 | A | API: liczniki `correction`, filtr `gapsOnly`, flaga `humanApproved`; OpenAPI, klient, testy, pomiar | — |
| TASK-0962 | A | Reviewer: zakres gry bez `importJobId`, zakładki, tanie liczniki | 0961 |
| TASK-0963 | A | Reviewer: zakładka „Braki zdjęć” (lista, zdjęcie z siatką, filtry, edycja pozycji) | 0961, 0962 |
| TASK-0964 | B | Admin: odchudzona Diagnostyka, bez selecta importu, przycisk Reviewera | 0963 |
| TASK-0965 | B | Decyzja D-540, dokumentacja, odbiór na żywych danych | 0964 |

Szczegóły i kryteria akceptacji: `ai_docs/tasks/0961-…` do `0965-…`.

## Reguły danych i błędów

- Źródło prawdy dla stanu zdjęcia i pozycji: klasyfikacja D-484 (`domain/
  image_geometry_completeness.py`); Reviewer nie liczy stanów samodzielnie.
- Źródło prawdy dla celu edycji: wiersz kolejki `grid-reviews` dla
  `(sourceImageId, positionIndex)`. Gdy brak wiersza — pozycja jest
  informacyjna (decyzja 5), bez przycisku edycji.
- Konflikt zapisu (zmieniona rewizja geometrii) obsługuje istniejące
  `onConflict` edytora: komunikat, odświeżenie zdjęcia, bez pętli.
- `gapsOnly` razem z `imageState` → 422 `IMAGE_GEOMETRY_COMPLETENESS_FILTER_CONFLICT`
  (brak cichego wyboru jednego z nich).
- Brak pliku źródłowego zdjęcia: komunikat „Zdjęcie źródłowe jest
  niedostępne”, lista pozycji nadal widoczna.

## Mapa wymaganie → zadanie → test

| Wymaganie | Zadanie | Test |
|---|---|---|
| Plansze z diagnostyki widoczne w Reviewerze (realne braki) | 0961, 0963 | test serwisu `gapsOnly`, test interakcji zakładki „Braki zdjęć” |
| Brak selecta importu, zakres całej gry | 0962, 0964 | test strony Reviewera bez `importJobId`, test launchera |
| Filtry w Reviewerze | 0963 | test interakcji filtrów |
| Koniec czarnego ekranu i długiego scrolla w Adminie | 0964 | test placement diagnostyki, test źródła sekcji |
| Szybkie liczniki w zakresie gry | 0961 | pomiar czasu, test repozytorium PostgreSQL |
| „Siatka niepotwierdzona” tylko jako licznik | 0964 | test źródła sekcji (brak listy) |

## Odbiór całości

Na żywym Admin + Reviewer: Mumie — „Braki zdjęć” pokazuje 4 zdjęcia (1
„Brakuje plansz”, 3 „Import nieudany”), 777 — zdjęcia „Plansza częściowa” z
filtrem ukrywającym zatwierdzone ręcznie; zdjęcie widoczne od razu, bez
przycisku; zapis siatki jednej pozycji; Admin bez selecta importu, z licznikami.
Wymaga restartu API i `npm run reviewer:build` (operator).

## Ryzyka

- **Wydajność klasyfikacji na całej grze** (5–11 s na stronę). Budżet z
  decyzji 7; przy przekroczeniu EXPLAIN i minimalna zmiana zapytania lub
  indeksu przez Alembic (numer migracji według końcówki gałęzi integracyjnej;
  head w chwili planowania: `0153_merge_compact_super_games`).
- **Plansza częściowa bez stanu końcowego** — łagodzone flagą `humanApproved`
  (decyzja 8); pełne rozwiązanie wymagałoby zmiany klasyfikacji D-484 i nie
  jest w zakresie.
- **Utrata UI wyjątków** (decyzja 6) — świadoma, odwracalna osobnym taskiem.
- **Równoległe sesje** zajmują numery tasków, decyzji i `vX.Y.N`: numery tu
  podane (TASK-0961–0965, D-540) sprawdzono 2026-10-10 względem końcówki
  `v1.1-vision-lab-hybrid-geometry` i wszystkich worktrees; wykonawca
  weryfikuje je ponownie przed pierwszym commitem i przed scaleniem.

## Poza zakresem

Walidacja/zatwierdzanie gotowych siatek, kolejka „Siatka niepotwierdzona”,
zmiana klasyfikacji D-484, blokada ponownego importu tych samych zdjęć,
przywrócenie UI wyjątków, zdalny Reviewer.

## Przypisanie modeli do zadań

Konfiguracja jest rekomendacją warunkową: nazwy modeli pochodzą z listy
modeli bieżącej sesji (`claude-fable-5-1`, `claude-opus-5-5`,
`claude-sonnet-5-5`, `claude-haiku-5-5`), a poziomy z listy wspieranych
poziomów rozumowania narzędzia delegowania (`low`, `medium`, `high`, `xhigh`,
`max`); środowisko wykonawcze nie udostępnia sprawdzenia dostępności z
wyprzedzeniem.

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0961 | claude-fable-5-1 | high | Kontrakt API, wydajność zapytań na dużych zbiorach, regeneracja OpenAPI i klienta; ryzyko regresji liczników. Eskalacja do `xhigh`, jeśli budżety czasu wymagają zmiany zapytania lub indeksu. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
| TASK-0962 | claude-sonnet-5-5 | medium | Wąska zmiana routingu i propsów Reviewera z testami; brak nowej logiki domenowej. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
| TASK-0963 | claude-fable-5-1 | high | Nowy ekran z integracją istniejącego edytora narożników, cyklem życia blob URL i obsługą konfliktów zapisu. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
| TASK-0964 | claude-sonnet-5-5 | medium | Usuwanie kodu UI i przepięcie launchera z aktualizacją testów źródłowych; niskie ryzyko danych. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
| TASK-0965 | claude-sonnet-5-5 | medium | Dokumentacja, wpis decyzji i odbiór na żywych danych według listy kontrolnej. | Nie (audyt po zadaniu zawieszony przez operatora 2026-10-01) |
