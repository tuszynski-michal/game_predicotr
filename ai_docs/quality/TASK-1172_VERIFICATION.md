# TASK-1172 — Weryfikacja D-596/D-597

Data: 2026-11-09; baza v1.7.583/14fcfb4e. Wyniki wykonawcy astra/high,
raport przygotowany do niezależnego przeglądu. Nie deklaruje audytu PASS.


Z katalogu worktree: właściwe testy pytest przez D:/game_predicotr/.venv/Scripts/python.exe
z PYTHONPATH własnego services/api/src i services/worker/src; testy Admin
`npm run test:geometry --workspace @game-predictor/admin`, scoped lint/typecheck,
`npm run docs:check`, `npm run code-map:check`. Każda komenda ma timeout.
Szerszy build dopiero po testach pionu. Audyt według CROSS_AUDIT do 1800 s.

Wykonawca: logi `artifacts/t1172-*`; interpreter
`D:/game_predicotr/.venv/Scripts/python.exe`, `PYTHONIOENCODING=utf-8`,
`PYTHONUTF8=1`, absolutne PYTHONPATH worktree API/worker/integration; timeout120s
na fazę i krótkie basetemp. Potwierdzone:

- API20 PASS (`t1172-existing-api.log`); reference unit5 PASS
  (`t1172-render-unit3.log`), dodatkowy rzeczywisty receipt/pin v2 w nowym procesie
  SQLite PASS (`t1172-cold-v2-final.log`). Replay omija zmieniony aktywny resolver;
  nullable targetSelection i brak/null nowego pola zachowują dawny fingerprint.
- Worker recovery/ledger/earlyguard15 PASS (`t1172-worker-recovery.log`), w tym
  zero wywołań sieci/banku/optymalizatora po błędzie preflight.
- Końcowy D597/preflight/crop50 PASS25.72s (`t1172-d597-final-tests.log`): realny
  oracle30 obrazów, SQL czytnik obu passów i aktualnych rewizji, CPU porównanie
  8→0, brak/unknown/context tamper/stale/missing pair odrzucane; domyślne
  content_pin, ProductionContentRun i preflight nadal blokują kwalifikację.
  D597 używa SQLite, nie poświadcza PostgreSQL RLS ani operatorskiej jakości.
- Disposable PostgreSQL v2: setup94.94s (`t1172-pg-setup3.log`, retained setup
  sam nie jest suite PASS), następnie nowy proces phase2 PASS1/102.77s
  (`t1172-pg-phase2.log`): rzeczywisty LAB registry0, zachowany import8,
  legacy create receipt cold replay, abandoned v1, frozen A, parent/freeze,
  jeden child, pełny worker proof reread i inventory. Oryginalny target.render8
  jest odrębny od execution0. Cleanup w nowym procesie potwierdza
  0DB/0runtimeRoles/0capabilityRoles (`t1172-pg-cleanup.json`), prywatny plik
  usunięty. D597 nie wymagał powtarzania tej kosztownej próby.
- Admin interaction28 PASS (`t1172-admin-interaction.log`), nowe wysłanie v2
  dodatkowo PASS1 (`t1172-admin-interaction-final.log`); SDK wrapper5 PASS
  (`t1172-client-test.log`); eksport OpenAPI/generacja i drift PASS
  (`t1172-generated-drift.log`). Istniejący wrapper przekazuje body bez zmian.
- Ruff/format i mypy19 plików PASS (`t1172-d597-ruff-final.log`,
  `t1172-d597-mypy.log`); końcowy nowy test receipt ma osobny Ruff PASS
  (`t1172-final-ruff2.log`). Admin scoped ESLint exit0, ostrzeżenie o katalogu
  pages przy uruchomieniu z root; TypeScript i Prettier sprawdzone osobno.
  Końcowy TypeScript exit0 (`t1172-admin-types-final.log`) i API domain/pins17
  PASS2.40s (`t1172-api-final.log`); `git diff --check` PASS.

Nie ma pełnego PASS istniejącego testu
`test_grid_content_experiment_workflow.py::test_real_child_dispatch_completes_and_replays_lost_export_response_once`:
próba T3 timeout120s/Windows fatal access violation w Torch Adam
(`t1172-workflow-trace.log`). Root wykonał ten sam nodeid na unchanged main
f8b8a05a: timeout60s, stos w fsync ledger, nie Adam
(`t1172-main-workflow-baseline.log/json`). To nie dowodzi tej samej przyczyny;
przyczyna pozostaje nieustalona. Nie osłabiono testu ani nie naprawiano Torch.
Po testach brak własnych orphan; trzy zastane procesy operatora nietknięte.
Mapy/docs check, niezależny Opus i zamknięcie pozostają po stronie root.


## Zasoby testowe

Potwierdzenie cleanup z nowego procesu: artifacts/t1172-pg-cleanup.json.
Zapisany full workflow timeout nie jest PASS ani dowodem błędu operatorowego modelu.
Rzeczywisty trening operatora i wdrożenie pozostają osobnymi operacjami.

Root po freeze: mapy zregenerowane; docs:check i code-map:check PASS
(startup43943B). Logi artifacts/t1172-root-*. Niezależny audyt pozostaje następny.

## Jedna runda poprawek R1

Opus R1 REVISE0P0/4P1; kod po jednej rundzie poprawek zamrożony do focused R2.
Szczegółowa mapa: TASK-1172_FIXES_R1.md. Selector/preflight29 PASS10.04s,
regresje73 PASS40.09s, nowy PostgreSQL actual advance/oracle/JSONB1 PASS29.87s,
nowoprocesowy cleanup0DB/0runtimeRoles/0capabilityRoles. Ruff/format28 PASS,
mypy19 PASS. API/SDK/Admin nie zmieniły się w poprawkach i nie powtarzano ich
zaliczonych kontroli. Logi artifacts/t1172-r1-*. P2-1(per-board resolver),
P2-4(długi workflow bez PASS), P2-5(fully-visible wyjątek) przyjęte jawnie.

Focused Opus R2 REVISE0P0/1P1. Root potwierdził samodzielną kolekcję
nowego testu Worker bez PYTHONPATH: exit2 ModuleNotFoundError; log
artifacts/t1172-r2-p1-collection-repro.log. Nie ma task PASS/commita;
jedna runda poprawek wykorzystana, oczekuje dodatkowej decyzji operatora.

## Zatwierdzona dodatkowa poprawka P1-5

Operator zezwolił na dodatkową poprawkę i skupioną kontrolę Opus, potem całe T4.
Zmieniono wyłącznie bootstrap importów jednego testu. Nowe procesy, PYTHONPATH
usunięty: pojedynczy plik collect-only PASS1/15.96s; cała Worker collect-only
PASS3623/33.87s. To kolekcja, nie wykonanie3623 testów. Ruff/format/diffcheck PASS.
PG nie powtarzano, produkcyjny kod pozostaje bez zmian od poprzedniego R2.
Dowody artifacts/t1172-p15-*.log/json i TASK-1172_FIXES_P1_5.md.
Poprzedni R2 REVISE oraz receipt zachowane jako _R2; nowa kontrola ma osobny
payload/request i oznaczenie lokalne R2b, formalny ReviewRound2 runnera.

Końcowy dodatkowy focused R2b Opus PASS0P0/0P1, payload i report SHA
zweryfikowane z receipt. Canonical i exact _R2b zachowane; scope dodatkowy
7 plików, poprzedni R2 zamknął produkcyjne P1. P2-1/4/5/7/8 przyjęte jawnie
w końcowym Outcome, P2-9 metadanych poprawione przy zamknięciu.
