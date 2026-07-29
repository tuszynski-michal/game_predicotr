---
title: Review geometry correction and immutable recrop
status: done
last_updated: 2026-07-29
---

# TASK-0109 — Review geometry correction and immutable recrop

## Status

`done`

## Goal

Pozwolić operatorowi skorygować cztery narożniki jednej planszy i zapisać nową,
niezmienną rewizję geometrii, wyprostowanej planszy oraz 15 cropów bez
przenoszenia wcześniejszych etykiet.

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

- dodać migrację i append-only model rewizji geometrii wraz z 15 nowymi
  obserwacjami cropów,
- dodać job-local endpoint tworzenia geometry revision z expected geometry i
  resolution revision oraz UUID idempotencji,
- przyjmować wyłącznie cztery narożniki w przestrzeni oryginalnego obrazu,
- zweryfikować kolejność, wypukłość, pole i granice narożników,
- wygenerować nową wyprostowaną planszę oraz dokładnie 15 cropów przez istniejący
  adapter obrazu, zapisać pliki content-addressed i policzyć checksumy,
- atomowo przełączyć review item na nowe cropy, status pending i usunąć wyłącznie
  jego nieopublikowany staging,
- zachować wcześniejsze decyzje, pliki i rewizje jako audyt,
- dodać generowany kontrakt TypeScript,
- dodać modal `Edytuj siatkę` z czterema przeciąganymi narożnikami, ukośną
  siatką 5 × 3, podglądem wyprostowanej planszy i 15 cropów,
- po zapisie przeładować dokładnie nowe cropy i zresetować draft symboli,
- dodać testy domeny, repozytorium/API, recropu i panelu.

## Out of scope

- automatyczne propagowanie geometrii na inne plansze,
- zmiana aktywnego profilu detekcji lub pipeline fingerprint,
- zamrożenie kohorty i retraining — TASK-0110,
- ręczne testy ekranu — odbiór po TASK-0111,
- hosting i zdalny dostęp — M8.7.

## Acceptance criteria

- [x] korekta jednego review item nie zmienia geometrii innego,
- [x] request nie przyjmuje ścieżek ani gotowych plików od klienta,
- [x] nieważne narożniki, stale revision i reuse UUID z innym payloadem są
  kontrolowanymi konfliktami,
- [x] zapis tworzy nowy board checksum i dokładnie 15 nowych crop checksum oraz
  `cropSampleId`,
- [x] wcześniejsza geometria, cropy i eventy decyzji pozostają niezmienione,
- [x] poprzednia etykieta nie jest kopiowana do nowego `cropSampleId`,
- [x] item po korekcie jest pending, nie ma staging row i pokazuje nowe assety,
- [x] anulowanie modala nie zapisuje pliku ani rewizji,
- [x] panel pokazuje narożniki, ukośną siatkę, wyprostowaną planszę i 15 cropów,
- [x] nowe zachowanie przechodzi testy, lint, typecheck, formatowanie i build.

## Expected files

- `services/api/alembic/versions/*_image_review_geometry_revisions.py`
- `services/api/src/game_predictor_api/domain/image_reviews.py`
- `services/api/src/game_predictor_api/application/image_reviews.py`
- `services/api/src/game_predictor_api/storage/image_review_repository.py`
- `services/api/src/game_predictor_api/schemas/image_reviews.py`
- `services/api/src/game_predictor_api/api/image_reviews.py`
- `services/worker/src/game_predictor_worker/images/*`
- `packages/admin-api-client/*`
- `apps/admin/src/features/operational-reviews/*`
- `apps/admin/test/operational-review-*.test.mjs`
- dokumentacja procesu.

## Assumptions

- kolejność narożników to top-left, top-right, bottom-right, bottom-left,
- preview klienta może używać transformacji CSS/canvas, ale zapisane pliki
  zawsze generuje backend z tego samego kontraktu,
- nowa rewizja nie uruchamia pełnej inferencji symboli; komórki wracają do
  pending bez etykiety człowieka, a sugestie mogą pozostać puste do późniejszego
  przeliczenia,
- pliki rewizji powstają pod zarządzanym `<artifact-root>/data`, nigdy w
  katalogu wskazanym przez klienta,
- każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Outcome

- Dodano migrację `0019_review_geometry`, bieżący wskaźnik rewizji planszy oraz
  append-only rekordy ręcznej geometrii z UUID idempotencji, kanonicznym
  checksumem komendy, planszą i dokładnie 15 cropami.
- Adapter `manual-review-geometry-v1` weryfikuje checksum źródła, granice i quad,
  wykorzystuje zachowany cropper v2, generuje preview bez zapisu oraz
  content-addressed PNG przy zatwierdzeniu.
- API udostępnia job-local preview i zapis z expected geometry/resolution
  revision. Zapis atomowo ponownie otwiera review, usuwa tylko jego staging,
  zachowuje eventy i nie przenosi labeli człowieka na nowe `cropSampleId`.
- Wygenerowany klient TypeScript i panel zawierają modal z czterema
  przeciąganymi narożnikami, ukośną siatką 5 × 3, planszą 500 × 300 i podglądem
  15 cropów. Zapis wymaga aktualnego preview, a anulowanie nie wywołuje mutacji.
- Walidacja: 190 testów Python (`16 skipped` środowiskowo), dodatkowy fizyczny
  test PostgreSQL, 15 testów klienta, 91 testów panelu, Ruff, mypy, TypeScript,
  ESLint, Prettier, OpenAPI/generated-client check i produkcyjny build Next.js.
- Zgodnie z decyzją właściciela nie wykonano ręcznych testów UI; odbiór całego
  stanowiska nastąpi po TASK-0111.
