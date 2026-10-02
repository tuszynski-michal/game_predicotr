---
title: T08 release readiness V2-only
status: active
last_updated: 2026-09-26
---

# T08 — wynik `no-go` dla apply 0125

## Identyfikacja i granice dowodu

- Revision bazowa: `df725f00e2036bd34864bc636e5d39464bab2064` (`v0.10.451`) wraz ze zmianami roboczymi.
- Deployment jest source-run: `python -m game_predictor_api` / `python -m game_predictor_worker`. Brak osobnej binarki nie jest blockerem; wcześniejsze stwierdzenie sprostowano.
- SHA256 źródeł/config testowanego deploymentu: `b253f4d1b3abb8d48f22b3c0982186529831a416a20e97aa4dc9532f504c7edd`. Algorytm identyfikacji: `_source_identity` nowego smoke.
- Właściwa `.venv`, Python 3.12.10, działa poza sandboxem. Diagnoza brakującego Pythona była błędna; TASK-0696 wycofano.
- Smoke: unikatowa baza `game_predictor_t08_de10f8d44b1b48d0b260b42a689ad937`, Alembic `0125_remove_legacy_public_game_store`, odrębne katalogi temp.
- Baza użytkownika pozostała na `0124`; nie wykonano na niej DDL/DML.
- Końcowy smoke: 67,56 s. PID API: 28300 i 2476; worker: 5900 i 32912. Wszystkie zakończono, bazę izolowaną usunięto bez FORCE.
- Surowy raport (temp, nietrwały): `%LOCALAPPDATA%/Temp/pytest-of-tuszy/pytest-112/test_fresh_api_and_worker_rele0/release-readiness.json`. Ten dokument zachowuje wyniki niezależnie od retencji temp.

## Rzeczywiste procesy API i workera

| Sprawdzenie | Wynik |
|---|---|
| Brak wszystkich 65 legacy public relacji | passed |
| Zachowanie catalog/control/shared | passed |
| Utworzenie active V2 i niepusty dataset | passed |
| Trwały job projekcji symboli wykonany przez worker | completed / ready |
| Restart API, odczyt ukończenia | passed |
| Drugi świeży worker | no_job |
| Brak location | 409 GAME_STORAGE_LOCATION_MISSING, fail-closed |
| POST game image-geometry-rollout | 422 UNSUPPORTED_JOB_PAYLOAD_VERSION, schemaVersion=3 |
| GET dataset-versions/{id}/layouts | 500, brak dataset_versions, bez owner scope |
| GET review-batches | 500, brak review_batches, bez globalnego routingu |

Nowe pliki `test_legacy_public_store_release_readiness.py` i `legacy_release_process_probe.py` zachowują trzy czerwone asercje. Ruff check, format i mypy obu plików przechodzą. Inicjalizacja ma limit 30 s, następnie HTTP readiness 10 s; skończone kroki mają timeout. Testowy probe uruchamia rzeczywiste entrypointy i zapisuje tożsamość/PID.

## Naprawy i testy skoncentrowane

| Obszar | Wynik i ograniczenia |
|---|---|
| Worker raw/normalized/payout — TASK-0697 | 3 passed w 41,41 s; retry po dispose/nowej sesji; SQLSTATE 42P01 bez scope, 23503 dla obcej gry. Ruff/format/mypy 4 plików passed. |
| Image batch — TASK-0694 | 15/16 scenariuszy passed w osobnych procesach: 13 head0125 i 2 historyczne migracje. Seed dwóch pending właścicieli jednej sekwencji narusza constraint0069. Ruff/format passed; 8 zastanych błędów mypy. |
| Catalog | 2 passed |
| Image selection | 4 passed |
| Browser staging retention | 1 passed; scoped asercje osobno dla obu gier, shared poza scope; ponowiono po audycie. |
| Worker fencing | 1 passed |
| Release workflow | seed V2 ujawnia brak scope w get_game_source_for_update; nie dodano sztucznego globalnego scope. 6 zastanych błędów mypy w teście. |
| Import report | EXPECTED_COUNT_MISMATCH zamiast NOT_READY_FOR_PUBLICATION — TASK-0695 |
| M2 Admin | 422 extra_forbidden payload symbolu — TASK-0695 |

Pełnej suite nie ponowiono. Dawny przekaz 49 failed / 64 passed dotyczył 28 plików bez zachowanego dokładnego wyboru; nie jest wynikiem tego przebiegu. Nie sumować powtórzeń jako odrębnych testów. Stałe nazwy baz sprawdzano przed uruchomieniem; po testach użyte bazy nie pozostały.

Mypy ma niepoprawny separator w config `mypy_path`. Kontrole użyły `MYPYPATH=services/api/src;services/worker/src` oraz `--follow-imports=silent`. To obejście, nie trwała naprawa; przyczyna jest w TASK-0695. Retention/import-report: mypy dwóch plików passed. Zastanych błędów nie wyciszano.

## Niezależne audyty

- TASK-0697: `gpt-6-astra/medium`, brak P0–P2; cele ON CONFLICT odpowiadają PK V2, testowy scope odpowiada LocalJobWorker.
- Fixture i nowe smoke: `gpt-6-astra/medium`, brak nowych P0–P2. TASK-0694 nie jest done bez pełnego przebiegu i klasyfikacji wszystkich awarii. Zastane stałe nazwy baz i FORCE wymagają kontroli przed uruchomieniem.
- Globalny routing: potwierdzona sprzeczność D-038 (źródła i rodzic w jednej transakcji) z pojedynczym game binding V2. Wymaga jawnego rozstrzygnięcia architektury — TASK-0698.

## Odtworzenie smoke — PowerShell, katalog repo

```powershell
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS='1'
.\.venv\Scripts\python.exe -c "import subprocess,sys; sys.exit(subprocess.run([sys.executable,'-m','pytest','services/api/tests/integration/test_legacy_public_store_release_readiness.py','-q','-s','--tb=short'], timeout=120).returncode)"
```

Test tworzy bazę UUID. Nie uruchamiać na bazie użytkownika.

## Bramka operacyjna

Read-only preflight `legacy-public-preflight-20260926-t09-preparation.json` z 2026-09-26 07:16:30 CEST: ready, 65 pustych tabel, 3 active V2, brak blockerów preflight. SHA256: `1df832cd6cbbbc348a4585780ac3207da15a71a223d26ad7a524d8edd5459908`.

**T08 pozostaje no-go. T09–T12 nie wykonano.** Ready preflight nie zastępuje readiness ani osobnej zgody na apply konkretnego świeżego raportu. Globalnych wejść nie wolno maskować public fallbackiem, wyłączeniem RLS, fikcyjnym scope fixture ani rozbiciem atomowego release bez decyzji. Kolejność T09→T10→T11→T12 pozostaje obowiązująca.
