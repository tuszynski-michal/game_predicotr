# TASK-1150 — Atomowy zapis postępu przy krótkiej blokadzie pliku Windows

## Status

`done`

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

- [x] Zwykły zapis nadal atomowy, jedna próba bez oczekiwania.
- [x] Przejściowa jawna blokada Windows jest ponawiana w podanym ścisłym limicie na tym samym temppliku.
- [x] Trwała blokada kończy się błędem, pozostawia poprawny poprzedni destination i sprząta własny tempplik; inne błędy nie są maskowane.
- [x] Test rzeczywistego uchwytu Windows bez FILE_SHARE_DELETE potwierdza zwolnienie blokady i pełny nowy JSON; testy deterministyczne sprawdzają liczbę prób, delay i brak zmiany budżetu/protokołu.
- [x] Scoped worker tests, lint/mypy, docs/map i Opus rozliczone przed osobnym commitem/task-close.

## Expected files / Test cases

- `services/worker/src/game_predictor_worker/images/grid_training_child.py` — istniejący `write_json_atomic` i prywatna stała opóźnień, bez wspólnego refaktoru writerów.
- Nowy `services/worker/tests/test_grid_training_atomic_json.py` — zwykły zapis, przejściowe i trwałe winerror5/32/33, obce kody/errno-only EACCES oraz rzeczywisty uchwyt Windows.
- Odczytani konsumenci: `images/grid_training_handler.py` używa writera dla spec i allowance oraz czyta progress; dziecko używa go także dla result i diagnostyki eksportu. Ich kod nie został zmieniony.
- Regresje bez zmian plików: `test_grid_training_handler.py`, `test_grid_training_child_diagnostics.py`, `test_grid_training_child.py` bez testu realnego trenowania i eksportu. Obejmują supervisor/child diagnostics, budget persistence, checkpoint restart i complete stderr.

## Verification

Pytest zmienionego modułu i wskazanych konsumentów, każde polecenie uruchomione przez `subprocess.run(timeout=120)`, najpierw unit + ruff/mypy, potem regresje. Jawny PYTHONPATH obejmuje `services/worker/src`, `services/api/src`, `services/test_support` tego worktree. Pytest używa nowego krótkiego katalogu `--basetemp=.t/<id>`; przed uruchomieniem sprawdzana jest jego rozstrzygnięta ścieżka wewnątrz `.t` i brak wcześniejszej zawartości.

```powershell
.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.t/<nowy-id> services/worker/tests/test_grid_training_atomic_json.py
.venv/Scripts/python.exe -m ruff check services/worker/src/game_predictor_worker/images/grid_training_child.py services/worker/tests/test_grid_training_atomic_json.py
.venv/Scripts/python.exe -m ruff format --check services/worker/src/game_predictor_worker/images/grid_training_child.py services/worker/tests/test_grid_training_atomic_json.py
.venv/Scripts/python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/images/grid_training_child.py
.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.t/<inny-nowy-id> services/worker/tests/test_grid_training_handler.py services/worker/tests/test_grid_training_child_diagnostics.py services/worker/tests/test_grid_training_child.py -k "not test_real_trainer_trains_checkpoints_exports_and_releases_the_gpu_lease"
```

Windows uchwyt jest zwalniany kontrolowanie po pierwszej rzeczywistej odmowie os.replace i chroniony finally także przy błędzie testu. Wyniki wykonania są w Outcome oraz `ai_docs/quality/TASK-1150_VERIFICATION.md`. Prowadzący wznawia po wdrożeniu ten sam run/parent; budżet zachowany.

## Risks / open questions

WinError5 może oznaczać trwały ACL, dlatego retry jest krótkie i skończone; nie jest obietnicą naprawy uprawnień. Nie zmieniać errno-only POSIX EACCES w ponawianie. Wspólny writer ma konsumentów supervisor/child, wymagają regresji domyślnego zachowania.

## Outcome

Commit: v1.7.547 (hash dopisuje kolejny commit).

### Changed

- `write_json_atomic` zachowuje dotychczasowy pojedynczy zapis, flush i fsync własnego temppliku. Wyłącznie jego atomowe `os.replace` ponawia jawne winerror5/32/33, maksymalnie7 razy z opóźnieniami10/20/40/80/160/160ms. Wspólny limit oczekiwania wynosi0,47s; sukces kończy pętlę natychmiast.
- Wszystkie próby używają tego samego kompletnego temppliku. Nie usuwamy ani nie zapisujemy destination w miejscu. Po trwałej odmowie propagowany jest błąd, poprzedni JSON pozostaje niezmieniony, a finally usuwa własny tempplik. Errno-only EACCES i pozostałe kody nie są ponawiane.
- Dodano12 testów, w tym faktyczne CreateFileW z FILE_SHARE_READ/FILE_SHARE_WRITE bez FILE_SHARE_DELETE, realną odmowę atomowej podmiany i kontrolowane zamknięcie uchwytu przed kolejną próbą.
- Audyt Opus R1 PASS bez P0/P1. W jedynej rundzie P2-1 callback testu zamyka natywny uchwyt wyłącznie gdy `not released`; dodatkowa odmowa nie grozi podwójnym CloseHandle. Zachowano asercje liczby odmów i dokładnych delay. Opcjonalnego dodatkowego testu bajtów serializacji nie dodawano.
- Nie zmieniono budżetu, formatu/spec/result/progress, lease, checkpointów ani kodu nadzorcy. Nie dotykano plików TASK-1149, usług, bazy, root/main ani operacyjnego przebiegu.

### Verification results

- Nowe testy atomowego JSON po P2-1:12 PASS,1,31s; rzeczywisty Windows test wykonany, bez skip. Log `artifacts/task1150-unit-p2.log`; wcześniejszy wynik12 PASS,1,29s w `task1150-unit.log`.
- Regresje konsumentów:34 PASS /1 deselected,21,62s. Wyłączono wyłącznie test realnego trenowania/eksportu. Log `artifacts/task1150-consumers-short-path.log`.
- Scoped Ruff check PASS; scoped mypy produkcyjnego modułu PASS,1 source file. Po P2-1 ponowiono Ruff check i format --check wyłącznie testu: PASS. Wynik12 PASS dotyczy końcowych bajtów testu; produkcja i jej hash bez zmian, zatem wynik34 PASS /1 deselected nadal aktualny, bez ponawiania. Końcowe hashe zapisano w `artifacts/task1150-frozen-sha256.txt`.
- Pierwsze próby setupu pytest nie uruchomiły testów z powodu domyślnego katalogu tymczasowego i brakującego katalogu nadrzędnego. Pierwszy przebieg konsumentów miał20 błędów długich ścieżek Windows,14 PASS. Ten sam kod i zestaw testów przeszedł z krótkim świeżym basetemp w worktree; nie zmieniano testów dla zielonego wyniku. Szczegóły w raporcie.

### Not completed

- Audyt Opus PASS, P2-1 rozliczone w jednej rundzie. Ostateczna regeneracja/kontrola mapy, docs:check, osobny commit i task-close pozostają prowadzącemu.
- Nie wykonano kolejnego treningu GPU, wznowienia ani wdrożenia poprawki. Dopiero prowadzący może wznowić ten sam run/parent z zachowanym budżetem.
- Trace dowodzi operacyjnej odmowy dostępu; test reprodukuje krótką blokadę sharing. Nie ustala to właściciela rzeczywistego uchwytu ani nie dowodzi, że błąd ACL zniknął. Trwałe odmowy nadal są błędami.

### Documentation updates

- Ten task i `ai_docs/quality/TASK-1150_VERIFICATION.md`; lista audytu `artifacts/task1150-audit-paths.txt`.
- Plan, CURRENT_STATE i dokumentację odbioru prowadzi root; wykonawca nie zmieniał ich przy tym zadaniu.

### Recommended next task

- Osobny commit TASK-1150 po bramkach dokumentacji/mapy, następnie wdrożenie i wznowienie zachowanego przebiegu przez prowadzącego.

### Lead acceptance

Opus5.5/high R1 PASS bez P0/P1. P2-1 zamknięte jednokrotnym CloseHandle w teście i ponowieniem12unit; produkcja nie zmieniła się po audycie. Opcjonalny test bajtowy odłożony: sama serializacja jest bez zmian w diffie, format i konsumenci mają regresje. Root domyka mapę/docs i osobny commit. Nie jest to dowód zakończenia uczenia; rollout i wznowienie istniejącego budżetu należą do1147.
