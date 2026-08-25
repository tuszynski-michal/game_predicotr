---
title: TASK-0292 — Wyszukiwanie plansz częściowym układem
status: in_progress
last_updated: 2026-08-26
---

# TASK-0292 — Wyszukiwanie plansz częściowym układem

## Goal

Udostępnić w zakładce gry widok `Wyszukaj plansze`, który wyszukuje jedną
logiczną planszę dla każdego numeru sekwencji według częściowego wzoru symboli,
bez skanowania setek tysięcy surowych obserwacji w żądaniu użytkownika.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- czysty, wersjonowany ranking częściowego wzoru 3 × 5,
- trwała projekcja kandydatów i jednego zwycięzcy na numer sekwencji,
- synchronizacja projekcji po imporcie, predykcji i decyzji review,
- read-only Admin API i wygenerowany klient,
- edytor wzoru z paletą symboli, cofnięciem i resetem,
- karuzela wyników z pełnym cropem planszy oraz bezpiecznym fallbackiem,
- testy, benchmark i dokumentacja odbioru.

## Invariants

- `sequence_number` pozostaje kluczem domenowym; wynik nie łączy źródeł o tym
  samym numerze w wiele kart.
- Accepted/corrected używa wyłącznie ręcznie rozwiązanych symboli, a pending
  najnowszych predykcji przypiętych do pozycji.
- Przyszłe `?` to brak dowodu: nie daje punktu i nie jest błędnym dopasowaniem.
- Endpoint jest read-only, ograniczony do 100 wyników i nie zawiera obrazów
  binarnych w bazie ani odpowiedzi JSON.
- Pierwotny crop planszy jest używany bez ponownego resamplingu; brak assetu
  daje kontrolowany fallback, nie znika wynik.

## Ordered implementation modules

1. Ranking domenowy i kontrakt znaczenia brakującego symbolu.
2. Modele/migracja projekcji oraz jednorazowy backfill.
3. Wspólny synchronizator projekcji w ścieżkach write.
4. Read-only API, OpenAPI i klient Admina.
5. Edytor częściowej planszy i nawigacja Admina.
6. Karuzela wyników, asset cropu i prefetch sąsiadów.
7. Benchmark, testy przekrojowe, dokumentacja oraz odbiór.

## Acceptance criteria

- [ ] Częściowy wzór zwraca wyniki w deterministycznym porządku: exact,
  alternatywy, błędy, status, numer sekwencji i ID.
- [ ] Przełącznik rozróżnia wszystkie wyszukiwalne plansze od wyłącznie
  `accepted/corrected`.
- [ ] Edytor obsługuje wskazanie komórki, sekwencyjne dodawanie, `Cofnij` i
  `Resetuj` bez automatycznego requestu na zmianę wzoru.
- [ ] Karuzela przechodzi dokładnie o jedną pozycję strzałkami i przyciskami,
  pokazuje status, wynik oraz pozycję.
- [ ] P95 ciepłego zapytania na obecnym zbiorze nie przekracza 500 ms; pojedyncze
  ciepłe żądanie nie przekracza 2 s.
- [ ] API, OpenAPI, Admin client, testy i dokumentacja są zgodne.

## Out of scope

- model CV lub OCR w wyszukiwarce,
- zmiana geometrii/croppera oraz automatyczne zatwierdzanie plansz,
- rozwiązanie trwałego problemu wielokrotnych pendingów (TASK-0291),
- UI mobilne i Reviewer.

## Outcome

### Changed

- `v0.8.1` dodaje czysty, wersjonowany kontrakt `partial-board-ranking-v1`.
  Ranking rozróżnia pełne dopasowanie, cztery pozycje alternatywy, sprzeczność
  i brak dowodu `?`; nie zależy od ORM, HTTP ani confidence modelu.
- `v0.8.2` dodaje migrację `0057_board_search_projection`, zwarte kandydatury
  symboli oraz jeden dokument widoczny dla pary `game + sequence`. GIN indeksy
  tokenów ograniczają zbiór kandydatów, a backfill w porcjach nie przenosi
  obrazów ani nie modyfikuje istniejącego review.
- `v0.8.3` dodaje synchronizację w tych samych transakcjach co tworzenie planszy,
  rewizja symboli, korekta geometrii i decyzje review. Migracja `0058` zapisuje
  stan `rebuilding/ready/failed` per gra; skrypt operatorski buduje historyczną
  projekcję stronicami po ID i materializuje dokumenty SQL-em, bez skanowania
  obrazów i bez ponownego uruchamiania importu.
- `v0.8.4` dodaje read-only endpoint wyszukiwania, stabilne błędy walidacji oraz
  wygenerowany klient Admina. Endpoint wykorzystuje wyłącznie gotową projekcję,
  sprawdza kody względem aktywnego katalogu gry i nie traktuje alternatyw stale
  zapisanych przy `accepted/corrected` jako dowodu.
- `v0.8.5` dodaje sekcję gry `Wyszukaj plansze` z responsywną paletą aktywnych
  symboli i lokalnym edytorem częściowego wzoru 3 × 5. Edycja łączy wskazanie
  konkretnej komórki z sekwencyjnym przejściem do kolejnego pustego pola;
  `Cofnij`, `Resetuj` i przełączenie scope nie wykonują requestu. Jedynie jawne
  `Szukaj plansz` wywołuje read-only API.
- `v0.8.6` dodaje karuzelę wyników z checksum-bound pełnym cropem planszy,
  pozycją, wynikiem, statusem i licznikami dowodów rankingu. Nawigacja
  przyciskami oraz `←/→` przesuwa dokładnie o jeden wynik i nie zawija listy;
  klient prefetchuje wyłącznie bezpośrednich sąsiadów. Brak cropu nie usuwa
  wyniku, lecz pokazuje kontrolowany fallback.

### Verification results

- `services/api/tests/test_board_search_domain.py`: 10 passed.
- `services/api/tests/test_board_search_projection_repository.py`: 3 passed.
- `services/api/tests/test_migration_baseline.py`: 41 passed.
- `services/api/tests/test_operational_image_reviews.py`,
  `services/worker/tests/test_image_pipeline_execution.py` i
  `services/worker/tests/test_pending_grid_reinference.py`: 32 passed;
  6 izolowanych testów PostgreSQL pozostaje opt-in.
- Ruff i sprawdzenie formatowania nowych plików: passed.
- `services/api/tests/test_board_search_api.py` i rozszerzona kontrola OpenAPI
  weryfikują parser powtarzalnego `cell`, scope, stabilne błędy oraz kontrakt
  odpowiedzi; klient Admina weryfikuje serializację zapytania.
- `apps/admin/test/board-search-editor-state.test.mjs` sprawdza edycję
  sekwencyjną, nadpisanie wskazanej komórki, cofnięcie i reset; test nawigacji
  potwierdza trwały adres sekcji `board-search` w kontekście gry.
- `apps/admin/test/board-search-results-state.test.mjs` sprawdza karuzelę
  jednego kroku bez zawijania i wyznaczanie wyłącznie istniejących sąsiadów;
  klient Admina sprawdza scope-bound URL pełnego cropu. Testy Admina,
  typecheck i produkcyjny build przechodzą; lint nie zgłasza błędów i pozostają
  wyłącznie trzy wcześniejsze ostrzeżenia w niepowiązanych modułach.

### Not completed

- Benchmark i odbiór wydajnościowy pozostają do wykonania. Historyczny backfill
  gry `777` zakończył się stanem `ready` dla `212251` kandydatów i `125431`
  dokumentów; endpoint nie uznaje stanu `rebuilding` za pusty wynik.

### Documentation updates

- Utworzono zadanie i jego niezmienne inwarianty.

### Recommended next task

- Moduł 7: benchmark, testy przekrojowe, dokumentacja i odbiór.
