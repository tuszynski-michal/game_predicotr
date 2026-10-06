---
title: TASK-0881 — rejestr kandydata lab
status: done
last_updated: 2026-10-06
---

# TASK-0881 — rejestr kandydata lab

## Status

`done`

## Goal

Zarejestrować kandydatów lab w istniejącym zasobie modeli bez fikcyjnych human cohort, z preview i recovery.

## Context

Operator zlecił podłączenie Mumii do głównej aplikacji, uploady folderów,
korektę siatek i symboli oraz dalsze zbiorcze uczenie. Nie wymagać nowych
etykiet przed implementacją. Plan konkretyzuje przyjęty zakres.

## Dependencies / entry conditions

TASK-0880 PASS; nie stosować migracji na DB użytkownika przed konkretnym preview/zgodą.
Pracować w C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3.
Weryfikować rzeczywisty HEAD tej gałęzi przed numeracją commita.

## Recommended execution

gpt-6.1-sol / high; konfiguracja zgodna z tabelą planu.
Niezależny review: gpt-6.1-sol / high. Eskalować analizę przy sprzeczności
pochodzenia danych, kontraktu lub ochrony poprzednich konsumentów.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/requirements/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/architecture/SUPERVISED_MODEL_IMPROVEMENT.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/MUMIE_MAIN_APP_PILOT_EXECUTION_PLAN_20261006.md
- ai_docs/process/DECISION_LOG.md — D-521
- ai_docs/delivery/GRID_V3_SHADOW_CONTRACT_20261005.md

## Scope

Wykonać dokładnie sekcję TASK-0881 planu, wraz z jej walidacją, stanami błędów,
idempotency, ochroną poprzednich workflowów i odtworzeniem w nowym procesie.
- Jawne pochodzenie lab_import i checksum-bound origin manifest.
- Migracja 0144 zachowuje istniejące production_training rekordy.
- Import idempotentny po utracie odpowiedzi i restarcie.
- Activation preview, per-game snapshot i deaktywacja pierwszego pilota.
- Spójny backend/OpenAPI/generated client/wrapper/UI/request tests.
- Regresja 777 i ochrona zatwierdzeń.

## Out of scope

Nowy seed/refit V5, trening na predykcjach, targety Super, fikcyjne human
approvals, automatyczna aktywacja poza zatwierdzonym preview, usuwanie danych,
push oraz zmiany modelu 777.

## Acceptance criteria

- [x] Jawne pochodzenie lab_import i checksum-bound origin manifest.
- [x] Migracja 0144 zachowuje istniejące production_training rekordy.
- [x] Import idempotentny po utracie odpowiedzi i restarcie.
- [x] Activation preview, per-game snapshot i deaktywacja pierwszego pilota.
- [x] Spójny backend/OpenAPI/generated client/wrapper/UI/request tests.
- [x] Regresja 777 i ochrona zatwierdzeń.

## Technical notes

Implementation started after TASK-0880 commit v1.7.222 /
e8de3b18d389207a5ceaa5d171e8a9e14d46c346. Executor: gpt-6.1-sol / high.
The existing model-iterations resource will expose managed candidate inventory
and preview. Import uses a VALIDATE job with server-pinned candidate identity.
The latest deactivation event must be read before resolving a cohort; an inner
join must not expose an older activation after a null-target deactivation.
Additional implementation files: application/lab_symbol_candidate_import.py,
storage/lab_symbol_candidate_import_repository.py,
storage/lab_symbol_candidate_validation.py,
worker/symbols/lab_candidate_import.py,
alembic/versions/0144_lab_symbol_candidate_registry.py, and focused tests.
Runtime composition, job response schemas, generated client, client wrapper and
Admin model-quality UI belong to the same change. No operator database writes,
service changes, model activation or migration execution are authorized here.

Plan jest źródłem rozstrzygnięć technicznych tego taska, D-521 jego zakresu
produktowego. Nie zastępować całych źródeł pojedynczymi wycinkami w podziale
train/test. Zdjęcie z pięcioma pozycjami nie może mieć dziewięciu slotów.
R2 RGB i odrzucona para R2 to różne kwalifikacje. Runtime lab RGB potrzebuje
bilinear antialias na RGB96, nie istniejącego INTER_AREA.

Zmiana kontraktu wymaga pełnego pionu OpenAPI/klient/wrapper/request test.
Task nie nadaje zgody na operacje DB użytkownika; szczegółowy preview stanowi
wejście 0884. Własne zmiany CURRENT stagingować oddzielnie od dawnych metadanych.

## Expected files

- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\storage\models.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\storage\symbol_model_snapshot_resolver.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\storage\symbol_model_registry_repository.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\api\symbol_model_iterations.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\src\game_predictor_api\schemas\symbol_model_iterations.py
- Istniejące: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\apps\admin\src\features\model-quality\model-quality-workspace.tsx
Nowe moduły, testy i migracje wskazano jawnie w odpowiadającej sekcji planu.

## Test cases

- Jawne pochodzenie lab_import i checksum-bound origin manifest. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Migracja 0144 zachowuje istniejące production_training rekordy. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Import idempotentny po utracie odpowiedzi i restarcie. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Activation preview, per-game snapshot i deaktywacja pierwszego pilota. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Spójny backend/OpenAPI/generated client/wrapper/UI/request tests. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.
- Regresja 777 i ochrona zatwierdzeń. — odtworzyć scenariusz i zapisać wynik; samo uruchomienie procesu nie wystarcza.

## Verification

Planowane testy istniejące oraz jawnie proponowane nowe:
- Nowy: C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_lab_symbol_candidate_import.py

```powershell
& 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' 'C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\run_step.py' --timeout 120 --cwd 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3' --name '0881-focused' 'C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe' -m pytest 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_lab_symbol_candidate_import.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_symbol_model_iterations.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_symbol_model_registry.py' 'C:\Users\tuszy\Documents\game_predicotr\worktrees\grid-engine-v3\services\api\tests\test_symbol_model_snapshot_resolver.py' -q
```

Polecenie jest planowane; nowe testy powstaną razem z właściwą implementacją.
Dla zmienionych modułów uruchomić tym samym ograniczonym runnerem python -m
ruff check, ruff format --check i mypy z dokładnymi absolutnymi ścieżkami modułów.
Dla pionów API/UI dodatkowo sprawdzone npm run openapi:generate/openapi:check,
admin:build i reviewer:build w wskazanym absolutnym worktree.
Odbiór obejmuje nowy proces i utraconą odpowiedź. Wyniki zapisuje Outcome;
planowane polecenie nie stanowi wyniku PASS.

## Risks / open questions

- Brak blokującej decyzji operatora dla przygotowania implementacji.
- Migracja/aktywacja na rzeczywistej bazie wymagają gotowego preview.
- Główna gałąź ma nowszą niezależną pracę RGB0878; zachować ją przy integracji.

## Outcome

### Changed

Przygotowano migrację 0144 z jawnym pochodzeniem production_training/lab_import.
Kandydat lab nie otrzymuje fikcyjnej kohorty ani epok treningu. Istniejący
zasób modeli udostępnia zarządzany inventory, zweryfikowany preview i import
VALIDATE z pinami wyznaczonymi przez backend. Import odtwarza trwały receipt
przed sprawdzeniem bieżących artefaktów i katalogu; publikacja sprawdza lease,
anulowanie, własność gry, checksumy i wszystkie powiązania.

Dodano preview i idempotentną deaktywację rejestru. Najnowsze wyłączenie
zatrzymuje resolver zamiast ujawniać wcześniejszy model. Cleanup blokuje
usunięcie takiego wyłączenia wraz z historycznym modelem. Synchronizacja
statusu iteracji obejmuje API cancel/retry i odzyskanie wygasłego joba po
awarii workera. TRAIN i istniejące rodzaje VALIDATE zachowują swoje kontrakty.

Backend, OpenAPI, wygenerowany klient, wrapper, testy żądań i panel Admin
tworzą jeden pion. Panel zapisuje pełne potwierdzone polecenie przed POST,
odtwarza je po restarcie/utracie odpowiedzi i zachowuje po 401/403/408/429/5xx.
Domenowe 404/409/422 pozwalają odświeżyć preview i wydać nowe polecenie.
Kwalifikacja pilota pokazuje osobno 34 kontrolne komórki, pochodzenie
human/AI i brak oszacowania jakości populacyjnej.

### Verification results

Wszystkie wyniki dotyczą absolutnego worktree grid-engine-v3. Runner miał
limit 120 sekund na krok. Pełny allowlist 42 plików, dokładne ścieżki testów,
polecenie PG i wyniki zapisano w:
C:\Users\tuszy\Documents\game_predicotr\artifacts\grid-v3-deployment-20261004\0881-final-proof.json.

- Backend/worker: 64 PASS, w tym receipt replay po drift, fencing, faktyczne
  requeue_job → save_job, crash/cancel/recovery, blokada cleanup i pięć
  istniejących/nowych konsumentów dispatch. Proof: 0881-focused-complete.json.
- Izolowany PostgreSQL: 1 PASS przez istniejący guarded
  application_role_database("t0881"), bez użycia bazy operatora. Odbiór
  potwierdził upgrade istniejącego rekordu production_training, constrainty,
  import/publikację, odtworzenie receipt w nowym procesie Python,
  activation/deactivation, scope-less/cross-game izolację i fail-closed
  downgrade z historią. Proof: 0881-isolated-pg-3.json.
- Klient API: 83 PASS. Panel i istniejące workflowy: 14 PASS, w tym stale
  deactivation 409 oraz utrata odpowiedzi → 403 → ponowne uwierzytelnienie →
  identyczny retry. Proof: 0881-client-tests.json i 0881-frontend-tests-final.json.
- Ruff lint i format: PASS dla 30 zmienionych modułów/testów.
  ESLint i Prettier zmienionych plików UI/klienta: PASS.
- Strict scoped Mypy: PASS dla 23 modułów. Typecheck Admin i klienta: PASS.
  Próba pełnej kompozycji Mypy przekroczyła limit 120 sekund; runner zakończył
  procesy potomne. Nie rozszerzano zakresu na dawne zależności.
  Świeży import API i CLI workera: PASS, bez startu lifespan lub usług.
- OpenAPI export --check, generated-client drift check: PASS.
- Admin build i Reviewer build: PASS. Pozostały wyłącznie wcześniejsze
  ostrzeżenia Next dotyczące wielu lockfile oraz ostrzeżenia zależności w testach.
- Niezależny audyt gpt-6.1-sol/high: 0 otwartych P0–P2. Wszystkie zgłoszone
  recovery, deactivation i cleanup regresje mają reprodukcję i PASS.
- git diff --check dla allowlist: PASS.

### Not completed

Nie wykonano migracji, importu ani aktywacji na bazie operatora. Nie
restartowano usług, nie scalano gałęzi, nie uruchamiano TASK-0882.
Implementacja i odbiór spełniają sześć kryteriów taska oraz odpowiadającą
sekcję zaakceptowanego planu. Osobny commit v1.7.223 i jego pełny hash
zostaną potwierdzone z historią po publikacji. Stare brudne metadane tasków
pozostają poza zakresem commita.

### Documentation updates

Ten task: kryteria odbioru, opis implementacji i rzeczywiste wyniki.
Root uzupełnia CURRENT_STATE, końcowy commit i przeniesienie do completed;
plan oraz decyzje pozostają w jego zakresie.

### Recommended next task

TASK-0882. Kontynuować zgodnie z planem po audycie i commicie.
