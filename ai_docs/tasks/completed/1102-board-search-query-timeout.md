---
title: Ograniczenie kosztu rankingu ciągów plansz
status: done
last_updated: 2026-10-27
---

# TASK-1102 — Ograniczenie kosztu rankingu ciągów plansz

## Status

`done`

## Goal

Usunąć powielanie kosztownych wyrażeń punktacji w SQL wyszukiwarki ciągów, zachowując kompletny ranking i limit 60 sekund.

## Context

BOARD_SEARCH_SEQUENCE_TIMEOUT występuje lokalnie i w linku. Zapytanie dwóch pełnych wzorów ma około 470 KB SQL i przekracza 60 sekund. Samo wydłużenie limitu nie rozwiązało problemu. Operator po wcześniejszym ostrzeżeniu o koszcie 20–40 minut zlecił teraz tę poprawkę w oddzielnym worktree, aby nadal pracować w uruchomionej aplikacji.

## Dependencies / entry conditions

Worktree od main b276628f, osobna gałąź codex/board-search-query-timeout. Działający checkout i trzy usługi pozostają bez zmian. TASK-1101 na osobnej gałęzi nie jest częścią tej implementacji. Numer 1102 wolny; wersje commitów wynikają z historii tego brancha, możliwa kolizja numerów v1.7.490–491 z TASK-1101 nie zmienia tożsamości commitów.

## Recommended execution

gpt-6.1-sol, reasoning high. Jeden moduł SQL i rzeczywiste testy zgodności PostgreSQL. Bez dodatkowego audytu; eskalacja przy potrzebie zmiany rankingu, schematu albo danych operatora.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md`
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-573--wyszukiwanie-po-kolejnych-układach`
- `ai_docs/tasks/completed/1099-board-search-sequence-timeout.md`

## Scope

Materializowane, wąskie wyniki punktacji raz na wzór; ranking całej populacji przed LIMIT; metadane zdjęć pobierane po ograniczeniu wyników. Testy identyczności całych punktacji i kolejności na izolowanej bazie PostgreSQL oraz kontrola wielkości SQL. Wspólny backend obejmuje Admina i linki.

## Out of scope

Restart, build i wdrożenie usług; dane i zapytania rankingowe na bazie operatora; zmiana kontraktu API, migracje, cache, benchmarki i duże fixture; merge i push.

## Acceptance criteria

- [x] Wyrażenia komórek są liczone raz na wzór, SQL nie rozrasta się przez powtarzanie w sortowaniu.
- [x] PostgreSQL i czysta domena zwracają identyczne wyniki, wszystkie składowe punktacji i kolejność dla 2–4 wzorów, luk, zawinięcia, alternatyw pending, 777a2, zakresów i limitów.
- [x] Brak obcięcia kandydatów przed rankingiem; zachowane tie-breaki oraz granica 60 s i krótsze jawne limity sesji.
- [x] Testy pionu, lint, format, typecheck modułu, docs:check i code-map:check przechodzą.
- [x] Główny checkout, uruchomione usługi i link pozostają bez zmian.

## Technical notes

Założenie: nie zmieniamy żadnej semantyki produktu ani punktacji. Materializowany CTE z licznikami i identyfikatorem pozycji zapobiega rozwijaniu CASE przez planer. Łączenie pozycji nadal modulo expected_layout_count; brakujące zdjęcia wykluczają cały ciąg. Żaden LIMIT per wzór nie jest dozwolony. Metadane i procent pojedynczej planszy są odtwarzane dopiero dla wybranych wyników w tym samym SQL i snapshotcie. SAVEPOINT i odtwarzanie ustawień sesji muszą pozostać skuteczne.

## Expected files

- `services/api/src/game_predictor_api/storage/board_search_sequence.py` — search_board_sequences.
- `services/api/tests/integration/test_board_search_sequence_postgres.py` — pełna zgodność domeny.
- `services/api/tests/test_board_search_sequence_timeout.py` — odtworzenie JIT razem z limitem sesji.
- Nowy `services/api/tests/test_board_search_sequence_sql.py` — regresja rozmiaru i etapów SQL.
- Dokumentacja techniczna, mapa kodu, task i CURRENT_STATE.

## Test cases

Wszystkie cztery wagi alternatyw; zaakceptowane ignorują alternatywy; brak dowodu i wildcard; różne liczby znanych komórek; pełne 15 komórek; 2/3/4 wzory; remisy, luki, wrap, limit 1/40/100. Istniejące testy API i timeoutu bez zmiany kontraktu. Wyłącznie własna izolowana baza *_test.

## Verification

Polecenia z worktree przez Python z głównej .venv i jawnym PYTHONPATH wskazującym worktree, timeout 120 s. Pytest plików sequence, opt-in testów PostgreSQL na własnej bazie, Ruff, mypy --follow-imports=skip, generate_code_map.py, npm run docs:check i code-map:check. Bez instalowania pakietów do współdzielonego środowiska.

## Risks / open questions

Małe testy zgodności nie dowodzą czasu na pełnej bazie operatora. Taki odbiór i wdrożenie wymagają osobnego polecenia. Nie ma pytania blokującego implementację.

## Outcome

Commit: v1.7.490 (hash dopisuje kolejny commit).

### Changed

- Zastąpiono rozwijanie tych samych CASE w SELECT, filtrze i sortowaniu przez materializowane, wąskie liczniki dowodów dla każdego wzoru. Połączenie pozycji i globalny ranking nadal obejmują całą populację; jedyny LIMIT jest po punktacji. Metadane plansz i ich procenty powstają dla wybranych wyników w tym samym SQL i snapshotcie.
- Wyłączono JIT tylko wewnątrz SAVEPOINT rankingu. Eliminuje to start kompilatora LLVM dla każdego żądania, bez trwałej zmiany ustawień bazy. Sukces odtwarza poprzednie jit i statement_timeout; błąd odtwarza oba przez rollback SAVEPOINT. Limit 60 s i krótszy limit połączenia pozostają bez zmian.
- Nie zmieniono API, klienta, danych ani punktacji. Wspólna ścieżka obejmuje lokalny Admin i oba tryby udostępniania; pojedynczy wzór nadal korzysta z istniejącej ścieżki GET.

### Verification results

- 91/91 testów: SQL, limity/JIT, czysta domena, API lokalne i publiczne oraz cały plik integracyjny PostgreSQL; 40,25 s w nowym procesie. PostgreSQL wyłącznie na własnej bazie *_test z istniejącym zabezpieczonym fixture. Zgodność całych punktacji, identyfikatorów, statusów i kolejności dla 2/3/4 wzorów, 15 pól, różnych mianowników, wszystkich czterech rang alternatyw, duplikatów alternatyw, samych niewiadomych, alternatyw bez primary, 777a2, approved/all, luk, wrap, remisów i limitów 1/40/100. Zachowano też testy migracji i logów z tego pliku.
- Generowany SQL z parametrami dla pełnych wzorów: 2 = 95302 B (wcześniej około 470444 B), 3 = 142694 B, 4 = 190642 B. Jest jeden LIMIT po rankingu; test regresyjny chroni materializację i liniowy rozmiar zapytania. Pomiar nie wykonuje SQL na bazie.
- Ruff check i format czterech zmienionych plików PASS; mypy --follow-imports=skip modułu SQL PASS. Mapa kodu zregenerowana, kontrola aktualności PASS. Cztery skrypty stanowiące npm run docs:check uruchomione bezpośrednio wspólnym interpreterem (worktree nie ma .venv): linki decyzji, okno stanu, budżet odczytu i kopie skilli PASS.
- Pierwszy przebieg nowych testów ujawnił błąd fixture (atrybut projekcji użyty na kandydacie domenowym). Poprawiono obliczanie znanych pozycji w fixture; docelowe 91 testów przeszło bez osłabienia asercji. Dwa wcześniejsze przebiegi 28 i 23 testów PASS przed rozszerzeniem pokrycia. Bez dodatkowego audytu: niewymagany dla tego taska.
- Odczyt głównego checkoutu po pracy: nadal codex/board-search-previous-photos, 1b10ebd1, te same dwa usunięte artefakty i worktrees/cloudflare-link-health. SHA256 głównego modułu SQL nadal ba73892587cd98d51e96268f89af13281ad820630f547d0851b28d214c53c8a9. Nie uruchamiano, nie zatrzymywano ani nie restartowano usług.
- Kryteria akceptacji i właściwe punkty Definition of Done sprawdzone; implementacja jest trwałym kodem w oddzielnym worktree. Nie jest wdrożona do działającej aplikacji.

### Not completed

- Bez wyszukiwania ani pomiaru czasu na pełnych danych operatora, benchmarku, buildów UI, restartów, wdrożenia, merge i push. Redukcja rozmiaru SQL nie jest dowodem czasu na całej bazie; odbiór operacyjny pozostaje osobnym krokiem.
- Wersja v1.7.490 wynika z historii tej gałęzi od main v1.7.489; koliduje numerem z odrębnym commitem TASK-1101, bez nadpisania historii ani reuse tego samego commita.

### Documentation updates

- API_CONTRACT opisuje materializację, późne pobieranie metadanych i lokalny cykl JIT bez zmiany OpenAPI. Task, CURRENT_STATE i mapa kodu uaktualnione.

### Recommended next task

- Akceptacja poprawki i osobna zgoda na integrację, następnie kontrolowany odbiór czasu rzeczywistego wyszukiwania w uzgodnionym momencie. Nie przerywać pracy operatora; TASK-1101 na osobnej gałęzi wymaga uwzględnienia podczas integracji.
