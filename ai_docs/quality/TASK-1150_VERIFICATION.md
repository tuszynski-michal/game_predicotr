# TASK-1150 — Atomowy postęp Windows: weryfikacja

Data:2026-11-03. Worktree `D:/game_predicotr/worktrees/grid-correction-growth`,
branch `codex/grid-correction-growth`. Wykonawca: `gpt-6.1-sol` / `high`.

## Diagnoza i granice

Odczyt lokalnego `diagnostic-1.log` przebiegu
`7a1b3835-639c-4439-8f49-3dfaea5e650a` wskazuje `PermissionError [WinError 5]`
w `images/grid_training_child.py:write_json_atomic` przy
`os.replace(temp, progress.json)`. `result-1.json` ma
`GRID_TRAINING_UNEXPECTED_ERROR`, `failed`, `steps=488`, attempt1.
Nie jest to dowód awarii pamięci GPU ani podstawa do odnowienia budżetu.
Odczyt nie ustala właściciela blokady lub trwałej polityki ACL.

## Zmiana

Jedyna zmiana produkcyjna mieści się w istniejącym writerze i prywatnej stałej:
gotowy, kompletny i fsyncowany tempplik podlega najwyżej7 próbom `os.replace`.
Wyłącznie jawne `winerror`5/32/33 dopuszczają kolejną próbę. Opóźnienia to
10/20/40/80/160/160ms, łącznie470ms. Inne błędy są propagowane od razu,
a trwała odmowa po siódmej próbie. Nigdy nie usuwamy destination ani nie
zapisujemy go w miejscu. Dotychczasowe finally sprząta wyłącznie własny tempplik.

Nie zmieniono formatu spec/progress/result, liczników kroków, budżetu,
identyfikatorów, lease, checkpointów ani kodu nadzorcy. Writer nadal obsługuje
jego istniejących konsumentów: zapis spec/allowance w handlerze oraz
progress/result/artefakty dziecka. Nie powstał refaktor wspólnych writerów.

## Testy

| Kontrola | Wynik |
|---|---|
| Nowy test atomowego JSON po P2-1 | 12 PASS,1,31s, w tym rzeczywisty uchwyt Windows bez skip |
| Handler + diagnostyka dziecka + child z wyłączeniem realnego trenowania/eksportu | 34 PASS /1 deselected,21,62s |
| Ruff check zmienionego modułu i nowego testu | PASS |
| Scoped mypy z follow-imports=skip, produkcyjny moduł | PASS,1 source file |
| Końcowy Ruff format --check i diff --check | PASS,2 pliki już sformatowane; brak dalszych zmian kodu |

Nowe testy sprawdzają:

- zwykły sukces: dokładnie jeden fsync przed jedną podmianą, zero sleep;
- przejściowe błędy5/32/33: jeden tempplik, pełny nowy JSON przy każdej próbie,
  nienaruszony stary destination do chwili sukcesu;
- trwałe błędy5/32/33: dokładnie7 prób, sześć określonych delay, propagację tej
  samej odmowy, stare bajty JSON oraz usunięcie tylko własnego temppliku;
- errno-only EACCES oraz obce winerror2/80/87: jedna próba, zero sleep,
  zachowany destination i sprzątnięty tempplik;
- rzeczywisty Windows `CreateFileW` z prawem odczytu i sharing READ/WRITE,
  bez FILE_SHARE_DELETE. Pierwsze rzeczywiste `os.replace` zwraca błąd sharing,
  uchwyt zostaje zamknięty w kontrolowanym backoff, kolejna podmiana zapisuje
  pełny nowy JSON. Finally zamyka uchwyt także przy porażce testu.

Regresje konsumentów pokrywają durable result przed zwolnieniem lease,
osobne diagnostyki prób, JSON-only probe, pełną linię stderr w nowym procesie,
watchdog, rezerwacje kroków, budżet zachowany po resume/reclaim, odzyskanie
checkpointu i eksportu oraz zatrzymanie starego dziecka. Handler używa fake
child. Wyłączono jedynie `test_real_trainer_trains_checkpoints_exports_and_releases_the_gpu_lease`.
Nie uruchomiono rzeczywistego GPU ani kolejnego operacyjnego runu.

## Sposób uruchomienia i problemy środowiska

Każde polecenie miało `subprocess.run(timeout=120)` i jawny PYTHONPATH do
`services/worker/src`, `services/api/src`, `services/test_support` worktree.
Interpreter: lokalna `.venv/Scripts/python.exe` (współdzielone środowisko,
źródła przypięte przez PYTHONPATH do worktree).

Pierwszy setup pytest nie mógł utworzyć numerowanego katalogu w domyślnym Temp;
drugi wskazał basetemp z nieistniejącym rodzicem. Były to wyłącznie błędy
fixture setup, bez wykonania testowanego writera. Nowy test przeszedł po
utworzeniu własnego rodzica i wskazaniu nowego katalogu w worktree.

Pierwszy przebieg konsumentów z długim `.test-tmp/task1150-consumers-<uuid>`
miał20 błędów ścieżek checkpointów Windows,14 PASS i1 deselected. Nie zmieniano
kodu ani testów. Ten sam zestaw przeszedł z nowym krótkim `.t/<4 znaki>`;
reprezentatywna najdłuższa ścieżka fixture ma226 znaków. Przed uruchomieniem
sprawdzono rozstrzygniętą ścieżkę wewnątrz przeznaczonego `.t` i brak istniejącej
zawartości. Nie usuwano cudzych katalogów i nie zmieniano konfiguracji systemu.

Komendy z katalogu worktree, z powyższym kontrolowanym runnerem:

```powershell
.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.t/<nowy-id> services/worker/tests/test_grid_training_atomic_json.py
.venv/Scripts/python.exe -m ruff check services/worker/src/game_predictor_worker/images/grid_training_child.py services/worker/tests/test_grid_training_atomic_json.py
.venv/Scripts/python.exe -m mypy --follow-imports=skip services/worker/src/game_predictor_worker/images/grid_training_child.py
.venv/Scripts/python.exe -m pytest -q --tb=short --basetemp=.t/<inny-nowy-id> services/worker/tests/test_grid_training_handler.py services/worker/tests/test_grid_training_child_diagnostics.py services/worker/tests/test_grid_training_child.py -k "not test_real_trainer_trains_checkpoints_exports_and_releases_the_gpu_lease"
```

Logi: `artifacts/task1150-unit.log`, `task1150-lint.log`, `task1150-types.log`,
`task1150-consumers.log` (pierwsze długie ścieżki) oraz
`task1150-consumers-short-path.log` (końcowy PASS), `task1150-format.log`.
Po audycie test otrzymał wyłącznie guard P2-1 opisany poniżej. Nowy wynik12 PASS
dotyczy końcowych bajtów tego testu. Kod produkcyjny ma niezmieniony hash,
dlatego wcześniejsze34 PASS /1 deselected oraz scoped mypy pozostają aktualne;
regresji konsumentów nie ponawiano. Zamrożone hashe obu plików zaktualizowano
w `artifacts/task1150-frozen-sha256.txt`.

## Audyt i jedna runda P2-1

`TASK-1150_AUDIT_claude-opus-5-5.md`: R1 PASS, brak P0/P1. Zamknięto P2-1
w jedynej małej rundzie: callback `release_reader` zamyka natywny uchwyt tylko,
gdy `not released`. Kolejny backoff nie zamknie ponownie uchwytu o tym samym
numerze. Zachowano asercje jednej rzeczywistej odmowy i `[0.01]` opóźnień,
więc nieoczekiwana dodatkowa blokada pozostaje jawnym błędem testu.

Po tej zmianie ponowiono wyłącznie12 unit (PASS,1,31s), Ruff check testu
i Ruff format --check testu (oba PASS). Logi:
`artifacts/task1150-unit-p2.log`, `task1150-test-lint-p2.log`,
`task1150-test-format-p2.log`. Produkcja bez zmian; nie uruchamiano ponownie34
regresji ani GPU. Opcjonalnego dodatkowego testu dokładnych bajtów serializacji
nie dodano; dotychczasowa linia serializacji pozostała bez zmian.

## Pozostaje prowadzącemu

Końcowa mapa/docs gates, osobny commit/task-close i wdrożenie. Audyt Opus PASS,
P2-1 rozliczone powyżej. Lista audytu:
`artifacts/task1150-audit-paths.txt`.

TASK-1149 jest rozłączny; jego API/testy, plan, CURRENT_STATE, baza operatora,
usługi oraz root/main pozostały poza zakresem tego wykonawcy. Wznowienie tego
samego parent/run i istniejącego budżetu należy do prowadzącego. Trwały ACL
nadal kończy się błędem; mały retry nie obiecuje naprawy uprawnień.

Prowadzący: końcowa regeneracja mapy, code-map:check i docs:check PASS po task-close. Kod/test zgodne z zamrożonymi hashami. Oddzielny commit1150 zawiera także wymagany zapis hasha1149; nie miesza zmian produkcyjnych obu tasków.
