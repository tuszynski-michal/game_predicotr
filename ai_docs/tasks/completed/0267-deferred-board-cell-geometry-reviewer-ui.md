---
title: TASK-0267 deferred board-cell geometry Reviewer UI
status: done
release: "0.7"
last_updated: 2026-08-23
---

# TASK-0267 — Końcowa kolejka korekty odroczonej geometrii komórek

## Goal

Udostępnić operatorowi w istniejącej aplikacji Reviewer osobną, ograniczoną
kolejkę trwałych `image_board_geometry_pending`, aby mógł ustawić cztery
narożniki siatki 5 × 3, sprawdzić 15 cropów source-direct i przekazać utworzoną
planszę do zwykłego zatwierdzania symboli.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/tasks/0256-deferred-self-improving-page-geometry.md`
- `ai_docs/tasks/completed/0266-manual-deferred-board-cell-resolution.md`

## Scope

- pokazać liczbę odroczonych plansz dla wybranego importu w Adminie i
  Reviewerze,
- pozwolić otworzyć Reviewer także wtedy, gdy import ma wyłącznie odroczoną
  geometrię i jeszcze nie ma zwykłego itemu review,
- dodać jawną końcową kolejkę korekty, niezależną prezentacyjnie od zwykłej
  kolejki plansz, ale bez tworzenia drugiej kolejki domenowej po zapisie,
- pobierać najwyżej jeden bieżący deferred i nawigować bounded po stabilnym
  kursorze API,
- wczytać checksum-bound kontekst i oryginalne źródło, pokazać numer sekwencji,
  pozycję oraz przyczynę odroczenia,
- edytować dokładnie cztery narożniki, rysować perspektywiczną siatkę 5 × 3 i
  generować read-only podgląd 15 cropów,
- zezwolić na zapis wyłącznie dla podglądu odpowiadającego bieżącym narożnikom,
- zachować klucz idempotencji dla niezmienionej komendy po niejednoznacznym
  błędzie transportu, a konflikt rewizji rozwiązywać przez bezpieczne
  przeładowanie,
- po zapisie przejść do następnego deferred; nowo utworzona plansza pozostaje
  w istniejącej zwykłej kolejce review.

## Out of scope

- zmiana backendu lub schematu bazy,
- automatyczna korekta albo auto-akceptacja,
- zmiana domyślnego pipeline'u v18, trybu opt-in v20 albo bramki rollout,
- trening, backfill i masowe przeliczenie,
- zmiana numeru z poświadczonego `seq_*`,
- łączenie deferred z trwałą projekcją zwykłej kolejki przed skutecznym zapisem.

## Invariants

- UI nie zapisuje niczego podczas przesuwania narożników ani preview.
- Nieaktualny preview nigdy nie odblokowuje zapisu.
- Źródło, manifest, model i rewizje pozostają związane przez payload TASK 5.
- Jedna plansza daje dokładnie 15 cropów i jeden zwykły item review albo zero
  projekcji.
- Decyzja człowieka albo istniejąca plansza zawsze wygrywa z bieżącym ekranem.
- Klient nie materializuje całej kolejki ani obrazów wszystkich deferred.
- Rozwiązane i superseded nie wracają do domyślnej kolejki `pending`.

## Acceptance criteria

- [x] Admin pokazuje licznik odroczonej geometrii i pozwala otworzyć pracę przy
      `review.total = 0`, jeżeli `deferred.pending > 0`.
- [x] Reviewer pokazuje osobny tryb korekty z licznikami i jednym elementem.
- [x] Oryginał oraz sugerowane cztery narożniki pochodzą z checksum-bound
      kontekstu TASK 5.
- [x] Overlay 5 × 3 reaguje na przeciąganie czterech narożników bez zapisu.
- [x] Każda zmiana narożników unieważnia poprzedni podgląd.
- [x] Zapis jest możliwy dopiero po aktualnym podglądzie 15 cropów.
- [x] Skuteczny zapis usuwa deferred z kolejki pending i nie omija następnego.
- [x] Exact retry nie tworzy drugiej planszy; konflikt lub superseded prowadzi
      do bezpiecznego odświeżenia bez nadpisania wyniku.
- [x] Zwykła kolejka i jej bounded bufor zachowują dotychczasowe zachowanie.
- [x] Testy klienta, Admina i Reviewera, lint, typecheck oraz build przechodzą
      dla zmienionego zakresu.

## Outcome

- Klient Admin API udostępnia scope-bound listę, kontekst, źródło, preview i
  resolution istniejących endpointów TASK 5 bez zmiany backendu/OpenAPI.
- Reviewer pokazuje osobny tryb jednego deferred, bounded nawigację, edycję
  czterech narożników, perspektywiczną siatkę 5 × 3 i 15 cropów source-direct.
- Aktualny preview jest warunkiem zapisu. Nieaktualny podgląd i zmieniona komenda
  czyszczą stan idempotencji; niejednoznaczny błąd niezmienionej komendy zachowuje
  ten sam klucz. Konflikt bezpiecznie przeładowuje kolejkę.
- Launcher Admina uwzględnia deferred-only pracę oraz pokazuje jej licznik.
- Przeszły testy klienta `40/40`, Admina `238/238` i Reviewera `40/40`, ich
  typecheck/lint, buildy Admina i Reviewera oraz `openapi:check`. ESLint Admina
  zgłasza wyłącznie dwa wcześniejsze ostrzeżenia dotyczące `<img>`.
- Browser smoke test został ograniczony przez wyłączoną usługę Reviewera na
  `127.0.0.1:3001`; build produkcyjny i testy kontraktowe potwierdzają UI bez
  modyfikowania danych użytkownika ani uruchamiania kolejnego procesu.
