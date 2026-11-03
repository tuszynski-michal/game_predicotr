# TASK-1150 — Atomowy zapis postępu przy krótkiej blokadzie pliku Windows

## Status

`in_progress`

## Goal

Krótki odczyt progress.json przez nadzorcę nie przerywa treningu na Windows; trwała odmowa nadal kończy się błędem po ściśle ograniczonym ponowieniu, bez utraty poprzedniego JSON i odnowienia budżetu.

## Context

Rzeczywisty trening TASK-1147, run7a1b3835-639c-4439-8f49-3dfaea5e650a, zakończył się na kroku488: PermissionError WinError5 w write_json_atomic/os.replace pliku progress.json. Trace zapisany w artifacts/grid-training/runs/<run>/diagnostic-1.log. Nie jest to diagnoza braku pamięci GPU. Dotychczasowy atomowy zapis nie obsługuje chwilowego braku FILE_SHARE_DELETE u czytającego na Windows.

## Dependencies / entry conditions

Root/main5cfe292b, DB0178, przebieg cc7e739e-027c-4f44-87d8-8088c0d86bb1 i ta sama zamrożona kohorta. Zużycie dziecka: reserved488/8000, usedSeconds161,969/7200, attempt1, brak checkpointu. Dane te nie są resetowane. TASK-1149 niezależnie optymalizuje freeze w tym worktree; nie dotykać jego kodu/testów. Przed implementacją potwierdzić właściwą funkcję i konsumentów.

## Recommended execution

Wykonawca gpt-6.1-sol / high; Claude Code claude-opus-5-5 / high jako niezależny audytor przed commitem. Mała zmiana protokołu plikowego wymaga testu rzeczywistej blokady Windows i regresji nadzorcy. Eskalować konieczność zmiany budżetu, identyfikatorów, lease, formatu JSON lub szerokiego refaktoru.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/delivery/GRID_CORRECTION_GROWTH_PLAN_20261103.md — TASK-1147, TASK-1150
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/architecture/CODE_MAP.md
- ai_docs/quality/TASK-1147_VERIFICATION.md
- Lokalny trace: D:/game_predicotr/artifacts/grid-training/runs/7a1b3835-639c-4439-8f49-3dfaea5e650a/diagnostic-1.log oraz wynik result-1.json.

## Scope

Ograniczone ponowienie wyłącznie os.replace w write_json_atomic z images/grid_training_child.py. Używać tego samego gotowego/fsync temppliku, nigdy nie usuwać destination ani nie zapisywać go w miejscu. Ponawiać tylko jawne winerror5/32/33; inne błędy natychmiast propagować. Maksymalnie7 prób z opóźnieniami10/20/40/80/160/160ms, łącznie najwyżej0,47s oczekiwania. Po ostatniej odmowie propagować oryginalny błąd; zachować finally usuwające własny tempplik. Format, fsync, kanały diagnostyczne, result i rozliczenie budżetu pozostają.

## Out of scope

Bez zmiany uprawnień, antywirusa, limitów GPU, progów jakości, nowych treningów, lease i identyfikatorów. Bez cache, nowych zależności i wspólnej przebudowy wszystkich writerów. Wykonawca nie zmienia root/main, usług/bazy operatora ani TASK-1149.

## Acceptance criteria

- [ ] Zwykły zapis nadal atomowy, jedna próba bez oczekiwania.
- [ ] Przejściowa jawna blokada Windows jest ponawiana w podanym ścisłym limicie na tym samym temppliku.
- [ ] Trwała blokada kończy się błędem, pozostawia poprawny poprzedni destination i sprząta własny tempplik; inne błędy nie są maskowane.
- [ ] Test rzeczywistego uchwytu Windows bez FILE_SHARE_DELETE potwierdza zwolnienie blokady i pełny nowy JSON; testy deterministyczne sprawdzają liczbę prób, delay i brak zmiany budżetu/protokołu.
- [ ] Scoped worker tests, lint/mypy, docs/map i Opus rozliczone przed osobnym commitem/task-close.

## Expected files / Test cases

Istniejący images/grid_training_child.py — write_json_atomic i niezbędny prywatny helper. Proponowany services/worker/tests/test_grid_training_atomic_json.py lub pasujący istniejący test protokołu po odczycie mapy. Regressions: supervisor/child diagnostics, budget persistence, checkpoint restart i complete stderr. Nie uruchamiać sztucznego obciążenia ani rzeczywistego GPU w testach wykonawcy.

## Verification

Pytest zmienionego modułu i wskazanych konsumentów, komendy max120s, najpierw unit + ruff/mypy, potem regresje. Windows uchwyt zwalniany kontrolowanie w finally także gdy test zawiedzie. Testy są planowane, nie PASS przed ich wykonaniem. Prowadzący wznawia po wdrożeniu ten sam run/parent; budżet zachowany.

## Risks / open questions

WinError5 może oznaczać trwały ACL, dlatego retry jest krótkie i skończone; nie jest obietnicą naprawy uprawnień. Nie zmieniać errno-only POSIX EACCES w ponawianie. Wspólny writer ma konsumentów supervisor/child, wymagają regresji domyślnego zachowania.

## Outcome

W realizacji; bez kolejnego uruchomienia GPU do poprawki i audytu.
