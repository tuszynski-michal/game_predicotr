---
title: Automatyczne siatki widocznych plansz z niepełną ramką
status: done
last_updated: 2026-09-15
---

# TASK-0549 — Automatyczne siatki widocznych plansz z niepełną ramką

## Status

`done`

## Goal

Silnik ma zachować jednoznacznie odtworzoną siatkę kompletnej planszy z
uciętą albo zasłoniętą ramką, skierować ją do `Do walidacji` i pozostawić
ręczne wyznaczanie geometrii wyłącznie dla slotów bez bezpiecznego wyniku.

## Context

Źródła `seq_61741-61749.jpg`, `seq_61651-61659.jpg` i
`seq_61786-61794.jpg` mają mocne dopasowanie całej strony i kompletne siatki
symboli, ale osłabione czerwone obramowanie pierwszej planszy. Najnowszy
preflight odrzuca pierwsze źródło przez
`PAGE_GEOMETRY_RED_EDGE_COVERAGE_INSUFFICIENT`: 164 inliery, ratio `0,4282`,
p95 `1,7877 px`, średnie pokrycie `0,8864`, minimum `0,3525`. Lokalny refiner
na tym samym obrazie odzyskuje siatkę pierwszego slotu z 12 wiarygodnymi
symbolami i p95 `3,2145 px`.

Obecna ścieżka v4 zachowuje kandydaturę wyłącznie wtedy, gdy quad wychodzi
poza boczną krawędź bitmapy. Nie zachowuje mocnego dopasowania znajdującego
się wewnątrz obrazu, jeśli tylko część ramki jest niewidoczna. TASK-0537
poprawił projekcję już istniejących propozycji, lecz jawnie nie zmieniał
detektora ani progów.

## Dependencies / entry conditions

- Aktywny Structured Geometry v3 i jawny wariant
  `structured_lattice_v4_partial_sides` pozostają podstawą.
- Istniejące snapshoty lateral v1/v2 i ich joby muszą odtwarzać stare
  zachowanie bez ponownej interpretacji.
- Załączone JPEG-i są realnymi, lokalnymi przypadkami regresji; testy nie
  zapisują ani nie modyfikują katalogu `D:\777`.

## Recommended execution

`gpt-5.6-sol` z reasoning `high`: zmiana przecina wersjonowany snapshot,
rejestrację strony, lokalny refiner, projekcję kolejki i OpenAPI. Dodatkowy
review modelem `gpt-6-astra` z reasoning `high` jest wymagany tylko wtedy,
gdy implementacja osłabi istniejące bramki homografii, kolejności albo
bezpieczeństwa zawartości.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/tasks/completed/0537-route-automatic-partial-grids-to-review.md`

## Scope

- Dodać nową, checksumowaną wersję polityki wariantu v4, która rozpoznaje
  mocne dopasowanie strony z maksymalnie trzema słabiej widocznymi ramkami.
- Zachować kandydaturę strony, jeśli homografia, kolejność, pełne podparcie
  pionowe i średnie pokrycie pozostają bezpieczne, a pozostałe ramki stanowią
  niezależny dowód układu.
- Dla każdego słabego slotu uruchomić istniejący refiner symboli. Poprawny
  `symbolGridQuad` ma dostać automatyczną propozycję kompletnej geometrii,
  wykluczenie z uczenia zwykłej geometrii i obowiązek potwierdzenia.
- Zwykłe, mocne sloty tego samego zdjęcia pozostają automatyczne. Slot bez
  bezpiecznej lokalnej siatki pozostaje `Do poprawy`.
- Rozszerzyć kolejkę, API i UI o propozycję kompletnej siatki z niepełną
  ramką oraz zachować dotychczasową propozycję `pending_partial`.
- Dodać test regresyjny oparty na parametrach trzech zgłoszonych źródeł oraz
  uaktualnić kontrakt OpenAPI i dokumentację.

## Out of scope

- Automatyczne zatwierdzanie albo renderowanie cropów przed decyzją człowieka.
- Zmiana standardowego wariantu v3, progów ORB/RANSAC i obsługi ucięcia
  pionowego.
- Ponowne uruchamianie istniejących jobów lub modyfikowanie danych użytkownika.
- Uczenie modelu z tych propozycji przed ręcznym potwierdzeniem.

## Acceptance criteria

- [x] Każde z trzech zgłoszonych źródeł zachowuje kandydaturę strony, a slot
      z osłabioną ramką dostaje automatyczną siatkę do walidacji.
- [x] Dla `seq_61741-61749.jpg` slot 0 nie wymaga ręcznego rysowania, jeśli
      lokalny refiner ponownie uzyska obecny bezpieczny wynik.
- [x] Slot z kandydaturą, ale bez poprawnej siatki lokalnej nadal trafia do
      `Do poprawy` bez syntetycznej geometrii.
- [x] Ucięcie góry/dół, brak całej planszy, zła kolejność, overlap, słaba
      homografia i zbyt mały globalny dowód pozostają fail-closed.
- [x] Stare snapshoty v1/v2 oraz stare artefakty odtwarzają się bez zmiany.
- [x] Nowe snapshoty, propozycje i odpowiedzi API są walidowane przez OpenAPI,
      klient wygenerowany oraz testy backendu i Reviewera.

## Technical notes

Nowa polityka v3 rozszerza ten sam wariant per-run. Nie zmienia istniejących
jobów, ponieważ snapshot, checksum i fingerprint pipeline'u nadal wiążą
zachowanie. Proponowane bramki ramki: co najmniej `0,65` dla automatycznej
akceptacji pojedynczego slotu, co najmniej `0,30` dla slotu kierowanego do
review, średnia strony co najmniej `0,70`, najwyżej trzy słabe sloty. Każda
propozycja nadal wymaga obecnych progów dopasowania, poprawnego uporządkowania
quadów i lokalnego `contentSafety=passed`.

Kompletna plansza z wadą ramki nie może udawać `pending_partial`. Otrzyma
osobne `automaticFrameProposal` z kwalifikacją `complete`, pustą maską,
`excludeFromGeometryTraining=true` i powodem `manual_exclusion`. Stara
`automaticPartialProposal` zachowuje maskę brakujących komórek. Oba rodzaje
propozycji udostępniają czteropunktowy `symbolGridQuad` jako nakładkę i są
liczone jako `needs_validation`; ręczny szablon powstaje tylko bez obu.

## Expected files

- Istniejące: `services/worker/src/game_predictor_worker/images/lateral_partial_contract.py` — nowy snapshot polityki.
- Istniejące: `services/worker/src/game_predictor_worker/images/page_geometry_registration.py` — kandydatura słabej ramki.
- Istniejące: `services/worker/src/game_predictor_worker/images/lateral_partial_artifact.py` — ścisłe odtworzenie kandydatury.
- Istniejące: `services/worker/src/game_predictor_worker/images/structured_geometry/lattice_refinement_v4.py` — kompletna propozycja lokalnej siatki.
- Istniejące: `services/worker/src/game_predictor_worker/images/production_workflow.py` — routing per slot.
- Istniejące: `services/api/src/game_predictor_api/schemas/geometry_qualification.py`, `services/api/src/game_predictor_api/schemas/jobs.py`, `services/api/src/game_predictor_api/schemas/image_grid_reviews.py` — kontrakt API.
- Istniejące: `services/api/src/game_predictor_api/storage/image_grid_review_repository.py` — stan kolejki.
- Istniejące: `apps/reviewer/src/features/grid-reviews/grid-review-state.ts`, `grid-review-actions.ts`, `grid-review-editor.tsx` — nakładka i zapis.
- Istniejące testy workera, API i Reviewera oraz wygenerowany klient OpenAPI.

## Test cases

- Mocna strona, dziewięć uporządkowanych quadów, jeden slot z coverage
  `0,3525`, średnia `0,8864`, lokalna siatka bezpieczna → propozycja ramki i
  `needs_validation`.
- Coverage `0,6250` i `0,4245` dla dwóch pozostałych zgłoszonych źródeł →
  ten sam jawny review zamiast cichego automatycznego zatwierdzenia.
- Cztery słabe ramki, coverage poniżej `0,30`, średnia poniżej `0,70`, zła
  geometria albo lokalny refiner bez siatki → brak propozycji.
- Zdjęcie mieszane → mocne sloty automatyczne, słaby z siatką do walidacji,
  słaby bez siatki do poprawy.
- Snapshot v1/v2 round-trip → identyczny payload i zachowanie historyczne;
  snapshot v3 → ścisła kontrola nowych pól i checksummy.
- UI/API → propozycja ramki pokazuje siatkę, nie wymaga czterech kliknięć i
  zapisuje kwalifikację kompletnej geometrii.

## Verification

```powershell
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services/worker/tests/test_lateral_page_registration.py services/worker/tests/test_structured_lattice_refinement_v4.py services/worker/tests/test_lateral_partial_workflow.py services/api/tests/test_image_grid_review_api.py services/api/tests/test_lateral_partial_engine_contract.py -q
npm run openapi:generate
npm test --workspace @game-predictor/admin-api-client
npm test --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services/api services/worker
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m mypy services/api/src services/worker/src
```

Zaliczenie wymaga wszystkich kryteriów oraz ponownego, read-only uruchomienia
rejestracji i lokalnego refinera na trzech wskazanych JPEG-ach.

## Risks / open questions

- Próg `0,65` celowo odpowiada istniejącej definicji mocnej auto-kotwicy.
  Może zwiększyć liczbę siatek do walidacji, ale nie kieruje ich do ręcznego
  rysowania i nie obniża bezpieczeństwa importu.
- Nowa polityka obejmuje tylko nowe preflighty. Istniejący niezmienny manifest
  nie może zostać po cichu przeliczony.

## Outcome

### Changed

- Snapshot polityki v3 rozpoznaje do trzech słabych ramek przy mocnej
  rejestracji strony i zapisuje wersjonowaną kandydaturę v2.
- Refiner symboli tworzy kompletną `automaticFrameProposal`, a kolejka, API i
  Reviewer pokazują gotową nakładkę jako `needs_validation`.
- Propozycja jest kompletna, wymaga potwierdzenia i nie wchodzi do zwykłego
  uczenia geometrii ani kotwic.

### Verification results

- Trzy zgłoszone JPEG-i przeszły read-only: slot 0 uzyskał kolejno 12, 11 i 11
  inlierów, p95 `3,2145`, `9,3631` i `7,5987 px` oraz status
  `pending_review`.
- Skoncentrowane testy workera i API: 99 zaliczonych.
- Reviewer: 188 zaliczonych; Admin: 485 zaliczonych; Admin API client: 57
  zaliczonych. Typecheck, Ruff, Prettier, kontrola OpenAPI oraz produkcyjne
  buildy Admina i Reviewera są zielone.

### Not completed

- Nie przeliczano ani nie zmieniano istniejącego preflightu i danych
  użytkownika. Nowa polityka obowiązuje nowe wykonanie.

### Documentation updates

- Uaktualniono wymagania importu, własność geometrii, kontrakt API, dziennik
  decyzji i bieżący stan projektu.

### Recommended next task

- Brak, jeśli realne trzy źródła oraz regresje przejdą.

## Plan implementacji

1. Wersjonować snapshot i kandydaturę rejestracji, zachowując ścisły replay v1/v2.
2. Dodać bezpieczną kwalifikację niepełnej ramki i routing per slot przez lokalny refiner.
3. Rozszerzyć trwałą kolejkę, API i Reviewer o kompletną propozycję do walidacji.
4. Zweryfikować regresje syntetyczne, trzy realne JPEG-i, pełne kontrakty i build; uaktualnić dokumentację i zamknąć task osobnym commitem.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0549 | gpt-5.6-sol | high | Zmiana wymaga spójnego wersjonowania algorytmu, trwałego artefaktu, API i zachowania kolejki. | Tylko przy osłabieniu istniejących bramek: gpt-6-astra, high. |
