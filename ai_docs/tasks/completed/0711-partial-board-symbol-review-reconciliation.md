# TASK-0711 — Uzupełnienie istniejących danych i odbiór

## Status
`done`

## Goal
Preview dokładnie 70 numerów, owner/revision-bound retry/checkpoint/human protection; apply tylko osobno zlecone; 1050 pozycji po operacji, audyt pozostałych gier read-only.

## Context
Użytkownik 2026-09-27 zlecił cały zaakceptowany plan T1–T4.
Właściciel reguł: ai_docs/delivery/PARTIAL_BOARD_SYMBOL_REVIEW_EXECUTION_PLAN.md,
sekcja T4. Obce zmiany z wejściowego git status zachować.

## Dependencies / entry conditions
TASK-0708–0710 odebrane. Wymagana ponowna kontrola kodu i stanu przed implementacją.
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
Wykonać kompletną sekcję T4 zaakceptowanego planu.
Outside po przypisaniu należy tylko do rzeczywistego symbolu, zachowując badge.
Widoczność jest niezależna od wyniku rozpoznania. Nie wymyślać obrazu/checksum.
Nie nadpisywać operatora, nie obchodzić routingu V2 i CAS.

### Odczytowy punkt odniesienia 2026-09-27

- Gra 777 / bfc4f949-5c14-4850-b02a-db99610bcfa5, schemat produkcyjny 0125.
- 70 bieżących właścicieli, 985/1050 pozycji, brak duplikatów aktywnej sekwencji.
  Brak 45 pozycji na 62287/62404/62440 i 20 na siedmiu innych planszach.
- 67 właścicieli pochodzi z późniejszego importu f786fed3, trzech z 5c36f4d0.
  Wybór wyłącznie stagingu 0935f4ba byłby błędny.
- Żadna z 70 plansz nie ma fast search document. Nie używać istniejącego
  backfillu opartego wyłącznie o te dokumenty do wyboru zakresu naprawy.
- Wstępna ocena board_geometry: 829 full / 201 partial / 20 outside.
  Finalne preview musi ponownie sprawdzić właściwą aktualną rewizję, ownera
  i źródło; liczby nie są regułą klasyfikacji ani wynikiem zastosowanej naprawy.
- Dane pomocnicze odczytu w work/partial-board-review; nie są trwałym
  kontraktem narzędzia ani checkpointem produkcyjnej operacji.
- Apply wymaga potwierdzenia rewizji oraz trwałego pokwitowania w tej samej
  transakcji co pozycje. Sam zapis lokalnego pliku po commicie nie wystarcza
  dla utraty odpowiedzi i restartu. Nie nadpisywać historycznych manifestów.

## Out of scope
Trening, push/merge, destrukcyjne migracje, produkcyjne apply bez osobnego kroku.

## Expected files
Nowe narzędzie preview/apply i raport w scripts/ oraz artifacts/; wspólny coordinator T1; nowa instrukcja operatorska.

## Acceptance criteria
- [x] Narzędzia preview/apply/audit i trwałe wznowienie przygotowane; preview dokładnie 70 numerów odebrane. Produkcyjne 1050 pozycji i audyt pozostałych gier są odbiorem osobno zlecanego kroku danych, nie wynikiem tej implementacji.
- [x] Testy powiązanych regresji i przypadków brzegowych.
- [x] Niezależny audyt bez P0–P2.
- [x] Dokumentacja i Outcome, osobny wersjonowany commit.

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
### Changed
- CLI preview/apply/audit/rebuild-counts: exact pilot, 5 nowych prób apply,
  maks. 50 plansz audytu, maks. 3 partie liczników po 10000; domyślna partia 5000.
- Migracja rozszerzająca 0128 i publiczne receipty PK(game,preview SHA,sequence),
  jawny SHARED routing i FK CASCADE zgodny z cyklem gry. Projekcja i receipt
  commitowane razem przez transakcję caller; plik raportu nie jest checkpointem.
- Pełny CAS właściciela, źródła, geometrii i decyzji; rzeczywisty SHA/wymiary
  źródła, ochrona etykiet/jakości/zatwierdzeń V2. Replay nie resetuje późniejszych
  zmian operatora. Blokery jawne w raporcie i kodzie zakończenia CLI.
- Wspólny resolver geometrii preview/writera: przypięty source revision,
  unikalny positionIndex (także luki), poprawny fallback null symbolGridQuad;
  legacy korzysta z bieżącej rewizji ręcznej.
- Powiązana regresja API sparse: asset pola jest wybierany po cell_index,
  nie pozycji w skróconej liście; brak obrazu daje kontrolowany not-found.
- Odbudowa liczników jest osobnym, ograniczonym poleceniem po 70 receiptach;
  wznawia trwały kursor i odmawia pozornego sukcesu przy failed projection.

### Verification results
- Focused 48 PASS / 8.61 s: test_partial_board_reconciliation,
  test_partial_board_reconciliation_cli, test_sparse_operational_cell_assets,
  test_symbol_cell_source_visibility, test_qualified_cell_reconciliation,
  test_game_data_v2_schema, test_symbol_count_rebuild_interleaving,
  test_image_symbol_review_backfill_storage (`pytest -q --basetemp=.venv/t711c`).
- Końcowe domain/CLI/schema 18 PASS / 2.67 s (`--basetemp=.venv/t711d`);
  częściowo pokrywają powyższe testy. Ruff/format 15 plików i mypy 8 modułów PASS.
- Niezależny audyt gpt-6-astra/medium: 9 domain/pinned/sparse + 5 CLI PASS;
  brak otwartych P0–P2. Kontrola manifest scope/SHA, nullable assets,
  ochrony decyzji, receipt/replay, sparse slots i bounded resume.
- Rzeczywisty PostgreSQL na unikalnych, izolowanych bazach: testy naprawy
  5 PASS / 29.34 s. Sprawdzono 15 pozycji, dwa brakujące pola przy zachowanej
  ręcznej decyzji, rollback po zapisie projekcji, konflikty owner/geometry/source,
  niepoprawny manifest przed replay i ponowienie w dwóch nowych procesach Python.
- Końcowa wspólna regresja PostgreSQL: 6 PASS / 41.86 s, moduły
  integration/test_partial_board_reconciliation_postgres.py oraz
  integration/test_outside_current_owner_postgres.py (`pytest -q --tb=short
  --show-capture=no --basetemp=.venv/t711final`, GAME_PREDICTOR_RUN_POSTGRES_TESTS=1).
  Potwierdzono również wcześniejsze decyzje/bulk bez fast document po zmianie
  wspólnego resolvera. Lint/format testu integracyjnego PASS.
- Preview produkcyjnego schematu 0125 wykonano wyłącznie READ ONLY / REPEATABLE
  READ. 70 ready, 0 blockerów, 985 istniejących / 65 brakujących, 829 full /
  201 partial / 20 outside. 67 ownerów z późniejszego importu f786fed3, 3 z 5c36f4d0.
- Dwa osobne procesy preview dały ten sam SHA
  `a964291d5517751f0761842d975fef74df4e1c77a8365d26977a6718f8e7e515`.
  Pełny plik: `artifacts/partial-board-symbol-review/20260927T012958Z/pilot70-preview.json`;
  ignorowany w Git (około 21.6 MB), małe zestawienie 70 numerów zapisane w quality.
- Wszystkie uruchomione testy/preview miały timeout do 120 s, potomne procesy
  retry 30 s. Nie wykonano benchmarku ani pełnego skanu innych gier.

### Not completed / operational handoff
- Nie wdrożono usług, nie wykonano migracji produkcyjnych, apply ani odbudowy
  liczników. Odbiór 1050 dostępnych pozycji i nowego procesu usług następuje
  dopiero po osobno zleconym wdrożeniu i kroku danych, zgodnie z planem.
- Po odbiorze pilota pozostaje read-only audit pozostałych gier; przygotowano
  ograniczoną komendę, nie rozszerzano zakresu naprawy.
- Nie wykonano push, merge, treningu ani restartu komputera.

### Documentation updates
- D-452; DATA_MODEL i VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.
- PARTIAL_BOARD_SYMBOL_REVIEW_RUNBOOK.md: kolejność backup/migracje/usługi/
  preview/apply/counts/odbiór i PowerShell.
- PARTIAL_BOARD_SYMBOL_REVIEW_PILOT_PREVIEW.md: konkretne 70 numerów i braki.
- CURRENT_STATE oraz Outcome i osobny commit.

### Recommended next task
- Osobno zlecone wdrożenie i uzupełnienie zatwierdzonego pilota po backupie,
  według runbooka; dopiero po nim odbiór 1050 i audit innych gier.

### Commit
- v1.7.16 / a4c38cacefc62edffe116b485f6497f708ba71d2; potwierdzono git show --stat i pozostały status.
