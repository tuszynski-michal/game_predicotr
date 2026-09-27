# TASK-0709 — Grupy, API i decyzje pól bez obrazu

## Status
`done`

## Goal
outside, unknown i grupy symboli są spójne w list/count/cursor/bulk; nullable assets; reassign/unreadable poza zdjęciem z CAS; kompletny OpenAPI i klient.

## Context
Użytkownik 2026-09-27 zlecił cały zaakceptowany plan T1–T4.
Właściciel reguł: ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md,
sekcja T2. Obce zmiany z wejściowego git status zachować.

## Dependencies / entry conditions
TASK-0708 odebrany. Wymagana ponowna kontrola kodu i stanu przed implementacją.
Apply danych pozostaje osobno zleconą operacją.

## Recommended execution
gpt-6-sol / high; niezależny audyt gpt-6-astra / medium.
Przy nierozwiązanych P0–P2 po dwóch rundach zatrzymać zależne prace.

## Relevant docs
- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md
- ai_docs/requirements/IMAGE_INGESTION.md
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md
- ai_docs/architecture/DATA_MODEL.md
- ai_docs/process/DECISION_LOG.md

## Scope / technical notes
Wykonać kompletną sekcję T2 zaakceptowanego planu.
Outside po przypisaniu należy tylko do rzeczywistego symbolu, zachowując badge.
Widoczność jest niezależna od wyniku rozpoznania. Nie wymyślać obrazu/checksum.
Nie nadpisywać operatora, nie obchodzić routingu V2 i CAS.

### Doprecyzowania implementacyjne

- Istniejący snapshot operacji zbiorczej zapisywał tylko filter_symbol_id,
  więc NULL nie odróżniał unknown od outside/all. Rozszerzająca migracja 0127
  dodaje nullable filter_scope; historyczny NULL zachowuje dawną interpretację.
- Bieżące operacje V2 muszą używać aktualnego właściciela i rewizji również
  bez fast search document. Dotyczy list, mutacji, bulk i Nieczytelnych plansz.
- Liczniki mają marker semantyki po stronie odczytu i zapisu. Stare wyniki
  nie mogą być publikowane jako nowe; odbudowa korzysta z ograniczonych partii,
  a współbieżny zapis nie może zakończyć jej z nieaktualnym akumulatorem.
- Testy PostgreSQL koordynatora: rzeczywisty predykat grup na macierzy ośmiu
  symboli/widoczności/jakości/stanów oraz zgodność count keys, izolowana migracja
  126→127 z istniejącą partycją; 2 PASS (9,41 s). Nie jest to test całego API.

## Out of scope
Trening, push/merge, destrukcyjne migracje, produkcyjne apply bez osobnego kroku.

## Expected files
services/api/src/game_predictor_api/domain/image_symbol_reviews.py; storage/image_symbol_review_repository.py; schemas/image_symbol_reviews.py; API/application mutation/bulk; packages/admin-api-client.

## Acceptance criteria
- [x] outside, unknown i grupy symboli są spójne w list/count/cursor/bulk; nullable assets; reassign/unreadable poza zdjęciem z CAS; kompletny OpenAPI i klient.
- [x] Testy powiązanych regresji i przypadków brzegowych.
- [x] Niezależny audyt bez P0–P2.
- [x] Dokumentacja i Outcome, osobny wersjonowany commit v1.7.14 (hash po commicie).

## Test cases / verification
Testy według sekcji Testy zaakceptowanego planu; wykonawca dobiera istniejące
focused test modules i zapisuje dokładne komendy/wyniki w Outcome.
Komendy z cwd repo; timeout do 120 s, dłuższy build zapowiedziany.
Nie wykonywać mutujących testów na produkcyjnych rekordach.
T4 rozdziela odbiór narzędzi od niezleconego jeszcze apply.

## Risks / open questions
Zastane historyczne kwalifikacje wymagają odczytu geometrii.
Nowy kontrakt bez cropa wymaga spójnych odbiorców, nie fikcyjnego zasobu.
Nie raportować wdrożenia ani naprawy danych na podstawie samych testów.

## Outcome
Commit: `v1.7.14` — `f86b29e0ef84af7769ed1adc6365c99d8b89ce49`.

### Changed

- Wspólne grupowanie all/unknown/outside/symbol w SQL, count keys, kursorach
  i snapshotach bulk. Przypisany partial nie znika; outside bez przypisania
  nie dubluje unknown. Brak predykcji nie jest confidence zero.
- sourceVisibility i jawny assetMode none z nullable tożsamością obrazu:
  backend, OpenAPI, wygenerowany klient, wrapper i konsumenci typów.
- Mutacje pojedyncze i bulk, listy oraz Nieczytelne plansze używają bieżącego
  właściciela V2 bez zależności od fast search document. CAS zachowany.
- Żadne ręczne przypisanie pola bez obrazu nie tworzy approved cropa;
  partial/outside pozostają wykluczone z treningu także po zmianie jakości.
- Migracja 0127 utrwala filter_scope; count checkpoint ma marker semantyki
  i jest resetowany po współbieżnych zmianach. Stare liczniki nie udają gotowych.
- Istniejący operational detail dopuszcza 0–15 rzeczywistych cropów, nadal
  udostępnia źródło i geometrię. Nie dodano równoległego endpointu podglądu.
- Realny test PostgreSQL wykrył JSON null vs SQL NULL dla render_spec;
  poprawiono binding ORM i wymuszone czyszczenie przy przejściu do outside.
  Historyczna aktualizacja oraz identyczne retry są objęte regresją.

### Verification results

- Wykonawca: 67/67 focused PASS; końcowy dodatkowy zestaw domeny/outside/
  unreadable/backfill 40/40 PASS (zestawy częściowo się pokrywają).
- JS 77/77 PASS, TypeScript Admin/client PASS, mypy 10 modułów PASS,
  Ruff kod/testy/migracja PASS, ESLint 4 zmienione pliki PASS bez ostrzeżeń,
  OpenAPI --check i generated drift PASS, git diff --check PASS.
  Pełny build Admina zaplanowany w T3. Testy TSX wymagały uruchomienia poza
  sandboxem z powodu błędu os.userInfo; nie zmieniano profilu środowiska.
- Niezależny Astra medium: 70/70 PASS, bez P0–P2; w tym cztery dodane przez
  audytora regresje przerwania/resetu/wznowienia odbudowy liczników.
- Koordynator, prawdziwy PostgreSQL: 2/2 PASS dla macierzy grup/liczników i
  migracji 126→127 z istniejącą partycją; 1/1 PASS dla zapisu przez koordynator,
  JSON null, retry, listy i decyzji bez fastdoc, ponownych sesji bazy, 15 pól
  Nieczytelnej planszy, snapshotu outside, workera bulk i jego ponowienia.
  Po retry dokładnie jedno zdarzenie operacji; brak sztucznego approved cropa.
- Koordynator, istniejące API szczegółów i źródła: 3/3 PASS dla 0/3/15 cropów,
  geometrii i checksum oraz odrzucenia zmienionego pliku źródłowego.
- Testy bazy używają unikalnych baz game_predictor_task0708_*; żadnego zapisu
  do bazy operatora. Ponowne sesje i serializowany checkpoint nie dowodzą
  restartu systemu operacyjnego; taki test nie był wykonywany.
- Komendy bounded 120 s: pytest modułów test_symbol_review_outside_contract,
  test_image_symbol_reviews_api, test_image_symbol_review_query_storage,
  test_symbol_count_rebuild_interleaving, test_partial_operational_source_context;
  izolowane integration/test_symbol_visibility_groups_postgres oraz
  integration/test_outside_current_owner_postgres z GAME_PREDICTOR_RUN_POSTGRES_TESTS=1.

### Not completed

- Nowy selector/kafelek/modal i statusy są T3; historyczna naprawa i odbiór
  rzeczywistych 1050 pozycji są T4. Bez wdrożenia i produkcyjnych migracji.

### Documentation updates

- ADMIN_APP, DATA_MODEL, CURRENT_STATE i niniejszy Outcome.

### Recommended next task

- TASK-0710 / T3 zgodnie ze zleceniem całego planu.
