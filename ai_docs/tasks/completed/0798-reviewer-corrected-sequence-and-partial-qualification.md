---
title: TASK-0798 — Reviewer: rozstrzygnięcie „corrected” ze zmianą numeru sekwencji planszy wirtualnej i kwalifikacja częściowa w edytorze operacyjnym
status: done
last_updated: 2026-10-01
---

# TASK-0798 — Reviewer: rozstrzygnięcie „corrected” ze zmianą numeru sekwencji planszy wirtualnej i kwalifikacja częściowa w edytorze operacyjnym

## Status

`done` (audyt pominięty — decyzja operatora 2026-10-01; commit v1.7.143; wdrożenie = restart API i Reviewera po `reviewer:build`)

## Goal

Rozstrzygnięcie Reviewera `corrected`, które zmienia numer sekwencji planszy
wirtualnej, kończy się poprawnym zapisem albo jawnym błędem 4xx (nigdy
500), a edytor operacyjny Reviewera pozwala zapisać korektę geometrii
planszy z kwalifikacją częściową.

## Context

Następstwa TASK-0796 (D-467 S6, 2026-10-01), zgłoszone przez implementera
bez naprawy:

1. Rozstrzygnięcie `POST /api/v1/admin/image-review-items/{id}/resolution`
   ze statusem `corrected` i innym `sequenceNumber` dla planszy
   `virtual_source` prawdopodobnie rzuca `ValueError` „Pinned source
   geometry slot does not own the current sequence” (walidacja zgodności
   slotu geometrii źródła z numerem sekwencji) i kończy się odpowiedzią
   500. Hipoteza do potwierdzenia testem; przed konwersją (TASK-0791)
   dotyczyło to tylko plansz wirtualnych, dziś wszystkich.
2. Edytor operacyjny Reviewera
   (`apps/reviewer/src/features/operational-reviews/operational-review-geometry-editor.tsx`,
   `operational-review-actions.ts`) nie wysyła kwalifikacji częściowej;
   od TASK-0796 korekta deleguje do `VirtualGridGeometryService`, który
   dla planszy z kwalifikacją częściową zwraca
   `IMAGE_GRID_REVIEW_QUALIFICATION_REQUIRED`, więc takiej planszy nie da
   się poprawić w Reviewerze (obok istnieje pełna korekta wirtualna
   `board-geometry-correction-target.ts` z kwalifikacją).

Baza operatora: `0138`, usługi na roli `game_predictor_app`.

## Dependencies / entry conditions

- Fakt: HEAD `v1.7.135` (TASK-0797).
- Niewiadoma (rozstrzyga zadanie testem): czy zmiana numeru sekwencji
  planszy wirtualnej ma być dozwolona. Numer sekwencji slotu wynika z
  geometrii źródła (`sequence_range_start + position_index`), więc zmiana
  numeru jednej planszy bez zmiany zakresu źródła jest sprzeczna z danymi.
  Zalecenie: odmowa jawnym kodem 409 z komunikatem wskazującym właściwą
  drogę (korekta zakresu/pozycji w kolejce siatek), o ile wymagania
  (`requirements/IMAGE_INGESTION.md`, D-462) nie mówią inaczej — jeśli
  mówią, zaimplementować zgodnie z nimi i opisać.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (warunkowo). Audyt: zawieszony
(decyzja operatora 2026-10-01).

## Relevant docs

- `AGENTS.md`, `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md` (rozstrzygnięcia przeglądu,
  numer sekwencji), `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/process/DECISION_LOG.md` (D-449 kwalifikacja częściowa, D-462)
- `ai_docs/tasks/completed/0796-remove-v19-paths-and-narrow-asset-enums.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`

## Scope

- Reprodukcja punktu 1 testem PG przez `create_app` na roli aplikacyjnej;
  naprawa według rozstrzygnięcia z Dependencies: brak 500, transakcja
  wycofana w całości przy odmowie, kod błędu w `ERROR_RESPONSES`, Reviewer
  pokazuje komunikat (toast) i nie traci stanu formularza.
- Punkt 2: edytor operacyjny wysyła kwalifikację częściową (te same pola
  i walidacja co `board-geometry-correction-target.ts`; wspólny kod
  zamiast kopii), podgląd pokazuje komórki niedostępne, zapis tworzy
  rewizję wirtualną z kwalifikacją; kontrakt API pionem, jeśli wymaga
  zmiany (OpenAPI, klient, wrapper, test żądania), allowlista proxy bez
  nowych tras.
- Testy: PG (oba punkty), testy Reviewera (`test`, `test:geometry`),
  typecheck i lint.
- Dokumentacja: `API_CONTRACT.md` (kod błędu), `IMAGE_INGESTION.md` jeśli
  doprecyzowuje regułę numeru sekwencji, Outcome.

## Out of scope

- Zmiana modelu sekwencji i geometrii źródła; bramka kompletności zdjęcia
  (plan `GRID_ENGINE_V3_HYBRID_EXECUTION_PLAN.md`).

## Acceptance criteria

- [ ] `corrected` ze zmianą numeru sekwencji planszy wirtualnej: brak 500;
      zachowanie zgodne z rozstrzygnięciem i opisane; test PG.
- [ ] Korekta geometrii planszy częściowej z edytora operacyjnego zapisuje
      rewizję wirtualną z kwalifikacją; test PG i test interakcji.
- [ ] ruff, mypy --strict, pytest, testy TS zielone poza znanymi
      niepowodzeniami HEAD; `--collect-only` OK.

## Verification

```powershell
$env:PYTHONPATH = "services/worker/src;services/api/src"
$env:GAME_PREDICTOR_RUN_POSTGRES_TESTS = '1'; $env:GAME_PREDICTOR_PG_TEST_ROLE = 'application'
.\.venv\Scripts\python.exe -m pytest services/api/tests/integration/test_reviewer_operational_geometry_postgres.py -p no:cacheprovider --basetemp C:\Users\tuszy\AppData\Local\Temp\t798pg
npm run test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
```

## Risks / open questions

- Reguła numeru sekwencji (odmowa vs. zmiana zakresu źródła) — patrz
  Dependencies.

## Outcome

Wypełnia agent po pracy.

Implementacja gotowa, bez commitu (commit i wdrożenie robi orkiestrator);
audyt zawieszony, przejrzałem własny diff. **Bez migracji**: wdrożenie to
restart API i Reviewera (oraz `npm run reviewer:build`).

**Reprodukcja punktu 1.** Test PG przez `create_app` na roli aplikacyjnej
odtworzył problem. Plansza po rozstrzygnięciu slotu odroczonego, `corrected` z
`sequenceNumber = suggested + 7`, dała **500**. Ślad: `save_resolution` →
`synchronize_after_board_resolution` → `_synchronize` →
`pinned_visibility_geometry` → `ValueError: Pinned source geometry slot does
not own the current sequence`. Wyjątek padał po roszczeniu kanonicznym i
zdarzeniu, więc bez obsługi kończył się 500. Na bazie operatora (tylko odczyt):
0 rozstrzygniętych itemów z numerem różnym od numeru planszy i 0 plansz
`virtual_source`, których slot geometrii źródła nie zgadza się z numerem.

**Rozstrzygnięcie reguły.** Numer zostaje przypięty, zmiana jest odrzucana
jawnym 409. Uzasadnienie:

- `IMAGE_INGESTION.md` i D-198 dopuszczają ręczną korektę numeru, ale sprzed
  D-467 S6. Dziś numer planszy wirtualnej wynika ze slotu geometrii źródła
  (początek zakresu `seq_*` plus pozycja), a komórki weryfikacji symboli są
  kluczowane numerem (D-462).
- Próba dopuszczenia (sprawdzenie slotu po numerze planszy zamiast numeru z
  decyzji) natychmiast trafiła na `UniqueViolation (game_id, review_item_id,
  cell_index)`. Komórki tego samego właściciela musiałyby się przenieść między
  numerami razem z decyzjami — to zmiana modelu sekwencji i komórek, poza
  zakresem.
- D-198 dostał notę „Zmiana 2026-10-02 (TASK-0798)”, a `IMAGE_INGESTION.md`
  doprecyzowanie.

### Changed

- `storage/image_review_repository.py`: `_require_source_attested_sequence`
  w `save_resolution`, po blokadach i ponownej walidacji, przed pierwszym
  zapisem. Dla `accepted`/`corrected` planszy `virtual_source` z innym numerem
  zwraca `ImageReviewConflictError("IMAGE_REVIEW_SEQUENCE_PINNED_BY_SOURCE")`
  (409, `details.boardSequenceNumber`/`requestedSequenceNumber`); żądanie
  wycofuje się w całości. Sprawdzenie slotu w write-through komórek
  pozostało bez zmian.
- Kontrakt pionem (backend, OpenAPI, klient, test żądania; wrapper bez zmian,
  bo typy przechodzą):
  - `OperationalImageReviewGeometryPreviewCommand` i `...Command` mają
    opcjonalne `geometryQualification` i narożniki ze znakiem
    (`ManualSourceGeometryPoint`). Ujemna współrzędna bez `pending_partial`
    daje 422. Granice edycji i obowiązkową deklarację częściowości sprawdza
    domena.
  - `OperationalImageReviewItemResponse` ma `geometryQualification`,
    `sourceWidth` i `sourceHeight`.
  - `OperationalImageReviewGeometryRevisionResponse` ma `geometryQualification`
    i narożniki ze znakiem.
  - Kwalifikacja przechodzi przez trasę, `OperationalImageReviewService`
    i `VirtualGridGeometryService.preview_review_item`/`save_review_item`.
  - Allowlista proxy bez nowych tras.
- Reviewer:
  - Edytor operacyjny to teraz okno dialogowe ze wspólnym
    `BoardGeometryCorrectionEditor` (ten sam edytor co w kolejce korekty i dla
    slotu odroczonego). Używa nowego celu `operationalBoardGeometryTarget`
    (`board-geometry-correction-target.ts`) na trasach operacyjnych.
  - Wspólna funkcja `correctionGeometryQualification` (używają jej też plansze
    zgłoszone) zastąpiła kopię. Edytor ma te same flagi „Niepełna plansza”,
    pola niedostępne i walidację; plansza z kwalifikacją zawsze ją wysyła.
  - Narożniki planszy częściowej ze znakiem: `parseGeometryCorners`.
  - Podgląd oznacza pola niedostępne („Crop N — poza zdjęciem”, przygaszone).
    To dotyczy też kolejki korekty.
  - Odmowa 409 decyzji pokazuje polski komunikat i nie przeładowuje formularza
    (`isRevisionConflict = false`, szkic zostaje).
- Testy:
  - PG w `test_reviewer_operational_geometry_postgres.py`: odmowa
    przeniesienia numeru z pełnym wycofaniem oraz korekta planszy w częściową
    z kwalifikacją, manifestem i 15 komórkami, a potem 422 bez kwalifikacji.
  - `test_image_batch_store`: test wyścigu przepisany na nową regułę
    (wygrywa plansza z numerem z nazwy, druga dostaje odmowę i zostaje
    `pending`) oraz nowy test sekwencyjny ścieżki
    `canonical_sequence_claim_lost`, który zachowuje jej pokrycie.
  - Reviewer: nowe `test/operational-board-geometry-target.test.mjs` (5) i
    `test-interactions/operational-review-geometry-editor.test.mjs` (2);
    zaktualizowany test kontraktu źródeł.
  - API: aktualizacja `test_openapi_contract` (test kolejki operacyjnej był
    nieaktualny od TASK-0796) i fixture w
    `test_image_symbol_review_virtual_source`.

### Verification results

- `pytest services/api/tests --collect-only`: 1909, OK.
- ruff i `ruff format --check` czyste dla 10 plików; `mypy --strict` dla 6
  zmienionych modułów: błędy tylko w znanych plikach HEAD; `git diff --check`
  czysty.
- API unit, sekwencyjnie po 6 plików: 1704 passed, 4 skipped, 19 failed. Same
  znane z HEAD: guard 7, reviews 6, virtual_grid partial preview 2,
  `test_image_symbol_reviews_api` 1, lateral[browser] 1, migration_baseline 1,
  `test_openapi_contract::grid_review` 1.
- PG na roli aplikacyjnej (`GAME_PREDICTOR_PG_TEST_ROLE=application`),
  pojedynczo; bazy i role testowe posprzątane:

  | Plik | Wynik |
  |---|---|
  | `test_reviewer_operational_geometry_postgres` | 4/4 |
  | `test_image_batch_store` | 16/16 |
  | `test_reviewer_session_application_role_postgres` | 2/2 |
  | `test_virtual_deferred_resolution_postgres` | 9/9 |
  | `test_game_storage_routing_postgres` (węzły 9–12) | 4/4 |

  Pierwszy przebieg `test_image_batch_store` dał 14/15: stary test wyścigu
  padł na nowej regule, został przepisany, a nowy test sekwencyjny doszedł.
- TS:

  | Pakiet | Wynik |
  |---|---|
  | Reviewer `test` | 199/199 |
  | Reviewer `test:geometry` | 9/9 |
  | Reviewer typecheck i lint | OK |
  | Admin typecheck | OK |
  | api-client `test` | 73/73 |
  | `check:generated` i `export_admin_openapi.py --check` | OK |
  | prettier (zmienione pliki) | OK |

- Worker bez zmian w kodzie — nie uruchamiany.

### Not completed

- Przeniesienie planszy z jej komórkami i decyzjami pod inny numer (zmiana
  modelu D-462). Pole numeru i przycisk „Zezwól na korektę numeru” w
  Reviewerze zostały; odmowa tłumaczy właściwą drogę. Usunięcie przycisku to
  decyzja operatora.
- Znaleziony, nie naprawiony błąd, wcześniejszy niż to zadanie i wspólny ze
  ścieżką Admina: `image_symbol_review_states.cell_count` liczy tylko backfill
  i rekonsyliację, a zapis geometrii odejmuje deltę dostępności. W grze, której
  stan ma `cell_count = 0` (nowa gra przed finalizacją backfillu), zmiana
  planszy pełnej w częściową łamie CHECK (`cell_count = -6`, 500). Test PG
  emuluje finalizację backfillu (`_finalize_cell_count`). W 777 licznik jest
  duży, więc to nie występuje.
- `CURRENT_STATE.md` zostawiony orkiestratorowi.

### Documentation updates

- `API_CONTRACT.md`: kod `IMAGE_REVIEW_SEQUENCE_PINNED_BY_SOURCE`, kwalifikacja
  i narożniki ze znakiem w korekcie operacyjnej, nowe pola itemu i rewizji.
- `IMAGE_INGESTION.md`: reguła numeru planszy wirtualnej.
- `DECISION_LOG.md`: nota pod D-198. Numeru nowej decyzji nie nadawałem —
  inne sesje równolegle zajmują numery D.
- `REMOTE_REVIEWER_THREAT_MODEL.md`: nota o kwalifikacji i narożnikach ze
  znakiem przez tunel.

### Recommended next task

- Licznik `cell_count` przy zmianie dostępności planszy (inkrementacja przy
  zapisie nowych komórek albo przeliczenie dla wybranych sekwencji zamiast
  delty względem niepoliczonego stanu).
- Decyzja operatora o przycisku korekty numeru w Reviewerze (usunąć albo
  zastąpić skrótem do odrzucenia planszy).
