# Audyt TASK-1137 — Wspólne limity budżetu uczenia siatek

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...2fed53b5fd001185354d7cf750a35a5ca8cf4c34 oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Sprawdziłem, jak zmiana wprowadza wersjonowaną politykę limitów `grid-training-limits-v2` (8000 kroków / 7200 s): w `RunBudget` i w `evaluate_admission`, w receipcie nadzorcy, w podglądzie API, w testach i w dokumentacji D-579. Plan treningu się nie zmienia: `TrainingPlan.of` i `estimate_cohort_cost` nadal korzystają z `preset.max_steps` i fingerprint presetu zostaje ten sam. Legacy budżet przechodzi na nowe pułapy dokładnie raz, a receipt trafia do trwałego zapisu przed startem procesu potomnego. Nie znalazłem błędów blokujących. Najważniejsze ryzyka są operacyjne: zużycie jest obcinane do starego pułapu w odzysku, który biegnie przed podwyższeniem, a cofnięcie kodu po zapisie kopert v2 nie jest możliwe.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `services/worker/src/game_predictor_worker/images/grid_training_handler.py:242` — Handler wywołuje `_recover_previous_attempt` przed `_admit`. Odzysk działa więc jeszcze na legacy kopercie z pułapami 4000/3600. `charge()` (`grid_training_admission.py:460`) obcina `used_seconds` do starego `max_seconds`, a kroki z `progress.json` są obcinane do starego `max_steps` (`grid_training_handler.py:253`). Skutek: jeśli osierocona próba przekroczyła stary pułap w niepotwierdzonym oknie (najwyżej `UNCONFIRMED_LIMIT_SECONDS` plus czas oczekiwania), nadwyżka przepada. Po podwyższeniu run dostaje wtedy trochę więcej zapasu, niż wynikałoby z rzeczywistego zużycia. To częściowo podważa kryterium „pełne zużycie zachowane”. Dla rzeczywistego runu (1149 s, attempt 2, `chargedAt` po zatrzymaniu wyczyszczony) problem nie występuje. Propozycja: zaakceptować i opisać ryzyko w D-579, bo strata jest ograniczona do jednego niepotwierdzonego okna. Alternatywa: liczyć odzysk na `with_current_limits(...)` jeszcze przed obcięciem, a receipt zapisać z kopertą sprzed odzysku.
- [P2-2] `services/worker/src/game_predictor_worker/training_core/grid_training_admission.py:480` — Pole `limit_policy` trafia do ciała koperty, które obejmuje digest. Kod sprzed TASK-1137 odczyta taką kopertę w `cls(**values)` jako `TypeError` i zgłosi `GRID_RUN_BUDGET_CORRUPT`. Skutek: po pierwszym zapisie v2 (każdy nowy run i każdy podwyższony legacy run) cofnięcie workera do v1.7.530 lub wcześniejszego, albo nadzorca GPU działający bez restartu, zamyka takie joby błędem stanu. D-579 (`ai_docs/process/decisions/DECISION_LOG_2026.md:24`) wymaga restartu nadzorcy, ale nie wspomina o tym, że rollback jest niemożliwy. Propozycja: dopisać to zdanie w Consequences D-579 albo w Outcome jako akceptację ryzyka.
- [P2-3] `services/api/tests/test_grid_training_run_preview.py:82` — Dwa zastane testy w zmienianym pliku nadal nie przechodzą: `:82` i `:189` (log `artifacts/task1137-api-baseline.log` potwierdza też wynik baseline). Zgodnie z AGENTS.md (sekcja „Testy, benchmarki i regresje”) jest to poza zakresem i zostało opisane w Outcome. Brakuje jednak trwałego śladu poza taskiem. Propozycja: dopisać blocker do `ai_docs/process/CURRENT_STATE.md` albo założyć osobny task naprawy tych testów, żeby czerwony plik nie maskował przyszłych regresji podglądu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Nowe i jawnie wznowione rozpoznane legacy runy mają pułapy 8000/7200, plan i fingerprint bez zmian | spełnione | `grid_training_admission.py:220-231`, `:405-432`, `:561`; plan nadal `min(planned_steps, preset.max_steps)` w `grid_training.py:331`; test `test_grid_training_resource_admission.py:242-285` (wszystkie trzy presety, `planned_steps == 1200`, fingerprint) |
| Pełne zużycie i historia zachowane; reset/restart/utrata odpowiedzi nie dodają kolejnego pułapu | spełnione z zastrzeżeniem P2-1 | `with_current_limits` tylko dla `LEGACY_LIMIT_POLICY` (`grid_training_admission.py:423`); round-trip i replay `test_grid_training_resource_admission.py:273-277`; nowy interpreter `:310-335`; handler `test_grid_training_handler.py:456-512` |
| Przekroczenie nowego pułapu blokuje; smoke i obce/nieznane koperty bez niejawnego upgrade | spełnione | `grid_training_admission.py:421-428`, `:562-563`; testy `test_grid_training_resource_admission.py:211`, `:276-277`, `:288-307` (nieznane pułapy, smoke, nieznana polityka → CORRUPT) |
| Receipt utrwalony przed startem dziecka; replay po utracie odpowiedzi nie dubluje receiptu | spełnione | receipt w `_admit` (`grid_training_handler.py:457-467`), zapis „admitted” przed launcher (`:611-615`); test `test_grid_training_handler.py:456-512` (`checked_launch`, jeden receipt) |
| Podgląd i dopuszczenie używają tych samych limitów; bez nowych endpointów | spełnione (po wdrożeniu i restarcie nadzorcy) | `preset_view` `grid_training_admission.py:595-596`, `within_budget` `:340`; test `services/api/tests/test_grid_training_run_preview.py:108-119`; brak zmian schematów, OpenAPI i routerów w diffie |
| Testy pionu/lint/typecheck/docs/map, Opus, task-close, osobny commit | niezweryfikowane (część procesu jeszcze trwa) | logi wykonawcy: `artifacts/task1137-core-tests.log` (94 passed), `artifacts/task1137-api-tests.log` (40 passed, 2 zastane FAIL); mapa `CODE_MAP_SYMBOLS.md`; task-close i commit jeszcze nie wykonane |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): nie dotyczy.

Otwarte: P2-1, P2-2, P2-3.

## Proponowane testy

- Test handlera dla legacy koperty z `chargedAt` ustawionym tuż przed starym pułapem (np. `used_seconds=3550`, osierocona próba, niepotwierdzone okno 100 s). Asercja ma udokumentować świadome zachowanie: obcięcie do 3600 albo zachowanie pełnej nadwyżki. Plik `services/worker/tests/test_grid_training_handler.py`, komenda `.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_grid_training_handler.py -k legacy` (timeout 120 s).
- Test handlera, który sprawdza, że `previousBudget` w receipcie zgadza się z kopertą po odzysku, gdy odzysk naliczył czas. Ten sam plik i ta sama komenda.

## Zakres przeglądu i ograniczenia

Przeczytałem cały brief z diffem, a do tego `grid_training_admission.py` (presety, `training_budget_limits`, `estimate_cohort_cost`, `RunBudget`, `evaluate_admission`, `preset_view`) i fragmenty `grid_training_handler.py` (`RunState`, `__call__`, `_recover_previous_attempt`, `_admit`, `_train`, `_reserve`, `_settle_steps`). Przejrzałem też `TrainingPlan.of` w `grid_training.py`, ścieżki `resume` i `view` w `services/api/.../grid_training_runs.py`, miejsca używające `RunBudget` i historii stanu, regułę AGENTS.md o zastanych błędach oraz artefakty `artifacts/task1137-*.log` i `task1137-operator-budget-preview.json`. Testów, lintów, mypy ani `docs:check` nie uruchamiałem. Wyniki weryfikacji pochodzą z logów wykonawcy. Nie sprawdzałem zachowania na rzeczywistej bazie ani działania nadzorcy GPU po restarcie.
