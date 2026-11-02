---
title: TASK-1122 implementation verification
status: active
last_updated: 2026-11-02
---

# TASK-1122 — weryfikacja przed audytem

Aktualna implementacja i weryfikacja znajdują się w
`D:/game_predicotr/worktrees/grid-corrections-learning`. Po audycie T2 R2 PASS
i commicie `7801ea4711f92f04eeeb58bfed124f9f850e01e0` (`v1.7.518`) lead przeniósł
T3 przez clean three-way merge, zachowując poprawki R1/R2. Ten commit jest bazą
audytu T3. Pierwotny `grid-corrections-panel` pozostaje zamrożony; historyczne
trees7c/5394 i manifestv2 opisują wyłącznie przygotowanie, nie bieżącą bazę.
Indeks zawiera przeniesione hunki T3 i nie był resetowany przez wykonawcę
integracji. Metadane record-hash T2 zachowano oddzielnie. T3 nie ma commita;
obowiązkowy audyt Opus5.5/high nadal poprzedza jego zamknięcie i commit.

## Zakres i wynik

Panel prowadzi przez korekty/braki, start, postęp, raport, oddzielne zastosowanie
i historię/przywrócenie. Dawne sterowanie pozostaje w Zaawansowanych, a próbka
jakości i reinference są osobnymi narzędziami. Liczby dostępnych etykiet,
sumaryczne minima, dolne granice braków i status podziału pochodzą wyłącznie
z nullable `dataAvailability` backendu. Brak pomiaru nie staje się zerem;
nieudany podział nie tworzy fikcyjnych liczników ról ani buforów.

Apply używa osobnego `learning_kind=grid-correction-apply-v1`, zamkniętego
payloadu, trwałego parenta i istniejących komend rejestru. Porównania względem
faktycznie przypisanej wersji wykonuje przed zmianami modeli. Przypina dowody
i rewizje, sprawdza currentness i CAS, utrwala deterministyczne receipts kroków
i pokazuje częściowy sukces także w przerwie commit/checkpoint. GET nigdy nie
wykonuje kolejnego kroku. Resume zachowuje tożsamość i dotychczasowe receipts.

Świeży preview dopuszcza nową rewizję tej samej bazy. Inny default bez dowodu
porównania z nim blokuje stary PASS i wskazuje nowy przebieg bez automatycznego
treningu. Zastosowanie nie przelicza wcześniejszych importów i korekt.

## Poprawki po audycie R1

Opus R1: REVISE, P1-1 oraz P2-1–P2-4. W jednej rundzie poprawek:

- P1-1: dokładnie zgodna istniejąca publikacja jest przyjmowana pod blokadą
  rejestru bez mutacji, z trwałym deterministycznym receiptem `already-published`.
  Sprawdzane są evaluationId/evaluationSha256/manifestSha256, kanoniczny JSON
  i checksum publication evidence. Niezgodność blokuje preview oraz wykonanie.
  Własny receipt publish zachowuje pierwszeństwo i idempotencję. Currentness
  pierwotnego raportu nadal jest wymagane przed zmianami modeli.
- Fake Catalogue odrzuca ponowną publikację. Testy odtwarzają ręczną publikację,
  utraconą odpowiedź/checkpoint, nowy apply po obcej rewizji tej samej bazy
  i niezgodne pola/checksum dowodu.
- P2-1: dotychczasowy test PostgreSQL replay/CAS/cancel/resume dotyczył rodzica
  LEARNING, nie APPLY. Szkic apply z artifacts nie zastępował testu w repozytorium.
  Nowy test rodzica APPLY jest regresją T3 po audycie; T4 wykorzysta ten sam test.
- P2-2: `GRID_APPLY_ALREADY_DEFAULT` opisuje fakt już ustawionego kandydata,
  bez sugestii nowego treningu. Panel chowa opt-in i start, zachowując historię
  i możliwość wznowienia wcześniejszego częściowego przebiegu.
- P2-3: drugi start tego samego learning blokuje wyłącznie aktywny parent,
  sprawdzany po JSONB pod registry lock. Failed nie blokuje nowego preview/start
  po obcym CAS. Jawne ryzyko: failed-but-resumable może po resume konkurować
  z nowym apply; CAS zachowuje spójność, lecz historia może zawierać konflikt.
- P2-4: ponowienie resume created/processing/completed zwraca bieżący widok
  bez requeue i nowych kroków; test potwierdza niezmienione ID/checkpoint.

Kontrole po poprawkach: 48/48 backend/API/worker i regresji T2 scoped/composition,
13/13 interakcji nowego panelu, Ruff oraz Admin TypeScript PASS. Następnie dodano
jeden test currentness istniejącej publikacji: 25/25 unit samego apply PASS.
Mypy zmienionego serwisu, scoped ESLint, OpenAPI/SDK i regeneracja mapy PASS.
Publiczny kontrakt HTTP nie wymagał zmiany; receipt pozostaje zadeklarowanym
słownikiem, a nowy rodzaj jest trwałym wynikiem kroku rodzica.
Realny APPLY PostgreSQL: wszystkie trzy warianty PASS, w dwóch ograniczonych
wywołaniach: `first_apply` 1/1,24.84s oraz manual/different_evidence 2/2,40.98s.
Focused R2: PASS, bez P0/P1. Pierwszy wariant potwierdził realne preview/start/get/list, JSONB, blokadę drugiego
klucza, claimy, publish→obca rewizja tej samej bazy→old FAILED→świeży preview
i nowy apply z przyjęciem istniejącej publikacji, replay resume, completed resume,
waitingForJobId, stare korekty/pliki i pin nowego importu w świeżym procesie.
Nie mockowano preview ani control.execute; jawna kontrolowana granica jakości
pozostaje w `_evidence` i historycznym `FixtureInspector`. Dowód leada:
`artifacts/task1122-apply-pg-first.log` i `artifacts/task1122-apply-pg-manual.log`.
Wariant ręcznej zgodnej publikacji potwierdził przyjęcie bez drugiej mutacji;
niezgodny reportId blokował realne preview/start bez utworzenia nowego apply.
Nowy plik PostgreSQL przeszedł Ruff u leada. To regresja T3 po audycie P1-1,
używana następnie w T4 zamiast wcześniejszego szkicu.
Build R1 leada PASS, exit0,17.52s (`artifacts/task1122-admin-r1-build*`).
Raportu audytu R1 nie zmieniano.

Pełne Paths po R1: `artifacts/task1122-audit-paths-r2.txt` (36 ścieżek, w tym
nowy test PostgreSQL APPLY leada). Focused R2 używa węższej listy
`artifacts/task1122-audit-paths-r2-focused.txt`: zmieniony serwis/panel/state,
unit/PG/UI tests, dokumentacja i zachowany raport R1. Metadane T2 i CODE_MAP
pozostają poza listą audytu.

## Wyniki kontroli

| Kontrola | Wynik |
|---|---|
| Nowe interakcje panelu oraz wcześniejszy workspace | 27/27 PASS; w tym11 nowych przypadków |
| Stan poleceń, model-state, kontrakt workspace i jobs | 29/29 PASS po integracji |
| Cały klient API po buildzie i końcowej generacji | 137/137 PASS |
| Apply service + apply/learning worker | 21/21 PASS |
| Apply HTTP, actor i zamknięty kontrakt | 8/8 PASS |
| Admin TypeScript | PASS |
| TypeScript/build klienta | PASS |
| ESLint zmienionych modułów Admina | PASS |
| Ruff check/format modułów backendu i testów | PASS |
| Mypy siedmiu modułów T3 i integracji | PASS, `--follow-imports=silent`, tymczasowy wyjątek wnętrza Torch |
| OpenAPI/SDK generation i generated-client drift check | PASS |
| Regeneracja mapy i `code-map:check` | PASS |
| `npm run docs:check` | PASS |
| Pełny Admin Next build po R1, uruchomiony przez leada | PASS, exit0,17.52s |

### Powtórna kontrola po połączeniu z T2 R1/R2

Wszystkie niżej wymienione kontrole uruchomiono z bieżącego original worktree,
z `PYTHONPATH` wskazującym jego źródła (potwierdzona ścieżka modułu usługi):

- Apply service/API/worker, learning worker, composition parenta oraz
  `test_grid_model_publication_scoped.py`: 40/40 PASS. Chroni to poprawki R1:
  currentness po scoped publish, live-base CAS przy default i zakres aktywacji.
- `integration/test_grid_correction_learning_postgres.py`: 1/1 PASS, 27.94s,
  disposable DB; replay/CAS, zwolnienie slotu, anulowanie i ten sam budżet po resume.
- Interakcje 27/27, stan/kontrakty 29/29, klient po buildzie 137/137 PASS.
- Nowe polskie etykiety `GRID_MODEL_EVALUATION_SCOPE_STALE`, `GRID_LEARNING_BUSY`
  i `GRID_LEARNING_CANCELLATION_PENDING` mają test przyczyny i bezpiecznego działania.
- OpenAPI oraz generated-client drift check, Admin TypeScript, scoped ESLint,
  Ruff i mapa kodu PASS.
- Scoped mypy siedmiu plików PASS z `artifacts/t1121-mypy.toml`,
  `--follow-imports=silent` i osobnym cache `artifacts/t1122-mypy-cache`.
  Lista obejmuje pięć nowych modułów oraz `grid_correction_learning.py` i `schemas/jobs.py`.
- Pełny Next build original: PASS, exit0, 20.52s. Dowody leada:
  `artifacts/task1122-admin-integrated-build.log` i `artifacts/task1122-admin-integrated-build-result.json`.

Lista wejściowa audytu: `artifacts/task1122-audit-paths.txt` (35 ścieżek).
Nie zawiera metadanych record-hash T2 (`CURRENT_STATE`, archiwum i completed1121)
ani generowanych `CODE_MAP*`; nie obejmuje raportów audytu T2 R1/R2.

Interakcje obejmują GET-only entry, restart widoku bez POST, utraconą odpowiedź
start/apply i retry z identycznym kluczem/treścią, opt-in dodatkowej gry,
wyczyszczenie potwierdzenia po zmianie zakresu, konflikt defaultu bez retrainingu,
partial success/resume, spóźnioną odpowiedź oraz minima/infeasible/null.

Backend sprawdzono na odtwarzanych instancjach serwisu: utracone odpowiedzi
publish/default/activate, receipts, CAS obcych zmian, partial success/resume,
assigned checksum/PASS/currentness, wymagane potwierdzenie i discriminator.
API TestClient wymagał zaakceptowanego uruchomienia poza ograniczeniem komunikacji
Windows; środowisko blokowało `asyncio.socketpair` przed kodem aplikacji.

Wstępny szkic leada z `artifacts/task1123-apply-draft.log` był historycznym smoke,
nie testem apply w repozytorium. Zastępuje go regresja T3 po audycie:
`services/api/tests/integration/test_grid_correction_apply_postgres.py`, opisana
w sekcji poprawek R1. T4 wykorzysta tę regresję, bez kopiowania starego szkicu.
Żaden z tych dowodów nie jest rzeczywistym treningiem lub oceną modeli operatora.

Polecenia uruchamiano z timeoutem120s i źródłami nowego worktree w `PYTHONPATH`.
Najważniejsze zestawy:

```powershell
$env:PYTHONPATH = "$PWD/services/api/src;$PWD/services/worker/src;$PWD/services/test_support"
.venv/Scripts/python.exe -m pytest services/api/tests/test_grid_correction_apply.py services/worker/tests/test_grid_correction_apply_handler.py services/worker/tests/test_grid_correction_learning_handler.py -q --basetemp artifacts/pytest-t1122
.venv/Scripts/python.exe -m pytest services/api/tests/test_grid_correction_apply_api.py -q --basetemp artifacts/pytest-t1122-api
# Z apps/admin (CLI zależności jest współdzielone; kod i wewnętrzne pakiety są z tego worktree):
node D:/game_predicotr/node_modules/tsx/dist/cli.mjs --tsconfig tsconfig.json --test test-interactions/grid-correction-learning-panel.test.mjs test-interactions/grid-model-workspace.test.mjs
node D:/game_predicotr/node_modules/typescript/bin/tsc --noEmit
```

## Rzeczywiste ścieżki T3

Nowe moduły:

- `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx`
- `apps/admin/src/features/model-quality/grid-correction-learning-state.ts`
- `apps/admin/src/features/model-quality/grid-correction-apply-panel.tsx`
- `apps/admin/src/features/model-quality/grid-correction-learning.css`
- `services/api/src/game_predictor_api/api/grid_correction_apply.py`
- `services/api/src/game_predictor_api/application/grid_correction_apply.py`
- `services/api/src/game_predictor_api/schemas/grid_correction_apply.py`
- `services/worker/src/game_predictor_worker/images/grid_correction_apply_handler.py`
- `services/worker/src/game_predictor_worker/images/grid_correction_workflow_handler.py`

Nowe testy:

- `apps/admin/test/grid-correction-learning-state.test.mjs`
- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`
- `packages/admin-api-client/test/grid-correction-apply-request.test.mjs`
- `services/api/tests/test_grid_correction_apply.py`
- `services/api/tests/test_grid_correction_apply_api.py`
- `services/worker/tests/test_grid_correction_apply_handler.py`
- `services/api/tests/integration/test_grid_correction_apply_postgres.py` — regresja T3 po R1, autor lead

Zmodyfikowane istniejące pliki:

- `apps/admin/src/app/globals.css`
- `apps/admin/src/features/jobs/job-state.ts`
- `apps/admin/src/features/model-quality/grid-model-state.ts`
- `apps/admin/src/features/model-quality/grid-model-workspace.tsx`
- `apps/admin/test/job-state.test.mjs`
- `apps/admin/test/grid-model-state.test.mjs`
- `apps/admin/test-interactions/grid-model-workspace.test.mjs`
- `packages/admin-api-client/openapi/openapi.json`
- `packages/admin-api-client/src/generated/index.ts`
- `packages/admin-api-client/src/generated/sdk.gen.ts`
- `packages/admin-api-client/src/generated/types.gen.ts`
- `packages/admin-api-client/src/index.ts`
- `services/api/src/game_predictor_api/application/grid_correction_learning.py` — filtry kind
- `services/api/src/game_predictor_api/main.py`
- `services/api/src/game_predictor_api/schemas/jobs.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `ai_docs/architecture/VISION_LAB.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/tasks/1122-grid-correction-learning-panel.md`

Ten raport jest dodatkowym nowym plikiem dokumentacji. Różnicę T3 należy liczyć
od commita T2 `7801ea47`, wyłączając metadane record-hash T2 i generowane mapy
z wejściowej listy audytu (mapy pozostają częścią końcowego commita T3).

## Niewykonane

Audyt T3 R2 zakończony PASS. Task-close, commity i końcowy odbiór T4 prowadzi lead. Nie uruchamiano usług,
rzeczywistego treningu/GPU, migracji operatora, rzeczywistego apply/rollback ani
merge/push. Pełny projektowy mypy pozostaje ograniczeniem T4 (zewnętrzny graf
Torch przekraczał wcześniejszy limit); nie przedstawiono go jako PASS. Lead
spróbował również szerokiego first-party mypy z tym samym tymczasowym wyjątkiem
Torch: limit 110s, bez PASS. 18 diagnostyk dotyczy 8 plików niezmienionych od
`c65823fd`, w większości granicy Module=Any po pominięciu Torch i dwóch innych
starszych modułów. Globalna konfiguracja nie została zmieniona. Dowody:
`artifacts/t1123-first-party-mypy*.log/json`, `artifacts/t1123-typecheck-limitations.json`.

## Dyspozycja po R2

Brak otwartych P0/P1. P2-3/P2-5/P2-6 R2 przechodzą do TASK-1123: guard resume
przy innym aktywnym apply, GET historii mimo obcej publikacji i adopcja w GET
dopiero po wcześniejszych porównaniach. T3 kod po PASS nie był ponownie zmieniany.
