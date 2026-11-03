# TASK-1145 — Uzgodniona numeracja migracji przyrostu korekt

## Status

`done`

## Goal

Przenumerować niewdrożoną migrację przyrostu korekt z 0172 na uzgodnioną 0178 bez zmiany jej działania.

## Context

Operator zatwierdził koordynację z wdrożeniem symboli w czacie `01a19d0a-ab63-7200-a96b-9ac0237d662e`. Koordynator zarezerwował dla tamtego łańcucha 0172–0177, a dla przyrostu korekt wolną 0178. Prowadzący zweryfikował zgodę oraz brak lokalnej kolizji 0178.

## Dependencies / entry conditions

TASK-1139 i TASK-1140 zamknięte, audyty R2 PASS. Baza pracy: `2c8522bc9a41b115c99b61ada4329b47a6d71f7c` (v1.7.540), worktree `D:/game_predicotr/worktrees/grid-correction-growth`. Rodzic migracji pozostaje `0171_grid_correction_learning`; integracja z obcym łańcuchem nastąpi osobno.

## Recommended execution

`gpt-6-astra` / `high`: ograniczona zmiana identyfikatora trwałego schematu. Audyt `claude-opus-5-5` / `high` organizuje prowadzący. Niezgodność grafu albo zmiana ciała migracji blokuje zadanie.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/CODE_MAP.md`

## Scope

Nazwa pliku i rewizji 0178, wymagany head w readiness, aktywne testy, bieżąca nota dokumentacyjna i mapa kodu. Testy tylko zmienionego pionu.

## Out of scope

Zmiana rodzica, kopiowanie migracji 0172–0177, merge-head, SQL capability, polityka, API/UI, historyczne raporty i zamknięte taski. Bez migracji operatora, usług, treningu, merge/push ani stage/commit wykonawcy.

## Acceptance criteria

- [x] Jedyny lokalny head to 0178 z rodzicem 0171.
- [x] Ciała upgrade/downgrade i SQL capability są identyczne z HEAD v1.7.540.
- [x] Readiness odrzuca poprzedni numer i przyjmuje 0178.
- [x] Guarded downgrade i ponowny upgrade przechodzą na disposable PostgreSQL.
- [x] Scoped lint/typecheck i mapa są spójne; historia audytów zachowana. Dokumentacja oraz docs:check sprawdzane przy formalnym zamknięciu.

## Expected files

- Rename `services/api/alembic/versions/0172_grid_correction_growth.py` na `0178_grid_correction_growth.py`; symbol `revision`.
- `services/api/src/game_predictor_api/storage/schema_readiness.py`: `EXPECTED_ALEMBIC_HEAD`.
- `services/api/tests/test_schema_readiness.py` i `services/api/tests/integration/test_grid_correction_growth_migration_postgres.py`.
- Bieżące `API_CONTRACT.md`, `VISION_LAB.md`, generowane mapy oraz nowy `quality/TASK-1145_VERIFICATION.md`.

## Test cases

Jedyny head 0178 i parent 0171; odrzucenie poprzedniego 0172; pusta historia pozwala zejść do 0171 i wrócić do head; release albo rezerwacja v2 nadal zabrania downgrade. Porównanie AST obu funkcji oraz sum SQL z bazowym commitem.

## Verification

Polecenia z worktree przez lokalny wrapper ustawiający PYTHONPATH; timeout do 120 s. Unit readiness, jeden test PostgreSQL guarded migration, scoped ruff/mypy i regeneracja mapy. Prowadzący wykonuje docs:check i audyt przed zamknięciem.

## Risks / open questions

Obca gałąź nie jest jeszcze częścią tego grafu. Nowa numeracja nie upoważnia do samodzielnego połączenia historii ani wykonania migracji operatora.

## Outcome

Commit: v1.7.541 (hash dopisuje kolejny commit).

### Changed

Migracja ma nazwę i identyfikator `0178_grid_correction_growth`; rodzic pozostaje `0171_grid_correction_learning`. Readiness oraz dwa aktywne pliki testów używają nowego head. Aktualna dokumentacja wyjaśnia zmianę numeru, zachowując oryginalne raporty i zamknięte taski.

### Verification results

Opus 5.5/high: PASS, `ai_docs/quality/TASK-1145_AUDIT_claude-opus-5-5.md`. P2-1 i P2-2 poprawiono w bieżącym planie i DOC_INDEX: jednoznaczne wskazanie 0178 oraz dodany TASK-1145. Kod nie zmienił się po audycie. Końcowe docs:check i code-map:check PASS; zamknięcie wykonano skryptem task-close.

Readiness 19 PASS (4,39 s), guarded PostgreSQL 1 PASS (25,99 s), ruff/format czterech plików PASS, mypy dwóch modułów PASS. Jedyny head 0178 i rodzic 0171 sprawdzone przez Alembic w teście. Porównanie z v1.7.540 potwierdza, że jedyną zmianą tekstu migracji jest `revision`; AST upgrade/downgrade oraz SQL v4/v5/v6 są identyczne. Mapa zregenerowana bez różnicy treści. Szczegóły w `quality/TASK-1145_VERIFICATION.md`.

### Not completed

Nie wykonano migracji operatora, połączenia historii Alembic, usług, treningu ani merge/push. Audyt PASS; zamknięcie prowadzi task-close. Aktualizacja grafu po wdrożeniu koordynatora pozostaje osobnym krokiem.

### Documentation updates

Aktualne API_CONTRACT i VISION_LAB mają notę historyczną 0172 → 0178. Plan, CURRENT_STATE i DOC_INDEX utrzymuje prowadzący; raporty R1/R2 TASK-1139/1140 pozostały nietknięte.

### Recommended next task

Koordynowany krok integracji grafu po wdrożeniu łańcucha symboli; poza zakresem TASK-1145.
