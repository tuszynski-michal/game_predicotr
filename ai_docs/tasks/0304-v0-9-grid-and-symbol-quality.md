---
title: TASK-0304 — Walidacja geometrii, jakość symboli i topologia planszy 0.9
status: in_progress
last_updated: 2026-08-28
---

# TASK-0304 — Walidacja geometrii, jakość symboli i topologia planszy 0.9

## Status

`in_progress`

TASK 1–5 zostały ukończone w kodzie. TASK 2 dodaje addytywny schemat 0073 i
kontrolowany backfill metadanych, TASK 3 przenosi przypiętą topologię przez
snapshot, fingerprint, geometrię, cropper i ręczny preview, a TASK 4 atomowo
synchronizuje zatwierdzenie geometrii, proweniencję cropów i istniejące
projekcje planszy. TASK 5 dostarcza bounded lokalne API kolejki walidacji.
Migracja nie została jeszcze zastosowana na roboczej bazie i wymaga osobnego
checkpointu SQL oraz okna operacyjnego. Lokalne Admin HTTP jest gotowe, a UI
pozostaje celowo bez zmian.

## Goal

Rozdzielić logiczną etykietę symbolu, jakość bieżącego cropa i możliwość użycia
cropa w treningu; przypiąć topologię planszy do wersji reguł oraz dostarczyć
osobne workflowy walidacji geometrii i rozwiązywania nieczytelnych symboli.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- topologia planszy przypinana z wersji reguł przed pierwszym importem,
- niezależne stany geometrii, etykiety, jakości i proweniencji cropa,
- `?` jako wartość domenowa, a nie symbol katalogowy,
- topologicznie poprawna geometria i source-direct cropy,
- osobna walidacja geometrii oraz rozwiązywanie nieczytelnych pól,
- unknown w wyszukiwaniu, datasecie, snapshotach i payoutach,
- bezpieczne kohorty treningowe po recropie,
- usunięcie legacy storage dopiero po pełnym cutoverze.

## Out of scope

- zastępcze zdjęcie jednej planszy — osobny task wersji 0.10,
- automatyczny detektor dla topologii innych niż jawnie wspierane,
- osobna tabela kolejki nieczytelnych plansz,
- zapis JPEG-a z narysowanym overlayem,
- migracje, API i UI w TASK 1.

## Acceptance criteria

- [x] Czysta domena definiuje topologię bez nowej stałej 15.
- [x] Geometria rozróżnia `needs_validation`, `needs_correction` i `approved`.
- [x] Komórka rozróżnia etykietę, jakość i proweniencję cropa.
- [x] Recrop zachowuje zatwierdzoną etykietę, ale wyłącza nowy crop z treningu.
- [x] `grid_issue` wraca jako pending, a `unreadable` można rozwiązać symbolem
  albo logicznym `?` bez kwalifikowania cropa do treningu.
- [x] Agregacja planszy uwzględnia zatwierdzenie geometrii i topologię.
- [ ] Migracje 0073–0075 i backfill są wdrożone i odebrane.
- [ ] Pipeline, API, Admin, Reviewer, dataset, mobile i payout przeszły cutover.

## Progress

### v0.9.1 — model domenowy i blokada topologii

- Dodano `BoardTopology`, przypięcie do wersji reguł oraz walidację niezmiennych
  wymiarów.
- Dodano wyliczany stan review geometrii z pierwszeństwem `grid_issue`.
- Rozszerzono czystą domenę komórek o `quality_issue`, tożsamość zatwierdzonego
  cropa, stan proweniencji i pełny predykat `trainingEligible`.
- Recrop zachowuje bezpieczną decyzję logiczną. Nowe piksele pozostają
  nietreningowe do jawnego zatwierdzenia; pole z błędem siatki wraca do pending.
- Zachowano kompatybilność aktualnych rekordów bez proweniencji. Do czasu
  migracji 0073 nie są one uznawane przez nową bramkę treningową.
- Nie zmieniono SQL, ORM, HTTP, workera ani UI.

### v0.9.2 — addytywny schemat i backfill 0073

- Migracja `0073_topology_geometry_crop_provenance` dodaje przypięcie topologii
  gry, snapshot wymiarów i zatwierdzenie geometrii planszy, jakość cropa oraz
  dokładną tożsamość cropa zatwierdzonego z etykietą.
- `has_grid_issue` pozostaje tymczasowo dostępne. Odczyt preferuje
  `quality_issue`, ale rozumie legacy bool; bieżące mutacje zapisują oba pola.
- Dodano append-only `image_board_geometry_review_events` oraz rozszerzono
  istniejący audyt komórek o jakość i proweniencję zatwierdzonego cropa.
- Bounded backfill blokuje grę podczas przypinania najnowszej zgodnej wersji
  reguł, przetwarza maksymalnie 200 plansz w transakcji i nie zgaduje topologii
  przy niespójnych danych.
- Plansze `accepted/corrected` otrzymują zatwierdzenie bieżącej geometrii,
  jednoznacznie ręczne rewizje również mogą zostać uznane za zatwierdzone, a
  pipeline'owe pending pozostają `needs_validation`.
- Zatwierdzone komórki otrzymują bieżącą tożsamość zatwierdzonego cropa.
  Backfill nie kopiuje obrazów i nie tworzy sztucznych eventów.
- `scripts/backfill_v09_schema.py` zapisuje atomowy checkpoint po każdej
  zatwierdzonej partii. Powtórzenie jest idempotentne; raport końcowy wymienia
  braki topologii, geometrii, jakości i proweniencji.
- Cykl migracji 0072 → 0073 → 0072 → 0073 przeszedł na izolowanej bazie
  testowej. Migracja i backfill nie zostały uruchomione na danych użytkownika.

### v0.9.3 — topologiczna geometria i source-direct cropper

- Nowy snapshot importu przypina `gridRows`, `gridColumns`,
  `topologyRulesVersionId` i fingerprint topologii; wersja reguł zostaje
  atomowo przypięta pod blokadą rekordu gry.
- Generyczne wyprowadzenie quadów, source-direct cropper i ręczny preview
  obsługują dowolne poprawne `rows × columns`, zachowując row-major i dokładnie
  jeden finalny `warpPerspective` na komórkę.
- Automatyczny adapter `board-cell-processing-v20-verified-v19-v1` pozostaje
  jawnie 3 × 5. Inna topologia jest blokowana kodem
  `IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED`, bez uruchomienia częściowego pipeline'u.
- `recognized_boards` otrzymuje snapshot wymiarów użytych przez nowy pipeline,
  a manifest odroczenia wiąże wymiary i wersję reguł z checksumą.
- Historyczne snapshoty, manifesty i fingerprint croppera bez topologii nie
  zmieniły bajtów ani interpretacji 3 × 5.
- Celowane testy worker/API, Ruff, ograniczony mypy oraz OpenAPI z generowanym
  klientem przechodzą. Baza użytkownika nadal pozostaje na 0072.

### v0.9.4 — atomowa synchronizacja geometrii, etykiet i cropów

- Wspólny koordynator storage zatwierdza dokładnie bieżącą rewizję geometrii,
  zapisuje append-only event i zwiększa rewizję katalogu najwyżej raz w
  transakcji.
- Agregacja planszy wymaga kompletnej liczby komórek wynikającej ze snapshotu
  topologii oraz zatwierdzonej bieżącej geometrii. Domknięcie korzysta z
  istniejącego mechanizmu decyzji planszy, więc canonical, staging, kolejka,
  status joba i projekcja wyszukiwania zmieniają się atomowo.
- Recrop zwykłego zatwierdzonego pola zachowuje etykietę i poprzednią
  proweniencję zatwierdzonych pikseli. Nowy crop ma stan
  `changed_since_approval` i pozostaje poza treningiem do ponownego
  zatwierdzenia.
- Recrop pola `grid_issue` usuwa problem jakości i pozostawia to pole jako
  `pending`; pozostałe poprawne etykiety nie są niepotrzebnie kasowane.
- Ręczny zapis geometrii jednocześnie zatwierdza nową rewizję i próbuje
  ponownie zmaterializować decyzję planszy wyłącznie wtedy, gdy wszystkie
  logiczne etykiety są kompletne.
- Celowane testy ścieżek API/worker oraz dwa izolowane testy PostgreSQL
  potwierdzają rollback całej planszy, idempotentne zatwierdzenie geometrii i
  dokładną tożsamość cropa po ponownej weryfikacji.

### v0.9.5 — API kolejki walidacji geometrii

- Dodano lokalne endpointy listy game-wide, checksum-bound źródła, szybkiego
  zatwierdzenia oraz topology-aware preview i zapisu rewizji.
- Lista używa wyłącznie bieżącego właściciela `image_board_search_fast_documents`,
  keysetu `(sequence_number, review_item_id)` oraz cursorów związanych z grą,
  widokiem, importem i kierunkiem. Limit domyślny to 25, maksymalny 100.
- Zatwierdzenie pod blokadą ponownie sprawdza rewizję decyzji i geometrii,
  checksumę oraz wymiary źródła i przypiętą topologię. `grid_issue` blokuje
  zatwierdzenie do czasu zapisania poprawionej rewizji.
- Asset ponownie sprawdza SHA-256 przed wysłaniem. Klient nie przesyła ścieżki
  ani aktora.
- Odpowiedź zapisu geometrii obsługuje dynamiczne `rows × columns` i nie
  dziedziczy historycznego constraintu dokładnie 15 komórek.
- OpenAPI i generowany klient zostały zaktualizowane. Celowane testy domeny,
  API i OpenAPI oraz izolowany test PostgreSQL przechodzą.

#### Outcome TASK 5

- Ruff dla zmienionych modułów: bez błędów.
- Celowane testy domeny/API/OpenAPI: `23 passed`.
- Regresja istniejącego operacyjnego review: `14 passed`.
- Izolowany test PostgreSQL bieżącego właściciela, konfliktu checksummy i
  zatwierdzenia: `1 passed`.
- OpenAPI check, typecheck i test wygenerowanego klienta: `47 passed`.
- Ograniczony mypy dla nowych modułów domeny/aplikacji/repozytorium: bez
  błędów. Pełny mypy repozytorium nadal raportuje wcześniejsze braki `py.typed`
  workera oraz niezwiązany błąd repozytorium kohort.
- Globalny `format:check` pozostaje czerwony wyłącznie na wcześniejszych,
  niezwiązanych plikach `apps/admin/next-env.d.ts`,
  `apps/reviewer/next-env.d.ts` i
  `apps/admin/test/reviewer-access-state.test.mjs`; nie zmieniano ich w TASK 5.
- Migracji 0073 ani backfillu na danych użytkownika nie uruchamiano.

## Następny etap

Checkpoint operacyjny TASK 2 pozostaje: migracja 0073 i bounded backfill na
danych użytkownika dopiero po zakończeniu aktywnych pipeline'ów. Następny etap
implementacyjny to TASK 6 — UI „Zatwierdzanie cięcia siatki”.

### v0.9.6 — UI „Zatwierdzanie cięcia siatki”

- Lokalny Reviewer korzysta z game-wide kolejki TASK 5 zawężonej do wybranego
  importu. Dostępne są widoki `needs_validation`, `needs_correction` i `all`.
- Jeden checksum-bound oryginał jest renderowany w canvasie z dynamicznym
  overlayem. Skróty `Enter` i `F` zatwierdzają i przechodzą dalej; blokada
  klienta zapobiega podwójnemu submitowi.
- Korekta obsługuje cztery kliknięcia LT/PT/PD/LD, drag narożnika, drag całej
  siatki, undo, reset oraz topology-aware preview `rows × columns`.
- Widok geometrii nie pobiera katalogu ani nie edytuje symboli. Nie zapisuje
  osobnego obrazu overlay.
- Zdalny Reviewer pozostaje na dotychczasowej ścieżce scope-bound. Jego proxy
  nie dostało dostępu do nowych endpointów Admin API. Lokalny legacy workflow
  pozostaje do odbioru za `REVIEWER_GRID_VALIDATION=legacy`.

#### Outcome TASK 6

- Dodano 7 celowanych testów stanu i kontraktu nowego workspace'u; wszystkie
  przechodzą.
- Reviewer lint, typecheck i produkcyjny build przechodzą.
- Build Admina pozostaje zablokowany przez wcześniejszą, niezwiązaną
  niekompletność TASK 7: `operationLabel` nie obsługuje jeszcze akcji
  `mark_unreadable` w `symbol-review-workspace.tsx`. Plik nie był zmieniany w
  TASK 6.
- Pełny zestaw Reviewera zachowuje wcześniejszą, niezwiązaną regresję testu
  nawigacji malejącej zdalnej selekcji. Pozostałe testy, w tym nowy pion,
  przechodzą.
- Migracji 0073 ani backfillu na danych użytkownika nie uruchamiano.

## Następny etap po TASK 6

TASK 7 — rozdzielenie `Nieczytelnego symbolu` od `Złej siatki`.
