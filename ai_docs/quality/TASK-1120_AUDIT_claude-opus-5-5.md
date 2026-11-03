# Audyt TASK-1120 — Dane z korekt i trwały podział

Werdykt: PASS
Audytor: claude-opus-5-5, high
Wykonawca: gpt-6-astra, high
Zakres: HEAD...c65823fd7b37bb34e73a0269b18114b87b3e3ff2 oraz zmiany niezacommitowane, data 2026-11-02
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Runda 2 sprawdza, jak wykonawca rozwiązał znaleziska z raportu `ai_docs/quality/TASK-1120_AUDIT_claude-opus-5-5.md`, czyli P1-1, P1-2 i P2-1–P2-6.

Oba P1 są zamknięte:

- **P1-1:** nakładka `recording_cohort_command_v3` sprawdza teraz u starych kohort wyłącznie nowe rezerwacje `photoRoles`. Całą dotychczasową semantykę uwzględniającą rodzinę modelu przekazuje funkcji `recording_cohort_command_legacy_v3`. Test regresji odróżnia nową wersję od poprzedniej: na wersji z rundy 1 by nie przeszedł.
- **P1-2:** dodano brakujące testy ogrodzenia etykiet, zmiany rejestru, ochrony starych kohort i pełnego przebiegu poleceń z odtworzeniem utraconej odpowiedzi i konfliktem CAS. Wyniki starych zestawów PostgreSQL są uczciwie zapisane w Outcome.

Z P2:

- P2-1–P2-4 są naprawione.
- P2-5 to jawna zależność od TASK-1121.
- P2-6 jest odłożone do bramki T4 zgodnie z planem.

Pozostaje ryzyko resztkowe: część ścieżek starych kohort przez nakładkę nie ma ukończonego testu (stale-ready rollback, `bind_existing_report`). Do tego API przyjmuje nową politykę przy tworzeniu joba oceny.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-5] `ai_docs/delivery/GRID_CORRECTIONS_LEARNING_PLAN_20261102.md:83` — dołączenie kwalifikujących historycznych kohort wspólnej bazy przeniesiono jawnie do TASK-1121.
  - **Dowód:** plan, D-577 (`ai_docs/process/decisions/DECISION_LOG_2026.md`, akapit „Adapter T1 rozdziela korekty własnej gry…”) i Outcome. Do tego czasu API zamyka trening nowej polityki.
  - **Dyspozycja:** akceptacja jako jawnej zależności odbioru. Do weryfikacji w audycie TASK-1121.
- [P2-6] `ai_docs/tasks/1120-grid-correction-training-data.md:1151` — pełny `mypy --strict` (`npm run python:typecheck`) nie został uruchomiony.
  - **Co jest:** przechodzi tylko ukierunkowany mypy z `--follow-imports=silent` na 16 modułach produkcyjnych.
  - **Dyspozycja:** odroczenie do TASK-1123 (T4) jest zgodne z planem (`GRID_CORRECTIONS_LEARNING_PLAN_20261102.md:152`: „lint/typecheck/build/docs:check” w T4). Akceptacja ryzyka. Uwaga: kryterium „Właściwe testy, lint/typecheck” jest odhaczone, choć pełny typecheck jest odroczony.
- [P2-7] `services/api/src/game_predictor_api/application/grid_model_evaluation.py:195` — tworzenie oceny przyjmuje kohortę nowej polityki.
  - **Co się dzieje:** `GridModelEvaluationService._cohort` (wywołanie w `create`, linia 268) sprawdza tylko status `frozen`, rodzinę, bazę i `eligibility`. Nie sprawdza `policyVersion`.
  - **Skutek:** kohortę `application-grid-corrections-v1` z tą samą rodziną i bazą można dołączyć do oceny kandydata wytrenowanego na starej kohorcie. Powstaje wtedy trwały job oceny, który kończy się błędem w workerze (`services/worker/src/game_predictor_worker/images/grid_cohort_dataset.py:159`) albo przy `bind_existing_report`. Nakładka kieruje to polecenie do `recording_photo_cohort_v1`, która zwraca `RECORDING_COMMAND_INVALID` (`source_recording_sql_v4.py:69`).
  - **Ocena:** działa fail-closed, bez utraty danych. Jest to jednak ta sama klasa problemu co zamknięte P2-4 (job powstaje przed odrzuceniem), tylko na ścieżce oceny.
  - **Poprawka:** w `_cohort` odrzucać politykę inną niż `application-grid-cohort-v1` kodem `GRID_RUN_POLICY_UNSUPPORTED` (lub odpowiednikiem dla oceny), z testem jednostkowym. Albo jawnie przypisać to TASK-1121 w D-577.
- [P2-8] `services/api/src/game_predictor_api/storage/source_recording_sql_v4.py:174` — nakładka obsługuje też `bind_existing_report` i stale-ready freeze starych kohort, ale żaden ukończony test nie przechodzi tymi ścieżkami.
  - **`test_grid_training_cohort_e2e_postgres.py`:** przekroczył 110 s po etapie `restart_replay_eligible`. Nie wykonały się `new_process_dataset_passed` ani `_stale_ready_rollback`.
  - **`test_grid_model_evaluation_e2e_postgres.py`:** zatrzymał się przed powiązaniem raportu, na niezmienionym `_write_atomic` workera (za długa ścieżka).
  - **`test_grid_model_evaluation_bridge_postgres.py`:** blokuje go przestarzała asercja głowy `0168_source_crop_runs` w linii 51. Jest już w HEAD, sprzed tego taska.
  - **Ocena:** logika nakładki dla tych rodzajów jest prosta: pętla `photoRoles`, potem delegacja. Ryzyko błędu jest więc niskie, ale nie wykluczone testem.
  - **Poprawka:** w T4 lub osobnym tasku naprawić przestarzałą asercję głowy (także `test_grid_training_lane_migration_postgres.py:69` i `test_source_image_crops_postgres.py:297`). Uruchomić e2e kohort i oceny z uzgodnionym dłuższym limitem albo w krótszym katalogu roboczym, a wynik zapisać w Outcome.
- [P2-9] `services/api/src/game_predictor_api/storage/source_recording_sql_v4.py:182` — nakładka liczy pełny kontekst dla każdego użytego członka starej kohorty.
  - **Co się dzieje:** dla każdego członka wywołuje `recording_photo_context_v1`, czyli domknięcie grup, zbiór ról i `recording_digest_v1(recording_proof_v1(groups))`. Potrzebuje przy tym tylko `photoRoles`. Dzieje się to przy każdym `validate_cohort_use`, więc przy każdym `eligibility()` w currentness, ocenie, kandydacie wspólnym i podglądzie treningu.
  - **Skutek:** koszt walidacji starych kohort rośnie liniowo o pracę dowodu na każdego członka. Przy obecnych limitach czasu testów e2e (P2-8) nie da się statycznie wykluczyć, że ten koszt dokłada się do przekroczeń.
  - **Poprawka:** jedno zapytanie zbiorcze, które łączy użytych członków kohorty z `recording_photo_uses` po bajtach, pikselach i grupach z `recording_occurrences`, bez liczenia dowodu. Albo pomiar w T4 i akceptacja.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Korekty bez resave | spełnione | `storage/grid_correction_split.py:1359-1366` (tylko `reader.capture`), bez zapisów korekt |
| Tylko geometrie human-approved, 24 punkty | spełnione | zapytanie `approved` w `storage/grid_correction_split.py` (`population`) wyklucza `system:%` i `worker:%`; etykiety z `GridCohortEvidenceReader` |
| Wiarygodne atesty i kopie | spełnione | walidacja rewizji/atestów w `prepare_split`; `domain/grid_correction_split.py:486-494` (reprezentant); `tests/test_grid_correction_split.py` |
| Trwałe role i bufory po freeze (wszystkie źródła) | spełnione | `domain/grid_correction_split.py:472-476` (rola `None` ⇔ bufor); `source_recording_sql_v4.py:106-127,146-162`; `test_grid_correction_registry_postgres.py:219-226` (41 rezerwacji, 20 `used_in_cohort`) |
| Provisional preview bez trwałego użycia | spełnione | rezerwacje dopiero w `register_cohort_use` przy freeze (`application/grid_training_cohort_freeze.py:165-182`); rollback w `test_grid_correction_registry_postgres.py:194-198` |
| Stare polityki bez zmiany semantyki (D-577) | spełnione | `source_recording_sql_v4.py:182-192`; regresja `test_grid_training_cohort_storage_postgres.py:272-305` (VALIDATION z nagłówkiem TRAIN innej rodziny, REGRESSION z `final_test`), freeze, replay i READ ONLY validate w liniach 403-445 |
| Ogrodzenie etykiet, rejestru i populacji | spełnione | `application/grid_training_cohort_commands.py:262-272` z testem `test_grid_correction_split_adapter.py:162-196`; `GRID_CORRECTION_REGISTRY_CHANGED` w `test_grid_correction_registry_postgres.py:161-187`; populacja w `test_grid_correction_split_adapter.py:106-127` |
| Restart, utracona odpowiedź, konflikt rewizji | spełnione | `test_grid_correction_registry_postgres.py:381-454` (prepare/pages/freeze replay w nowej sesji, `GRID_COHORT_REVISION_CONFLICT`) |
| Blokada treningu nowej polityki przed jobem | spełnione (trening), z uwagą dla oceny | `application/grid_training_cohorts.py:136-140`, `application/shared_grid_model_candidate.py:72-78`, testy `test_grid_training_run_preview.py:175-179`, `test_grid_correction_cohort_contract.py:123-141`; ocena w P2-7 |
| Właściwe testy, lint/typecheck i dokumentacja | spełnione z zastrzeżeniem | Outcome: Ruff 22 pliki, ukierunkowany mypy 16 modułów, testy jak w tabeli Outcome; pełny mypy odroczony (P2-6); luki e2e w P2-8 |
| Audyt Opus 5.5/high bez otwartych P0/P1 | spełnione | ten raport: PASS |
| Outcome, task-close, wersjonowany commit, record-hash | niezweryfikowane | do wykonania przez koordynatora po tym audycie |

## Listy zamknięte i otwarte

Zamknięte:

- **P1-1:** nakładka sprawdza wyłącznie `photoRoles` (`source_recording_sql_v4.py:186-191`) i deleguje do `recording_cohort_command_legacy_v3` (linia 192). Test `test_grid_training_cohort_storage_postgres.py:272-305` z freeze (405), replay (433-440) i READ ONLY validate (444-445) przechodzi przez nakładkę po `upgrade heads` (linia 149). Outcome: 2 PASS.
- **P1-2:** testy ogrodzenia etykiet (`test_grid_correction_split_adapter.py:162-196`), zmiany rejestru bez częściowych wierszy (`test_grid_correction_registry_postgres.py:161-187`), nowej ochrony starych kohort (251-281) i pełnego przebiegu z replay/CAS (286-454). Stare zestawy PostgreSQL uruchomiono, a ich rzeczywiste wyniki zapisano w Outcome. Ryzyko resztkowe przeniesione do P2-8.
- **P2-1:** każde źródło dostaje rolę albo bufor (`domain/grid_correction_split.py:472-476`), a `recording_photo_cohort_v1` rezerwuje wszystkie z flagą `used_in_cohort` (`source_recording_sql_v4.py:126-128,154-161`). Test: 41 rezerwacji, 20 użytych.
- **P2-2:** liczby w komunikacie błędu (`storage/grid_correction_split.py:1405-1408` w briefie, `:223` w pliku) i test `test_grid_correction_split_adapter.py:130-159`.
- **P2-3:** `population_sha` pomija `revision_id`/`status` i zostawia tylko `active` (`storage/grid_correction_split.py`, `population_sha`). Testy `test_grid_correction_split_adapter.py:113-127`.
- **P2-4:** blokada `GRID_RUN_POLICY_UNSUPPORTED` w podglądzie i w kandydacie wspólnym, z testami. Ścieżka kolejki treningu korzysta z `apiBlockers` podglądu (`application/grid_training_runs.py:107`).

Otwarte: P2-5 (zaakceptowana zależność od TASK-1121), P2-6 (odroczone do T4), P2-7, P2-8, P2-9.

## Proponowane testy

- **Ocena z kohortą nowej polityki:** test jednostkowy `GridModelEvaluationService._cohort`/`create` z nagłówkiem `policyVersion: application-grid-corrections-v1`. Oczekiwane odrzucenie przed utworzeniem joba. Plik `services/api/tests/test_grid_correction_cohort_contract.py`, komenda `.\.venv\Scripts\python.exe -m pytest services/api/tests/test_grid_correction_cohort_contract.py`.
- **`bind_existing_report` starej kohorty przez nakładkę:** po naprawie przestarzałej asercji głowy uruchomić `$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'; .\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_grid_model_evaluation_bridge_postgres.py`.
- **Stale-ready rollback i dataset w nowym procesie:** dokończyć `test_grid_training_cohort_e2e_postgres.py` z uzgodnionym limitem czasu, w T4.
- **Pomiar kosztu nakładki:** czas `validate_cohort_use` starej kohorty z kilkuset członkami przed i po 0170.

## Zakres przeglądu i ograniczenia

**Przeczytane:**

- brief rundy 2, task z Outcome i dyspozycją, wyciąg planu (także T4) i diff niezacommitowanych zmian;
- `storage/source_recording_sql_v4.py` w całości i migracja `0170_grid_correction_photo_roles.py`;
- `storage/grid_correction_split.py` i fragment `domain/grid_correction_split.py` (przypisania, reprezentanci, liczby błędu);
- `application/grid_training_cohort_freeze.py` (freeze), początek `recording_cohort_command_v3` w `source_recording_sql_v3.py` (replay, wiązanie polityki) i `application/grid_model_evaluation.py` (`prove_cohort`, `_cohort`);
- testy: `test_grid_correction_registry_postgres.py` w całości, `test_grid_correction_split_adapter.py`, część `test_grid_correction_cohort_contract.py`, zmieniony fragment `test_grid_training_cohort_storage_postgres.py` oraz etapy `test_grid_training_cohort_e2e_postgres.py`.

Przestarzałą asercję głowy w `test_grid_model_evaluation_bridge_postgres.py:51` potwierdziłem `git log`: plik nie zmienił się od TASK-1047.

**Ograniczenia:**

- Nie uruchamiałem testów, lint, mypy, `openapi:check`, `docs:check` ani PostgreSQL. Wyniki z Outcome przyjąłem jako deklarację.
- Nie dało się statycznie ustalić, czy przekroczenia czasu e2e wynikają ze środowiska, czy z kosztu nakładki (P2-9).
- Wykonalności podziału na rzeczywistych danych operatora (117 plansz na 89 zdjęciach) nie da się sprawdzić statycznie.
