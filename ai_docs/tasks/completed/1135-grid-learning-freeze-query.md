---
title: Bounded cohort freeze row selection
status: done
last_updated: 2026-11-03
---

# TASK-1135 — Naprawa timeoutu zamrażania korekt siatek

## Status

`done`

## Goal

Usunąć potwierdzony timeout selekcji wierszy podczas freeze, zachowując dokładny zakres blokad, ich kolejność, izolację gier i istniejące limity czasu.

## Context

Operator zlecił naprawę nieudanego uczenia oraz audyt Opus. Przebieg `ecdb88d5-3808-4069-bd64-e122d52cfa62` zatrzymał się z `JOB_EXECUTION_FAILED` / `OperationalError` na kohorcie `ready_to_freeze` (rewizja 163), przed utworzeniem treningu. Log PostgreSQL z 2026-11-02 22:36:48 UTC potwierdza statement timeout przy FETCH. Kohorta ma 788 źródeł, w tym 86 użytych, oraz 158 stron materializacji.

Ograniczona reprodukcja READ ONLY na tych danych: stary wybór komórek przekracza 3 s (SQLSTATE 57014), wariant z uprzednim rozwinięciem identyfikatorów zwraca 11610 unikalnych komórek w 0,343 s. Artefakty: `artifacts/task1135-postgres-failure.log`, `artifacts/task1135-readonly-reproduction.json`, `artifacts/task1135-plan-*.json`.

## Dependencies / entry conditions

- Baza `main` / v1.7.526 / a31e8adbc026f1bc17c7ffee97499d0b6f856157.
- Brak zmian śledzonych przed taskiem; trzy cudze worktrees pozostają nietknięte.
- Użytkownik zatwierdził implementację naprawy i audyty oraz przekazanie niezbędnego kodu do Anthropic. Bez delegowania.

## Recommended execution

gpt-6.1-sol / high: ograniczona zmiana SQL i integracyjne testy blokad. Niezależny Claude Code claude-opus-5-5 / high przed commitem. Zmiana semantyki ochrony danych lub konieczność migracji wymaga ponownej oceny zakresu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — uczenie siatek z korekt.
- `ai_docs/architecture/VISION_LAB.md` — correction learning pipeline i freeze.
- `ai_docs/architecture/CODE_MAP.md`, `ai_docs/architecture/CODE_MAP_SYMBOLS.md`.

## Scope

- W `_lock_inputs` wybrać unikalne identyfikatory z tablic użytych członków kohorty przed połączeniem z tabelami plansz, review i komórek.
- Zachować filtry gry/kohorty/used, deduplikację, sortowanie po UUID i `FOR UPDATE OF r` oraz wszystkie pozostałe blokady freeze.
- Test PostgreSQL zakresu, duplikatów i rzeczywistych blokad; regresja istniejącego freeze i aktualności danych.
- Ograniczony odczyt na zapisanej kohorcie po zmianie oraz audyt Opus.

## Out of scope

Zwiększanie timeoutów, migracje, zmiana danych operatora, restart usług, merge/push, faktyczny trening i aktywacja modelu. Zgłoszone wcześniej odświeżanie panelu pozostaje osobnym zagadnieniem; w tym tasku nie zmieniamy UI ani API.

## Acceptance criteria

- [x] Potwierdzony błąd ma reprodukcję na istniejących danych.
- [x] Nowy wybór obejmuje dokładnie te same wiersze użytych członków, bez wycieku między grami/kohortami i bez duplikatów.
- [x] PostgreSQL potwierdza blokady wybranych wierszy oraz brak blokady niepowiązanych wierszy; blokady znikają po zakończeniu transakcji.
- [x] Limity czasu i kolejność blokad pozostają bez zmian; stare polityki kohort przechodzą regresję.
- [x] Testy zmienionego pionu, scoped lint/typecheck, docs/map i audyt Opus rozliczone.
- [x] Outcome, task-close, osobny wersjonowany commit i record-hash.

## Technical notes

Obecny skorelowany warunek `m.cell_ids @> ARRAY[r.id]` prowadzi do nested loop po całej tabeli komórek. Zalecana zmiana: podzapytanie `SELECT DISTINCT unnest(m.<ids>) AS id` z istniejącymi filtrami członkostwa, JOIN po id i istniejący filtr gry na tabeli celu. Sortować końcowy wynik przed blokadą. Nazwy tabel i kolumn pochodzą wyłącznie z zamkniętej, istniejącej listy w kodzie. Nie materializować globalnego zbioru w Pythonie i nie omijać RLS.

## Expected files

- `services/api/src/game_predictor_api/application/grid_training_cohort_freeze.py` — `_lock_inputs`.
- Nowy `services/api/tests/integration/test_grid_cohort_freeze_selection_postgres.py`.
- `ai_docs/architecture/VISION_LAB.md`, regenerowana mapa kodu, niniejszy task i dokumenty zamknięcia.

## Test cases

- Użyte i nieużyte źródła, nakładające się tablice identyfikatorów, obca kohorta i gra → tylko właściwe wiersze, każdy raz.
- Druga transakcja nie może zablokować wybranego wiersza NOWAIT, lecz może zablokować wiersz poza zakresem. Po rollbacku pierwszej może zablokować oba.
- Istniejący mały przepływ przygotowania/materializacji/freeze działa bez mockowania `_lock_inputs`.
- Stare i nowe zapytanie na istniejących danych, READ ONLY i limit 3 s; bez syntetycznego obciążenia.

## Verification

Komendy ustalić z istniejącego harnessu integracyjnego; wywołania mają timeout ≤ 120 s i krótki `--basetemp` w artifacts. Wyłącznie jednorazowe disposable PostgreSQL. Testy planowane nie są jeszcze wynikami.

## Risks / open questions

Odczyt porównawczy nie dowodzi ukończenia GPU treningu. Aktualne nieudane zadanie operatora nie jest automatycznie wznawiane. Zapisane role, geometria i przypisania pozostają zachowane.

## Outcome

Commit: v1.7.527 / `c0a16b6abc42704572ac0dc17329e548f8c77061`.

### Changed

- `_lock_inputs` rozwija i deduplikuje tablice członków kohorty przed JOIN do trzech tabel. Zachowane game/cohort/used, sortowanie UUID, `FOR UPDATE OF r`, pozostałe blokady oraz limity 30/60 s.
- Nowy test na ograniczonej roli PostgreSQL: dokładny zbiór i kolejność, duplikaty, nieużyty członek, obca kohorta i identyfikatory obcej gry, rzeczywiste NOWAIT oraz zwolnienie blokad po rollbacku. Fixture używa polityki korekt; nie deklaruje kwalifikacji etykiet.

### Verification results

- Odczyt logu serwera i READ ONLY reprodukcja: stary wybór przekracza 3 s / SQLSTATE 57014; nowy zwraca 11610 unikalnych komórek w 0,343 s, bez blokad i zapisów operatora (`artifacts/task1135-readonly-reproduction.json`).
- `test_grid_cohort_freeze_selection_postgres.py`: PASS 1 / 33,54 s na nowej bazie PostgreSQL (`artifacts/task1135-postgres-selection-final.log`). Wcześniejszy wariant fixture legacy również PASS 1 / 38,09 s. Trzy wcześniejsze próby korygowały wyłącznie fixture: jawny intent, brak kolumny import_job_id na planszy i wymagania stanu kohorty. Ograniczeń bazy nie wyłączano.
- Pełny `test_grid_training_cohort_e2e_postgres.py`: PASS 1 / 102,25 s. Przygotowanie, materializacja, rzeczywisty freeze (8,58 s), utracona odpowiedź/replay, aktualność, nowy interpreter z datasetem TRAIN/VALIDATION/REGRESSION i dokładnymi 120 etykietami oraz odrzucenie cofniętej etykiety. CPU-only, bez trenera GPU (`artifacts/task1135-e2e.log`).
- Cztery pliki domeny/storage/workflow: 77 PASS, 1 istniejący błąd starego testu `test_shared_candidate_rejects_correction_policy_before_creating_plan`. Test oczekuje odrzucenia polityki korekt, podczas gdy TASK-1121 dopuścił ją z weryfikacją historii; fixture ma `session_factory=None`. Oba pliki są identyczne z main a31e8adb, wyjątek występuje przed freeze. Poza zakresem tej poprawki, testu nie osłabiano (`artifacts/task1135-unit-final.log`, `artifacts/task1135-preexisting-contract-failure.json`).
- Dwie próby testów HTTP w ograniczonym środowisku zatrzymały się przy socketpair/asyncio; stack zapisano i potwierdzono brak osieroconych procesów. Ostateczna próba bez tego ograniczenia zakończyła się opisanym powyżej wynikiem.
- Ruff format/check PASS. Scoped mypy zmienionego modułu PASS: pełny config projektu z wyłącznie torch/torch.* follow_imports=skip i CLI --follow-imports=silent; globalnej konfiguracji nie zmieniono. Nie jest to pełny projektowy mypy.
- `docs:check`, `code-map:check`, regeneracja mapy i `git diff --check` PASS.
- [Audyt Opus 5.5/high](../../quality/TASK-1135_AUDIT_claude-opus-5-5.md): PASS, runda 1, 164,80 s, bez P0/P1.
- P2-1 zaakceptowane ograniczenie: testy automatyczne chronią semantykę i blokady, nie plan wykonania. Nie dodano strażnika kopiującego implementację SQL ani zależnego od konkretnego planera. Reprodukcja wydajności pozostaje ograniczonym testem na istniejących danych, bez syntetycznego obciążenia. W razie zmiany selekcji ponowić ten odczyt z jawnym budżetem.
- P2-2 poprawione: `artifacts/task1135-final-query-evidence.json` zawiera dokładny SQL pobrany z AST końcowej funkcji, wariant READ ONLY bez FOR UPDATE, jego SHA-256, parametry i EXPLAIN dla trzech tabel. Powtórzony ograniczony odczyt: 114 plansz / 0,296 s; 114 review / 0,063 s; 11610 komórek / 0,141 s (łącznie z EXPLAIN). Nie jest to pomiar blokad ani pełnego freeze; te pokrywa osobny test PostgreSQL/e2e. Ciepły cache i inne czasy nie stanowią benchmarku porównawczego.

### Not completed

- Nie wznawiano zadania operatora, nie uruchamiano GPU treningu, nie publikowano/aktywowano modelu. Nie zmieniano geometrii ani domyślnej wersji. Brak restartu usług i migracji. Merge/push po akceptacji wyniku.
- Zgłoszony wcześniej stan odświeżania panelu pozostaje osobnym zagadnieniem; ten task usuwa potwierdzoną awarię backendu.

### Documentation updates

- VISION_LAB opisuje selekcję identyfikatorów przed blokowaniem. Mapa kodu zregenerowana. Dowody lokalnych odczytów i komend są w artifacts/task1135-*.

### Recommended next task

Po akceptacji: scalenie/push, restart general workera i jawne wznowienie istniejącego zadania zamiast tworzenia nowej próby; następnie rzeczywista ocena kandydata i porównanie plansz do korekty. Przejście zamrażania nie dowodzi powodzenia późniejszego treningu.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1135 — timeout freeze | gpt-6.1-sol | high | Selekcja i rzeczywiste blokady PostgreSQL | Obowiązkowy: Claude Code claude-opus-5-5 / high, przed commitem |
