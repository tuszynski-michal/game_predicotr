---
title: Zgodność kontroli startu z migracją wymiany zdjęć
status: done
last_updated: 2026-11-03
---

# TASK-1146 — Zgodność kontroli startu z migracją wymiany zdjęć

## Status

`done`

## Goal

API i worker przyjmują dokładnie rzeczywistą głowę Alembic0177 i odmawiają startu na starszej bazie.

## Context

Podczas zatwierdzonego wdrożenia wykryto EXPECTED_ALEMBIC_HEAD=0174_source_replacement, choć ukończony łańcuch zawiera0175–0177. Wdrożenie z bazą0177 nie wystartowałoby. Operator zatwierdził scalenie, stop/start usług, migrację0171→0177, push i dodatkowy zakres/koszt. Naprawa jest konieczną, wąską korektą zgodności przed tym wdrożeniem.

## Dependencies / entry conditions

Gałąź codex/777a2-readability-replacement, start87f0870e. Nowy numer1146 po sprawdzeniu rezerwacji:1139/1140 growth,1141 purge,1142–1144 selector,1145 numer migracji growth. Bez zmiany cudzej migracji0178. Główna baza nadal0171; usług jeszcze nie zatrzymano.

## Recommended execution

gpt-6-astra / high, ograniczona naprawa stałej i testów zgodności. Niezależny claude-opus-5-5 / high przed commitem, krótki brief i najwyżej6celowanych odczytów. Bez nowej pętli audytów lub rozbudowy funkcji.

## Relevant docs

- AGENTS.md; ai_docs/process/DEFINITION_OF_DONE.md.
- ai_docs/delivery/777A2_PHYSICAL_SOURCE_PURGE_PLAN_20261103.md.
- ai_docs/architecture/DATA_MODEL.md i API_CONTRACT.md, sekcje wymiany źródeł.
- .agents/skills/merge-to-main/SKILL.md.
- ai_docs/tasks/completed/1141-source-replacement-physical-purge.md.

## Scope

storage/schema_readiness.py:EXPECTED_ALEMBIC_HEAD i właściwy opis; test_schema_readiness.py oraz wąski test faktycznej głowy Alembic. Błąd ma nadal działać fail-closed dla innych rewizji. Dokumentacja/Outcome, task-close i osobny commit/hash.

## Out of scope

Zmiany migracji, obchodzenie kontroli schematu, zmiana API, usług lub danych w tym podzadaniu. Całe wdrożenie prowadzi root po tej poprawce.

## Acceptance criteria

- [x] Jedyna głowa Alembic i EXPECTED_ALEMBIC_HEAD są równe0177_source_replacement_purge.
- [x] Testy przyjmują właściwy head i odmawiają starego/innego head.
- [x] Celowane testy/lint/typy/docs/map sprawdzone; Opus5.5 bez P0/P1; task-close/commit/hash.

## Expected files

Istniejące: services/api/src/game_predictor_api/storage/schema_readiness.py; services/api/tests/test_schema_readiness.py; właściwe dokumenty procesu. Bez innych plików produktu.

## Verification

RootPython D:/game_predicotr/.venv/Scripts/python.exe. Dokładne komendy wykonawca zapisze w Outcome; każdy subprocess timeout120s, audyt maks480s. Testy bez bazy operatora i bez usług.

## Risks / open questions

Nie akceptować zestawu starszych rewizji jako obejścia. Stała ma przypinać dokładny lokalny head, tak jak dotychczasowy kontrakt. Brak nowych decyzji domenowych.

## Outcome

Commit: v1.7.540 (hash dopisuje kolejny commit).

### Changed

Stała i opis bramki startowej wskazują `0177_source_replacement_purge`. Istniejący test `ScriptDirectory.get_heads()` zachowano i zaktualizowano oczekiwaną rewizję; odmowa obejmuje również każdą rewizję0171–0176. Reguła pojedynczej, dokładnie zgodnej głowy pozostaje bez zmian. Brak nowych decyzji, migracji lub zmian API.

### Verification results

Wszystkie polecenia z katalogu worktree, Python `D:/game_predicotr/.venv/Scripts/python.exe`, subprocess timeout120s.

- Przed poprawką pojedynczy `test_expected_head_is_the_single_alembic_head`: FAIL, rzeczywisty head0177 kontra pin0174; potwierdzony błąd.
- `-m pytest services/api/tests/test_schema_readiness.py -q --tb=short --basetemp=D:/game_predicotr/artifacts/t1146-green`: **23 PASS /2,88s**, nowy proces, bez połączenia do bazy.
- `-m ruff check` i `-m ruff format --check` dla obu zmienionych plików Python: PASS.
- `-m mypy --follow-imports=silent services/api/src/game_predictor_api/storage/schema_readiness.py`: PASS. Kontrola obu plików wykazała trzy zastane błędy typów `down_revision` w niezmienionych testach merge (linie25/47/48); odczyt wersji testu z HEAD do ignorowanego artifacts i ponowny mypy potwierdził te same trzy błędy. Kopia starego testu dodatkowo zgłasza oczekiwany konflikt literal0174 z poprawionym modułem0177. Nie zmieniano tych testów ani ustawień typowania; pełnej zieleni mypy testów nie deklarujemy.
- Cztery skrypty `check_decision_links.py`, `check_current_state_window.py`, `check_startup_read_budget.py`, `check_skill_mirrors.py`: PASS. `generate_code_map.py` i `--check`: PASS, wygenerowana mapa bez różnic.
- [Niezależny audyt Opus5.5/high](../../quality/TASK-1146_AUDIT_claude-opus-5-5.md): **PASS**, actual `modelUsage=[claude-opus-5-5]`,6 odczytów, bez P0/P1/P2. O1 zamyka task-close; O2 kosmetyka istniejącego zawinięcia komentarza bez zmiany. Manifest v21 pozostaje zgodny z dokumentacją TASK-1141 (0177 nie zmienia wersji manifestu). Nie powtarzano zielonych testów bez nowej zmiany; start usług po migracji należy do wdrożenia koordynatora.
- DoD: zgodność rzeczywistej głowy i sukces guardu pokrywają testy head/accept; fail-closed starych/obcych rewizji pokrywa19 przypadków odmowy. Zakres kodu ograniczony do dwóch wskazanych plików; brak zmian domeny/API/schematu. Kontrole, dokumentacja i niezależny audyt zakończone.

### Not completed

Bez szerokich testów/buildów, usług, migracji, danych operatora, merge i push. Wdrożenie prowadzi koordynator po zamknięciu tej poprawki.

### Documentation updates

Opis modułu, task/Outcome, aktywny wskaźnik CURRENT_STATE i regeneracja mapy kodu. Brak zmiany kontraktu danych/API; architektura pozostaje zgodna z migracją0177.

### Recommended next task

Koordynator może kontynuować zatwierdzone wdrożenie po zielonym audycie i commicie; przyszła migracja0178 wymaga własnej aktualizacji pinu i tego samego testu.


## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1146 — Kontrola schematu przy starcie | gpt-6-astra | high | Konieczna zgodność startu z już audytowaną migracją; bez zmian schematu. | claude-opus-5-5 / high, krótki przegląd przed commitem |
