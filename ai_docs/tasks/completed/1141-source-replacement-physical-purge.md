---

title: Fizyczne usuwanie zastępowanego zdjęcia

status: done

last_updated: 2026-11-03

---

# TASK-1141 — Fizyczne usuwanie zastępowanego zdjęcia

## Status

`done`

## Goal

Po zatwierdzonym usunięciu wybranego starego zdjęcia odzyskać miejsce jego zbędnych plików i rekordów, zachowując manifest luk i działający zwykły import nowych dziewięciu plansz.

## Context

Operator 2026-11-03 jawnie zatwierdził dodatkowy zakres i koszt. Poprzedni wariant zachowywał stare źródło i pełną historię, więc nie spełnia doprecyzowanego wymagania odchudzania. Zakończone taski pozostają historycznym dowodem poprzedniego zakresu, nie dowodem fizycznego usuwania.

## Dependencies / entry conditions

Worktree D:/game_predicotr/worktrees/777a2-readability-replacement, branch codex/777a2-readability-replacement, start d78eaf1c. Czysty przed zadaniem. TASK-1139 i 1140 zarezerwowane w równoległym GRID_CORRECTION_GROWTH_PLAN_20261103; 1141 sprawdzono w aktualnej liście worktree i najnowszych czatach. Nie integrować cudzych niezakończonych prac. Ponownie sprawdzić numery decyzji/migracji przed zapisem.

## Recommended execution

gpt-6-astra / high. Jeden wykonawca prowadzi projekt, implementację i celowane testy. Audyt claude-opus-5-5 / high w dwóch momentach: projekt przed kodem oraz gotowy pion przed commitem. Jedna runda poprawek P0/P1; nie tworzyć pętli audytów.

## Relevant docs

- AGENTS.md; ai_docs/process/DEFINITION_OF_DONE.md.

- ai_docs/delivery/777A2_PHYSICAL_SOURCE_PURGE_PLAN_20261103.md.

- ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md.

- ai_docs/requirements/ADMIN_APP.md, sekcja Plan wymiany zdjęć.

- ai_docs/architecture/DATA_MODEL.md, sekcje manifestu i TASK-1131.

- ai_docs/architecture/API_CONTRACT.md, obszar board-sources.

- ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md; ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md.

- ai_docs/process/decisions/DECISION_LOG_2026.md, kotwice D-579 manifest wymiany i D-580 wycofanie całego źródła.

- ai_docs/quality/777A2_READABILITY_REPLACEMENT_ACCEPTANCE_20261103.md.

## Scope

Pełny pion opisany w planie: source-only purge, mały niezależny manifest/tombstone, migracja, istniejący preview/command/recovery, API/client/UI i testy. Szczegóły projektu wykonawca zapisuje poniżej przed audytem projektu i kodowaniem.

## Out of scope

Operacje na danych operatora, globalny cleanup, usuwanie modeli/aktywacji lub cudzych danych, VACUUM FULL, usługi, merge/push, nowe warianty zamienników, trening i skan detektora.

## Acceptance criteria

- [x] Manifest/request działa po fizycznym usunięciu plików i operacyjnego grafu; mały source tombstone dozwolony.

- [x] Dedykowane zarządzane oryginały/wycinki/podglądy faktycznie usuwane; współdzielone zasoby i modele pozostają.

- [x] Wszystkie numery zdjęcia pozostają lukami z rezerwacją; zwykły workflow nowego importu i weryfikacji działa.

- [x] Stare ID/SHA nadal nie mogą wrócić do current; mały tombstone jest jawnym dowodem, nie aktywnym źródłem.

- [x] Fresh preview/confirmation, atomowość, exact replay, restart i recovery sprawdzone.

- [x] API/OpenAPI/generated/wrapper/request test i UI zgodne, lint/typecheck/build/docs/map rozliczone.

- [x] Audyt projektu i gotowego pionu Opus 5.5/high, bez otwartych P0/P1; Outcome i task-close/commit/hash.

## Technical notes

Projekt wykonawczy D-583 i macierz w zaakceptowanym planie (sekcja Projekt wykonawczy) są obowiązującym kontraktem. Rezerwacja0177; jeden source-only adapter, compact mode replace_delete_source, action purge, source_images.purged_at i odpięcie frozen FK do efemerycznych rodziców. Bez zmiany istniejącego preserve_history. Szczegóły: zamknięty zakres DELETE, niezbędne zależności, schema/FK/tombstone, fazy i recovery, integracja istniejącego endpointu, liczniki oraz konkretne istniejące komendy testowe z timeoutami. Nie stosować pełnego generic delete graph (usuwa modele/kohorty) ani globalnego obejścia retention.

## Expected files

Istniejące: application/cleanup.py:CleanupService/ManagedCleanupArtifactStore; storage/cleanup_repository.py:SqlAlchemyCleanupRepository; storage/source_replacement.py:SourceReplacementRepository; storage/source_replacement_retirement.py:SourceRetirement; storage/source_replacement_guards.py; API/schema cleanup/source_replacement; istniejący panel features/cleanup/source-replacement-panel.tsx; OpenAPI/generated client/wrapper; właściwe wymagania/architektura/proces i mapa.

Proponowane: dedykowany adapter source-only purge, migracja Alembic i testy PostgreSQL/FS/HTTP/UI. Ścieżki, zakres FK i test commands potwierdzone w sekcjach Pliki i granice/Zaplanowane dowody planu.

## Test cases

Planowane kryteria i ograniczenia w sekcji Weryfikacja i odbiór planu. Bez benchmarków ani danych operatora.

## Verification

Dokładne komendy planowane zapisano w planie, nowe pliki testów oznaczono jako planowane; timeout zwykle120s, audit480s. Python D:/game_predicotr/.venv/Scripts/python.exe; nie modyfikować root node_modules junction do main.

## Risks / open questions

Nowe znaczenie usunięcia jawnie zastępuje wcześniejszą bezterminową retencję operacyjnego starego zdjęcia; modele i cudze dowody nie stają się zbędne. Konkretne zależności rozstrzyga projekt i audyt. Zgoda na mechanizm nie oznacza zgody na wykonanie usuwania bez realnego preview.

## Outcome

Commit: v1.7.535 (hash dopisuje kolejny commit).

Projekt D583 zapisany. Audyt projektu Opus5.5/high R1 REVISE (actual modelUsage claude-opus-5-5): cztery P1, bez P0. Jedyna korekta projektu: wspólny exact-path predykat, unfinished-import i aktywni konsumenci, jawna klasyfikacja FK oraz ambiguous-COMMIT recovery. Targeted PLAN R2 PASS, actual modelUsage claude-opus-5-5/high; brak P0/P1. Implementacja gotowa do audytu końcowego.

### Verification results

- Owned PostgreSQL physical pion: ostatni 1 PASS /31,68s (t1141-pg10). Dziewięć boards, source-only DELETE i pliki, sąsiad tego samego joba oraz shared path innej gry zachowane; rollback, COMMIT+lost acknowledgement+restore→nowa sesja GET/replay, exact request i nowe staging/job/discovery admission po purge. Grid busy odmawia przed mutacją; znany source asset zwraca SOURCE_PURGED. Wcześniejsze nieudane próby rozszerzonego fixture dotyczyły JSON NULL/statusu/revizji/virtual provenance i bind przed savepoint, nie były zaliczone jako PASS.
- Frozen PostgreSQL:1 PASS /25,48s (t1141-frozen-04).9boards/9reviews/135cells, cohort/item/virtualcell/reference/model/activation to_jsonb bez zmian po nowej sesji, SHA reference i stubweights zachowane; trained blocker przed DB/FS; nowe INSERT trzech frozen tabel odmawiają. Bez neural inference.
- FS/HTTP/legacy:27 PASS /16,77s (t1141-unit01). Końcowe miniatury/HTTP:3 PASS /8,43s (t1141-unit02): foreign-file recovery_required bez nadpisania, tylko własne pary atlas JSON/WebP usuwane, mieszane i cudze pozostają.
- UI/wrapper:11 PASS; scoped Admin TypeScript, ESLint, Prettier PASS. Helper b2a_selection tylko panel/wrapper/testy; implement_b1 tylko frozenPG test. Obaj gpt-6-astra/high według przypisania taska; jeden wspólny audyt/commit.
- Ruff18zmienionych plików PASS. Scoped mypy14modułów PASS: --follow-imports=skip --disable-error-code=no-any-return --allow-untyped-decorators --no-warn-unused-ignores --allow-subclassing-any. To nie pełny backend ani kontrola importowanych zależności.
- Resolver wskazuje lokalny WT; client build4,33s i rzeczywisty Next Admin build22,88s PASS. Checked finally odpiął wyłącznie własne app-local junctions; root/main bez zmian. OpenAPI current, generated drift, code map i cztery checkery docs PASS.

### Komendy i ograniczenia

RootPython D:/game_predicotr/.venv/Scripts/python.exe, cwd worktree. PG: GAME_PREDICTOR_RUN_POSTGRES_TESTS=1, python -m pytest services/api/tests/integration/test_source_replacement_purge_postgres.py --basetemp=D:/game_predicotr/artifacts/t1141-pg10 -q -x --tb=short --show-capture=no; analogicznie test_source_purge_frozen_postgres.py z basetemp t1141-frozen-04. Owned fixture sprawdza name/OID/capability i usuwa tylko własną bazę. HTTP/PG wymagają dostępu do lokalnych socketów.

FS/HTTP: python -m pytest services/api/tests/test_source_purge.py services/api/tests/test_source_replacement_cleanup_recovery.py services/api/tests/test_source_replacement.py --basetemp=D:/game_predicotr/artifacts/t1141-unit01 -q -x --tb=short; końcowy test_source_purge.py w t1141-unit02. Każda komenda testowa timeout120s.

Node --import tsx --import ./artifacts/task1131/react-test-setup.mjs --test: apps/admin/test-interactions/source-purge-panel.test.mjs, source-replacement-panel.test.mjs, source-retirement-actions.test.mjs oraz packages/admin-api-client/test/source-purge-request.test.mjs, source-replacement-request.test.mjs. Tsc scoped artifacts/task1131/selection-tsconfig.json z paths do WT. Build używa sprawdzonego .tooling/t1141_build.py (Admin300s, client120s). Logi D:/game_predicotr/artifacts/t1141-build/ i t1141-checks/.

### DoD / zakres

Manifest/request po DELETE: PG nowego admission. Dziewięć plansz i pliki: real PG/FS, exact counts; modeli/aktywacji i foreign danych nie usunięto. Tombstone i nowe frozen use: PG oraz dotychczasowe current predicates, retained prior.sequence_numbers zachowuje mobile proof. Trwałość: nowe sesje, rollback i utracony COMMIT; recovery_required nie nadpisuje pliku. API/generated/wrapper/UI/build: powyższe dowody. Dokumentacja D583, wymagania, model, API, import i mapa zaktualizowane. Finalny Opus R2 PASS; task-close i zapis hash wykonane w cyklu zamknięcia.

Nie wykonywano danych operatora, migracji produkcji, usług, treningu, aktywacji, merge ani push. Mechanizm odzyskuje dedykowane pliki; współdzielone atlasy i immutable metadata mają jawne liczby/powody zachowania. Nie obiecuje fizycznego shrink pliku PostgreSQL. Malformed cache descriptors pozostają w istniejącym prunerze; nie budowano nowego cache frameworka.

### Audyt końcowy R1 i jedyna runda poprawek

[Final R1](../../quality/TASK-1141_AUDIT_claude-opus-5-5_R1.md): REVISE, actual modelUsage claude-opus-5-5, high,352,9s. Jedno P1: potencjalny koszt candidate×allconsumers w retencji. Poprawiono tę samą funkcję retained: normalizacja wariantów x/data/x tylko małego zestawu wejściowego, exact path=ANY w każdej gałęzi, bez regexp/join całych tabel z kandydatami. Prefiksy dotyczą wyłącznie małego zbioru rootów modeli/kohort/eksportów. Semantyka preview/finalize pozostaje wspólna; nie uruchamiano benchmarku ani dużego fixture.

P2-1 przyjęte ograniczenie istniejącego recovery: równoległy generic cleanup może przywrócić jeszcze niezatwierdzoną kwarantannę. Stan jest wykrywany jako recovery_pending i naprawiany exact replay; nie deklarujemy zakończenia na podstawie samego COMMIT. Bez nowego koordynatora operacji. P2-2 zamknięte: fast_documents dopisane do klasyfikacji, komentarz jawnie wskazuje queue trigger zamiast globalnego resetu. P2-3 przyjęte: downgrade przed purge odtwarza poprawne FK ze standardowymi nazwami, które mogą różnić się od historycznych; po purge downgrade odmawia, bo nie odtworzy pikseli/parents. P2-4 zamknięte: projekt zgodny z SOURCE_PURGED dla znanego source i404/410 dla usuniętychboard/cell. P2-5 zamknięte dowodem panelu: po executeSourcePurge następuje await refresh(batchId); pending dodatkowo udostępnia odświeżenie/replay, bez fałszywych deletedBytes.

Targeted R2 obejmie wyłącznie poprawkę P1; brak nowej eksploracji ani kolejnych wariantów.

Po poprawce P1: istniejacy PG+FS/HTTP 4 PASS /31,18s (t1141-fix01), Ruff2moduly PASS i scoped mypy2moduly PASS. Nie jest to pomiar produkcyjnej skali; poprawka eliminuje niekorzystny ksztalt join/regexp, testy potwierdzaja semantyke.

### Wynik końcowy

[Finalny audyt R2](../../quality/TASK-1141_AUDIT_claude-opus-5-5.md): PASS, actual modelUsage claude-opus-5-5/high, brak otwartych P0/P1. R1 zachowany osobno. Jedna runda poprawek zakończona. Możliwe liniowe scans kolumn ścieżek pozostają ograniczeniem; nie ma pomiaru czasu produkcyjnego ani deklaracji skalowalności z małego fixture. Granica katalogu rootów jest zachowana, a exact/root stosują ten sam predykat preview/finalize. P2 rozliczone wyżej; bez kolejnej rundy.

DoD wykonane: spójny pion backend/migracja/API/client/UI, fizyczne pliki+PG i restart/replay, preserved models/shared, scope-only counts, dokumentacja/mapa, build/lint/scopedtypes, dwa momenty audytu i task-close. Migracja0177 jest plikiem do wdrożenia; uruchomiona wyłącznie na disposable bazach testów. Nie przeprowadzono realnego purge ani pilota danych operatora.
