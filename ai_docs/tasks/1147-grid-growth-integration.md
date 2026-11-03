# TASK-1147 — Integracja przyrostu korekt i wymiany źródeł

## Status

`in_progress`

## Goal

Połączyć obie zatwierdzone funkcje w jednym grafie Alembic 0178 po 0177, zachowując ochronę historii, wymiany źródeł i uczenia, a następnie wykonać skoordynowane wdrożenie i odbiór.

## Context

Operator zatwierdził integrację, push, migrację, restart i odbiór. Wykonawca przygotowuje wyłącznie worktree; prowadzący koordynuje późniejsze operacje z oknem mającym wyłączną kontrolę root/main/usług/bazy.

## Dependencies / entry conditions

Nasza baza `7881711b` (v1.7.542); stabilny import `60f50c64` obejmuje wdrożenie symboli, wymianę źródeł i TASK-1146. Merge rozpoczęty bez commita w `D:/game_predicotr/worktrees/grid-correction-growth`. Bez zmian historycznych audytów i już wdrożonych migracji 0172–0177.

## Recommended execution

`gpt-6-astra` / `high`; focused `claude-opus-5-5` / `high` przed commitem prowadzącego. Sprzeczność ochrony domeny albo konieczność zmiany danych wymaga eskalacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md`
- `ai_docs/requirements/VISION_LAB.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/delivery/777A2_READABILITY_REPLACEMENT_PLAN_20261102.md`
- `ai_docs/delivery/777A2_PHYSICAL_SOURCE_PURGE_PLAN_20261103.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md` — wyłącznie konflikty D-582/D-583.
- `ai_docs/archive/CURRENT_STATE_2026Q4.md` — wyłącznie kolidujące sekcje merge.

## Scope

Rozwiązanie konfliktów, zachowanie dokumentów obu historii, ograniczenie okna stanu i indeksu decyzji, parent 0177 dla migracji 0178, jeden head i readiness 0178, zgodny OpenAPI/SDK, testy integracji obu pionów.

Po zwolnieniu okna operacyjnego prowadzący wykonuje zatwierdzone scalenie/push, migrację, restart i odbiór według planu. Wykonanie tych kroków pozostaje obecnie zablokowane; gotowy kod nie oznacza ukończenia całego zadania.

## Out of scope

Wykonawca nie zmienia root/main, usług, bazy operatora ani modeli. Nie wykonuje commita, audytu ani push. Nie naprawia znanych niezwiązanych błędów reset_game/stats.

## Technical notes

0175 dodaje SQL strażników current/retired/reserved oraz blokadę sequence-ownership. 0178 zastępuje te same funkcje, więc samo przepięcie parent usunęłoby ochronę. Prowadzący zaakceptował mały wspólny helper z dokładnym strażnikiem 0175, używany przy instalacji v6 oraz odtworzeniu v4/v5 na downgrade do 0177. Funkcje upgrade/downgrade zachowują strukturę; logika uczenia i zwolnień nie zmienia się. Gwarancja identycznego wygenerowanego SQL jest celowo zastąpiona zachowaniem obu ochron.

## Expected files

- Konflikty dokumentacyjne: CURRENT_STATE, archiwum Q4, DOC_INDEX, indeksy decyzji i pełne wpisy; żadna sekcja historyczna nie ginie.
- `0178_grid_correction_growth.py`, `schema_readiness.py`, aktywne testy readiness/migracji.
- Proponowany `storage/source_recording_replacement_sql.py`; integracja z `source_recording_sql_v6.py`.
- Test PostgreSQL ochron rejestru po upgrade i downgrade; istniejące testy partial v1/v2 i UI.
- Generowane OpenAPI/SDK i mapa; dokumentacja planu, domeny, verification.

## Acceptance criteria

- [x] Jedyny head 0178, parent 0177, zachowane starsze rewizje.
- [x] SQL chroni wycofane i zarezerwowane źródła po upgrade oraz downgrade; historia i replay pozostają bezpieczne.
- [x] Zachowane funkcje obu gałęzi, kontrakty, partial v1/v2 i UI.
- [x] Dokumenty obu historii zachowane, okna i budżety przechodzą kontrolę.
- [x] Wymagane testy, lint/types/build worktree i focused audyt rozliczone przed commitem; standardowy build root jest częścią odbioru operacyjnego.
- [ ] Skoordynowane wdrożenie i odbiór operatora wykonane po usunięciu blokady przez uprawnionego koordynatora.

## Test cases

Readiness poprzednich rewizji; 0177 → 0178 → 0177 → 0178; guarded downgrade z historią; retired/reserved źródła i utrwalony replay; atomowe zwolnienia rezerw v1 i hard v2; partial controls obu polityk; odświeżanie i ręczna aktualność oceny; API klient obejmuje oba zestawy metod.

## Verification

Każde skończone polecenie z timeout do 120 s, jawny workdir i PYTHONPATH worktree. Disposable PostgreSQL. Audyt organizuje prowadzący. Wyniki w `quality/TASK-1147_VERIFICATION.md`.

## Risks / open questions

Wdrożenie napotkało `GAME_STORAGE_LIFECYCLE_IN_PROGRESS`: stary running delete gry z 2026-10-20. Operator następnie osobno zatwierdził dokończenie usuwania pustej gry 777v2 wraz z pozostałą konfiguracją i przypisaniem. Zgodę odczytano w czacie koordynatora `01a19d0a-ab63-7200-a96b-9ac0237d662e`. Koordynator realizuje lifecycle i wcześniejszą migrację do 0177; do jawnego przekazania okna zachowuje wyłączną kontrolę usług, root/main i bazy.

## Outcome

### Changed

Merge `60f50c64` do gałęzi o HEAD `7881711b` przygotowany bez commita. Wszystkie dziewięć konfliktów rozwiązane i oznaczone w indeksie. 0178 ma parent 0177 i zachowuje dokładny strażnik 0175 przez wspólny helper zarówno w nowym SQL v6, jak i przy przywróceniu v4/v5. Logika splitu, release i obu polityk pozostaje niezmieniona. OpenAPI i klient wygenerowane ponownie; wrapper zachowuje metody obu funkcji.

### Verification results

PG guarded migration wraz z current/retired/reserved/retention na 0178 → 0177 → 0178 PASS; core registry z restartem PASS; rzeczywiste replacement guards PASS. API/worker 104 PASS, evaluator v1/v2 z restartem 5 PASS, UI 74 PASS, requesty klienta 9 PASS. Ruff 11 plików i mypy 8 modułów PASS; TypeScript Admin/klienta, ESLint i build Admina PASS z lokalnymi aliasami. Docs:check PASS, budżet 44765/45000 B. Pełne sekcje archiwum stanu i decyzji obu rodziców zachowane, potwierdzone porównaniem tekstu. Szczegóły i znane porażki retencji: `quality/TASK-1147_VERIFICATION.md`.

### Not completed

Focused Opus 5.5/high R1: PASS, bez P0/P1. Raport: `quality/TASK-1147_AUDIT_claude-opus-5-5.md`. Kod integracji zapisano w checkpoincie `08a9ffcf`; kolejna synchronizacja pozostaje bez commita. Ten wykonawca nie zmieniał main, bazy ani usług operatora. Koordynator zakończył osobno zatwierdzony lifecycle i wdrożenie do 0177; odbiór 0178 nadal oczekuje na przekazanie okna operacyjnego. Zadania nie zamknięto i nie zgłoszono wdrożenia 0178 jako wykonanego.

### Documentation updates

Plan, aktualna architektura i kontrakt, CURRENT_STATE, DOC_INDEX oraz rozwiązane indeksy/archiwa obu historii. Historyczne audyty i ukończone zadania bez zmian treści.

### Recommended next task

Przegląd i zapis synchronizacji ze stabilnym main, następnie skoordynowany odbiór 0178 w ramach tego samego planu.

### Audit dispositions

- Opus R1 PASS obejmuje wąski kod integracji; nie jest ponownym audytem całego przychodzącego pionu ani dowodem wdrożenia. Raport statyczny zachowany bez zmian.
- P2-1/P2-3: zamknięte. Końcowe 29 unit/readiness oraz trzy PG PASS; ruff check/format bez fix 12 plików i scoped mypy 8 modułów PASS. Dodatkowy test zgodności SQL w jednej rundzie poprawek; wyniki w verification.
- P2-2: otwarta bramka odbioru. Po fast-forward root wymagane normalne typecheck i build Admina bez tymczasowych aliasów; dotychczasowy build worktree nie dowodzi tego kroku.
- P2-4: prowadzący akceptuje odłożenie dwóch zastanych FAIL retencji do osobnej naprawy. Zmiana nie wprowadza ich; obecne zabezpieczenie produktu jest fail-closed. Ryzyko i dowód baseline zapisane również w CURRENT_STATE. Nie zgłaszamy pełnego quality PASS.
- P2-5: potwierdzona przez koordynatora rewizja operatora to 0171. Przed migracją ponownie odczytać tożsamość bazy i rewizję; niespodziewane 0178 blokuje automatyczną kontynuację do czasu sprawdzenia rzeczywistego schematu i strażników. Instrukcja dopisana do planu.
- Bez drugiego audytu: brak uwag P0/P1 i zmian zachowania produktu w tej rundzie; nowe testy i udokumentowane bramki operacyjne. Task pozostaje in_progress, bez task-close przed odbiorem wdrożenia.

### Integration checkpoint

Integrację kodu zapisano jako v1.7.543 / `08a9ffcf`. Checkpoint nie zamyka
TASK-1147; odbiór operatora i task-close nastąpią po zatwierdzonym wdrożeniu.

Po zgodzie koordynatora przygotowano merge bez commita stabilnego
`be10f90e8d6d8121f70577be7243946ab5ee8979` do tego checkpointu. Dwa konflikty
dotyczyły wyłącznie okna i archiwum CURRENT_STATE. Zachowano pełne sekcje obu
historii, ograniczono okno do 10 zakończonych tasków i zachowano aktualne
informacje o wdrożonym 0177. Poprawka zależności React z TASK-1148, lockfile
oraz Selector 1.0.5 są zgodne z przychodzącym refem. Bez nowych zmian produktu
i bez ponawiania testów PG/UI. Kontrole synchronizacji i zachowania historii
są zapisane w `quality/TASK-1147_VERIFICATION.md`. Migracja i odbiór 0178
pozostają przed nami; root/main/usługi/baza nadal pod kontrolą koordynatora.
