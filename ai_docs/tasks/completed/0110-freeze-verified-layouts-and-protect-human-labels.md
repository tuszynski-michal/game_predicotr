---
title: Freeze verified layouts and protect human labels
status: done
last_updated: 2026-07-29
---

# TASK-0110 — Freeze verified layouts and protect human labels

## Status

`done`

## Goal

Pozwolić właścicielowi jawnie zamrozić kompletną kohortę zweryfikowanych
plansz jako niezmienny, checksum-bound eksport, który chroni dokładne decyzje
człowieka i stanowi jedyne dopuszczalne wejście późniejszego retrainingu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- dodać licznik zweryfikowanych plansz per gra i import job,
- dodać jawną komendę zamrożenia bez automatycznego progu,
- utworzyć wersjonowany rekord i niezmienny artefakt JSON z dokładnymi
  decyzjami accepted/corrected,
- zachować numer sekwencji, rewizję decyzji i geometrii, źródło, planszę,
  dokładnie 15 `cropSampleId`, checksum i symboli oraz pipeline provenance,
- zapewnić idempotentny retry dla identycznego stanu i nową wersję po zmianie
  dowolnej decyzji,
- nie włączać treningu ani publikacji jako skutku ubocznego eksportu,
- zdefiniować fail-closed granicę, w której późniejsza inferencja może zmieniać
  sugestie wyłącznie nierozwiązanych plansz,
- dodać lokalny panel zamrożenia i historię wersji,
- przygotować kontrakt eksportu jako jedyne dopuszczalne wejście późniejszego
  retrainingu i ręcznie zweryfikowanego stagingu.

## Out of scope

- faktyczne trenowanie lub promowanie nowej wersji modelu w chwili zamrożenia,
- automatyczne uruchomienie operacji po osiągnięciu 1000/3000 plansz,
- automatyczna publikacja datasetu,
- zmiana `massImportAllowed`,
- masowy import zdjęć,
- ręczne testy ekranu — odbiór po TASK-0111,
- hosting i zdalny dostęp — M8.7.

## Acceptance criteria

- [x] eksport zawiera wyłącznie kompletne accepted/corrected i dokładnie 15
  komórek na planszę,
- [x] odrzucone i oczekujące elementy nie tworzą próbek, ale są raportowane w
  licznikach,
- [x] identyczny stan gry i import joba zwraca tę samą wersję oraz checksum,
- [x] zmiana decyzji, geometrii albo cropu tworzy nową wersję,
- [x] artefakt nie przechowuje binarnych obrazów ani ścieżek absolutnych,
- [x] accepted/corrected pozostają związane z zatwierdzonym `cropSampleId` i
  nie mogą zostać nadpisane przez późniejszą predykcję,
- [x] zamrożenie nie uruchamia retrainingu, inferencji ani publikacji,
- [x] panel wymaga jawnego potwierdzenia i pokazuje historię wersji,
- [x] OpenAPI, generowany klient, migracja, testy, lint, typecheck i build
  przechodzą.

## Technical notes

- Eksport jest wersjonowany per `(game_id, import_job_id)`.
- `input_state_sha256` jest liczone z kanonicznych rewizji i referencji
  zatwierdzonych plansz; `payload_sha256` z finalnych bajtów JSON.
- Artefakt powstaje pod zarządzanym `<artifact-root>/data`, a baza przechowuje
  wyłącznie względną ścieżkę i metadane.
- Puste kohorty są odrzucane. Oczekujące elementy nie blokują zamrożenia już
  rozwiązanej części, ponieważ właściciel może jawnie zamrażać iteracje po
  1000/3000 planszach; blokują natomiast późniejszą publikację całego zakresu.
- Retraining i ręcznie zweryfikowany staging pozostają osobnymi, jawnymi
  komendami. Ten task dostarcza ich niezmienne wejście i ochronę danych, ale nie
  uruchamia ciężkiej operacji.
- Każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Expected files

- `services/api/alembic/versions/*_image_verified_cohort_exports.py`
- `services/api/src/game_predictor_api/domain/image_review_cohorts.py`
- `services/api/src/game_predictor_api/application/image_review_cohorts.py`
- `services/api/src/game_predictor_api/storage/image_review_cohort_repository.py`
- `services/api/src/game_predictor_api/storage/models.py`
- `services/api/src/game_predictor_api/schemas/image_review_cohorts.py`
- `services/api/src/game_predictor_api/api/image_review_cohorts.py`
- `packages/admin-api-client/*`
- `apps/admin/src/features/operational-reviews/*`
- `services/api/tests/test_image_review_cohorts.py`
- `apps/admin/test/operational-review-*.test.mjs`
- dokumentacja procesu i architektury.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests/test_image_review_cohorts.py -q
.\.venv\Scripts\python.exe -m ruff check <changed-python-files>
.\.venv\Scripts\python.exe -m mypy <changed-python-modules>
node_modules\.bin\tsc.cmd -p packages/admin-api-client/tsconfig.json --noEmit
node_modules\.bin\tsc.cmd -p apps/admin/tsconfig.json --noEmit
```

## Risks / open questions

- Pełny retraining może być kosztowny i pozostaje osobnym, jawnym przebiegiem
  po zebraniu wystarczającej kohorty.
- Publikacja ręcznego zakresu nadal wymaga ciągłości, braku duplikatów i
  standardowej walidacji; sam eksport tych warunków nie obchodzi.

## Outcome

### Changed

- Dodano migrację `0020_verified_cohorts`, model wersjonowanego eksportu i
  unikalność stanu oraz wersji per gra/import job.
- Zamrożenie blokuje kontekst, waliduje pełny stan kolejki i materializuje
  kanoniczny `verified-image-review-cohort-v1` pod zarządzanym storage.
- Payload zawiera kompletne accepted/corrected 15/15 z dokładnym numerem,
  rewizją, geometrią, źródłem, planszą, cropami, checksumami i etykietami.
  Pending/rejected są częścią checksumy stanu i liczników, ale nie próbek.
- Exact retry ponownie weryfikuje plik po SHA-256. Zmiana dowolnego statusu lub
  rewizji tworzy nową wersję bez mutacji wcześniejszego artefaktu.
- Dodano POST/GET Admin API, wygenerowany klient oraz kompaktowy panel z
  licznikiem, ostatnią wersją, historią i osobnym dialogiem potwierdzenia.
- Zamrożenie nie ma ścieżki uruchamiającej model, inferencję lub publikację.
  Istniejący staging accepted/corrected pozostaje osobną granicą standardowej
  walidacji.

### Verification results

- `195 passed, 16 skipped` w pełnym zestawie `services/api/tests`.
- Fizyczny PostgreSQL: pełny upgrade → downgrade → upgrade do
  `0020_verified_cohorts`, `1 passed`.
- Klient TypeScript: `16 passed`; panel: `92 passed`.
- Ruff dla zmienionego zakresu i pełny lint Python przeszły.
- mypy: `233 source files`, bez błędów.
- TypeScript strict klienta i panelu, ESLint zmienionego zakresu oraz Prettier
  przeszły.
- OpenAPI i wygenerowany klient są aktualne.
- Produkcyjny build Next.js przeszedł.

### Not completed

- Nie wykonano faktycznego retrainingu ani publikacji — są to osobne jawne
  operacje i zamrożenie nie może ich uruchamiać.
- Zgodnie z decyzją właściciela ręczny odbiór UI pozostaje odroczony do
  TASK-0111.

### Documentation updates

- Zaktualizowano Data Model, API Contract, System Architecture, Decision Log
  (D-090), plan M6.5 i CURRENT_STATE.

### Recommended next task

- `TASK-0111 — Verification workbench scale and usability acceptance`.
