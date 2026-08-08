---
title: TASK-0176 worker lane resource budgets and Admin status
status: done
release: "0.4"
last_updated: 2026-08-05
---

# TASK-0176 — Worker lane resource budgets and Admin status

## Status

`done`

## Goal

Uzupełnić rozdzielenie kolejek o jawny, bounded budżet wątków obu lokalnych
procesów oraz wiarygodny status `running | degraded | stopped` widoczny w
workspace `Joby`, także wtedy, gdy worker jest bezczynny.

## Context

TASK-0172 i TASK-0173 rozdzieliły claimy oraz procesy, ale lokalny plik
supervisora nie jest kontraktem API, a heartbeat joba istnieje tylko podczas
przetwarzania. Panel nie odróżnia więc pustej kolejki od zatrzymanego workera.
Równoległe procesy dzielą CPU, RAM i dysk, dlatego ich biblioteki numeryczne i
prefetch muszą mieć jawne limity bez wprowadzania brokera ani mikroserwisu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/delivery/VERSION_0_4_EXECUTION_PLAN.md`
- `ai_docs/tasks/0171-fast-selection-real-corpus-regression-and-activation.md`

## Scope

- dodać małą tabelę stanu instancji worker lane przez migrację Alembic,
- rejestrować start, okresowy heartbeat również podczas bezczynności oraz jawne
  zatrzymanie procesu,
- wyliczać w API status lane z czasu ostatniego heartbeat zamiast z istnienia
  aktywnego joba,
- pokazać dwa zwarte statusy w workspace `Joby`: `General` i
  `Selekcja zdjęć`, z czasem ostatniego sygnału oraz budżetem wątków,
- ustawić przez supervisor osobny współdzielony budżet wątków bibliotek
  numerycznych; image selection ogranicza `scan_workers` do swojego budżetu,
- zachować cancel/retry adresowane identyfikatorem joba i dodać regresję, że
  akcja jednego lane nie zmienia drugiego.

## Out of scope

- twarde limity procentu CPU realizowane przez Windows Job Objects,
- limit pamięci kończący proces,
- przyciski uruchamiania lub zatrzymywania procesów z przeglądarki,
- Redis, Celery, osobny mikroserwis, kontener albo URL,
- pełny równoległy test rzeczywistego Importu i Selekcji — należy do TASK-0177,
- aktywacja selektora v9 — pozostaje w TASK-0171.

## Acceptance criteria

- [x] Każdy lane ma najwyżej jedną aktualną instancję opisaną tokenem procesu.
- [x] Bezczynny worker odnawia heartbeat bez tworzenia sztucznego joba.
- [x] Długi handler nie zatrzymuje heartbeat lane.
- [x] API zwraca deterministycznie `running`, `degraded` albo `stopped` dla obu
      lane oraz nie ujawnia ścieżek lokalnych i komend procesu.
- [x] Panel pokazuje oba lane niezależnie od filtra i obecności jobów.
- [x] Supervisor przekazuje jawne budżety wątków; zagnieżdżone biblioteki
      numeryczne nie zwiększają ich poza konfigurację procesu.
- [x] Image selection nie uruchamia więcej scan workers niż wynosi jej budżet.
- [x] Cancel/retry jednego joba nie zmienia joba ani statusu drugiego lane.
- [x] Migracja, testy API/workera/Admina, OpenAPI, typecheck i lint zmienionych
      części przechodzą w bounded czasie.

## Technical notes

Heartbeat lane jest diagnostyką procesu, a heartbeat joba pozostaje fencingiem
konkretnego wykonania. Rekord ma klucz lane i losowy `instance_token`; starszy
proces nie może nadpisać nowszej rejestracji. Brak rekordu lub jawne zatrzymanie
oznacza `stopped`; świeży heartbeat `running`; przekroczony próg świeżości bez
jawnego zatrzymania `degraded`, a po dłuższym progu `stopped`.

Budżet CPU w 0.4 jest kontrolowanym budżetem wątków, nie obietnicą dokładnego
procentu użycia procesora. Supervisor ustawia zmienne OpenMP/BLAS/NumExpr przed
startem każdego procesu. Image selection używa do czterech zewnętrznych scan
workers, ale natywne biblioteki pozostają jednowątkowe, co zapobiega
zagnieżdżonej oversubscription i pozostaje przenośne na późniejszy komputer.

## Expected files

- `services/api/alembic/versions/0032_worker_lane_runtime.py`
- `services/api/src/game_predictor_api/domain/worker_lanes.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/storage/worker_lane_repository.py`
- `services/api/src/game_predictor_api/application/worker_lanes.py`
- `services/api/src/game_predictor_api/api/worker_lanes.py`
- `services/api/src/game_predictor_api/schemas/worker_lanes.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/src/game_predictor_worker/jobs/runtime.py`
- `scripts/manage_worker_lanes.ps1`
- `apps/admin/src/features/jobs/job-monitor.tsx`
- `apps/admin/src/features/jobs/job-actions.ts`
- generated Admin API client and focused tests
- `ai_docs/process/CURRENT_STATE.md`

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests services/worker/tests -q
npm test --workspace @game-predictor/admin
npm run openapi:check
npm run typecheck --workspace @game-predictor/admin
npm run powershell:check
```

## Risks / open questions

- Status jest operacyjny i zależy od zegara API; próg musi tolerować krótki
  stall systemu, ale szybko ujawniać zakończony proces.
- Wspólny dysk nadal może ograniczać throughput. Pomiar realnej konkurencji
  należy do TASK-0177, a nie do tego pionu kontraktowego.

## Outcome

Zakończono 2026-08-05. Dodano migrację `0032_worker_lane_runtime`, tokenowane
rejestrowanie instancji i heartbeat obu procesów, niezależne stany
`running | degraded | stopped` w API oraz zwarte karty statusu w workspace
`Joby`. Supervisor przekazuje jawne budżety: `general=2`, a
`image_selection=4` z jednowątkowymi bibliotekami natywnymi, dzięki czemu
zewnętrzny prefetch nie tworzy zagnieżdżonej nadsubskrypcji CPU. Zatrzymanie
procesu zapisuje stan `stopped`, a token fencing chroni nowszą instancję przed
starym procesem.

Weryfikacja:

- migracja PostgreSQL i repozytorium runtime: `2 passed`,
- testy runtime/CLI workera: `11 passed`; pełny powiązany zestaw: `12 passed`,
- testy API statusu lane: `3 passed`,
- testy Admina: `167 passed`, klienta API: `32 passed`,
- typecheck Admina i klienta, OpenAPI check, mypy oraz Ruff: `passed`,
- składnia 25 skryptów PowerShell: `passed`,
- rzeczywisty bounded smoke supervisora: oba procesy `running` z budżetami
  `2/4`, po zatrzymaniu oba `stopped`, bez pozostawionych procesów.

Rzeczywisty jednoczesny przepływ Selekcji i Importu, pomiary zasobów oraz
niezależne cancel/retry pozostają bramką TASK-0177. Nie aktywowano selektora v9
i nie uruchamiano korpusu właściciela 40 000 zdjęć.
