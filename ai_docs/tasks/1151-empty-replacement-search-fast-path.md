---
title: Przywrócenie wyszukiwania bez historii wymiany zdjęć
status: in_progress
last_updated: 2026-11-03
---

# TASK-1151 — Przywrócenie wyszukiwania bez historii wymiany zdjęć

## Status

`in_progress`

## Goal

Wyszukiwanie777A2 i podgląd wyników odpowiadają na rzeczywistych danych, bez kosztownego zbioru wykluczeń przy pustej historii wymiany.

## Context

Regresja wprowadzona przez0175/0176: source_replacement_excluded_reviews_v1 wykonuje joiny dużego korpusu nawet bez historii. Pojedynczy readonly SELECT count funkcji777a2 przekroczył10s; retired=slots=entries=0 w0–0,016s. APIhealth200 nie dowodziło sprawnego wyszukiwania. UserGET15symboli pozostawał loading. Globalne166971zdjęć/1500019plansz/22248975pól i aktywacje identyczne sprzed wdrożenia;777a2 ma53262źródła,purged0. Bez usunięcia danych777A2.

## Dependencies / entry conditions

Startmain5cfe292b, baza178. Koordynator drugiego okna wstrzymał restart i dalsze obciążenie; jego1149/1150 zapisane,1151/179 zarezerwowane tutaj. Usługi i baza pozostają pod jego kontrolą do uzgodnionego wspólnego wdrożenia. Zgoda na pierwotne scalenie/push, migrację i restart pozostaje w sesji; to wąska naprawa regresji zatwierdzonego zakresu.

## Recommended execution

gpt-6-astra/high, wąska poprawka SQL i bramki startu. claude-opus-5-5/high przed commitem, jeden celowany przegląd. Bez nowego frameworka, benchmarku, skanowania zdjęć lub treningu.

## Relevant docs

- AGENTS.md; ai_docs/process/DEFINITION_OF_DONE.md.
- ai_docs/requirements/ADMIN_APP.md, Plan wymiany zdjęć.
- ai_docs/architecture/API_CONTRACT.md, read-only board-search.
- ai_docs/architecture/DATA_MODEL.md, current/exclusion guards TASK1128 i0176.
- ai_docs/quality/777A2_DEPLOYMENT_BLOCKER_20261103.md.
- .codex/skills/claude-audit/SKILL.md; .agents/skills/task-close/SKILL.md.

## Scope

Nowa Alembic0179 (parent178): dotychczasowa funkcja zmienia nazwę na source_replacement_excluded_reviews_impl_v1, nowy publiczny wrapper o poprzedniej nazwie jest STABLE SECURITY INVOKER z search_pathpg_catalog. Gdy dla g nie ma retired, żadnychslots ani restoredentries, zwraca pustySET bez wywołania implementacji. W przeciwnym razie deleguje bez zmian do starej funkcji. Dotyczy także rawSQL supergame, zakresu, szczegółów i list. Nie usuwa guardów. Downgrade usuwa wrapper i przywraca nazwę oryginału; zachowuje jego OID/ACL i całą historię. Pin head179 i odmowa178. Bez mutacji tabel, API/UI i manifestu21.

## Acceptance criteria

- [x] OwnedPG dowodzi niewykonania kosztownej implementacji przy pustej historii, także rola runtime.
- [x] Dotychczasowe retired/reserved/closed guards zachowane w PG; downgrade/upgrade roundtrip.
- [x] Testy head/lint/types/docs/map i Opus bez P0/P1.
- [ ] Odbiór operatora na dokładnym wzorze15symboli z jego logu: HTTP200 z wynikami, czas zmierzony, podgląd/range sprawdzony; dane bez zmian.

## Expected files

Nowa migracja0179 i test PG; schema_readiness i jego test; DATA_MODEL krótka nota, task/CURRENT_STATE/map/raport. Brak zmian kontraktu API lub zależności.

## Verification

RootPython z PYTHONPATH wskazującym tenWT dlaapi/worker i tests; subprocess timeout120s. OwnedPG opt-in GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 i istniejący fixture test_source_replacement_postgres.database. Schema tests, nowy PGtest, istniejący guardsPG. Opus480s/zewnętrzny600s. LiveHTTP readonly po migracji przez właściciela okna, pojedyncze żądanie z limitem75s. Nie uznawać samego health za odbiór.

## Risks / open questions

Fast path dotyczy dowiedzionej pustej historii tej gry. Nie prognozuje wydajności pełnego zbioru po rzeczywistej wymianie; dotychczasowe fences pozostają. Testy nie mają dodawać danych do bazy operatora. Restart jest konieczny również dla starych preparedplans odnoszących się doOID przemianowanej funkcji.

## Outcome

### Changed

Migracja0179 i dokładny pin startu. Stara funkcja zachowuje niezmienione ciało/OID/ACL jako impl; wrapper pomija ją wyłącznie przy dowiedzionym braku trzech źródeł fences dla danej gry. Brak nowego API, mutacji tabel lub wyłączenia walidacji. Mapa kodu regenerowana; krótka nota DATA_MODEL.

### Verification results

- Readonly incydent: retired=0/slots=0/entries=0 w0–0,016s; SELECT count starejfunkcji przekroczył statement_timeout10s. Dowody artifacts/deploy-777a2-20261103/search-incident-diagnosis.json i database-search-incident.json; globalne counts i aktywacje nie zmieniły się od wdrożenia.
- RootPython z PYTHONPATH na tenWT(api/worker/tests), GAME_PREDICTOR_RUN_POSTGRES_TESTS=1, subprocess120s: test_schema_readiness.py + test_empty_replacement_search_postgres.py + test_source_replacement_guards_postgres.py:29PASS49,91s. Własne tymczasowe bazy, nie baza operatora. Nowy test zastępuje impl funkcją rzucającą wyjątek: owner i runtime nadal dostają0, dowodząc niewykonania dużychjoinów. Rollback odtwarza funkcję. Roundtrip179→178→179 potwierdza identyczną definicję starejimplementacji. Istniejące guardy obejmują retired, reservedalias oraz planned/gap_open/restored.
- Ruff check dla4zmienionychPythonów PASS po zawinięciu3literalnychSQLstrings (pierwsza kontrola E501). Mypy produkcyjnego schema_readiness PASS; generate_code_map PASS. Zawinięcie SQL nie zmienia zapytań; bez ponowienia pełnych PG.
- Opus5.5/high R1: PASS, bez P0/P1, raport quality/TASK-1151_AUDIT_claude-opus-5-5.md. P2-1 przyjęto jawnie: nie ma osobnego testu każdego z3niepustychźródeł w izolacji; poprawność wszystkich trzechwarunków i ich równoważność potwierdził niezależny audyt kodu0176/0179, a istniejący PGguard obejmuje niepustąhistorię. Nie zmieniamy tejsemantyki. P2-2 przyjęto: test roundtrip porównuje ciało, OID/ACL zachowuje ALTERFUNCTIONRENAME z natury PostgreSQL; nie ma destrukcyjnego odtwarzaniaimpl. P2-3 domknie realnyHTTP z wynikami po179 na roli produkcyjnej. TeP2 nie blokują pilnej naprawy; nie deklarujemy nieistniejącego pokrycia testowego.
- Cztery docscheckery PASS po skróceniu3historycznychpunktów z zachowaniem pełnych tekstów w archiwumQ4; startup44702B. Pierwsza kontrola miała45325B i została poprawiona. GitdiffcheckPASS. Realny odbiór jeszcze przed done; nie raportujemy samego startu usług jako naprawy.

### Not completed

Brak operacji na zdjęciach, skanu, pilota, aktywacji i treningu. Nie deklarujemy czasu dużejhistorii wymiany; zachowuje dotychczasową implementację. LiveHTTP kryterium musi być potwierdzone po migracji, przed done. Właściciel okna zdrugiegochatu wykona wspólny stop/merge/migrate/start po audycie tejpoprawki, potem domknięcie1151.

### Documentation updates

Task/CURRENT_STATE, DATA_MODEL i generowana mapa. Po odbiorze wpisać dokładny czas/wyniki userGET i brak usunięcia danych, następnie task-close/commit/hash.

### Recommended next task

Najpierw odbiór wyszukiwarki777A2 na wzorze użytkownika. Dopiero potem wznowienie pozostałego odbioru drugiegookna.
