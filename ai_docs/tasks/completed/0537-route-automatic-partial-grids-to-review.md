# TASK-0537 — automatyczne niepełne siatki trafiają do walidacji

## Status

`done`

## Goal

Rozdzielić odroczone plansze z poprawną automatyczną propozycją siatki od
przypadków bez geometrii: propozycję od razu nałożyć na obraz i skierować do
potwierdzenia, a ręczne wskazywanie narożników wymagać wyłącznie tam, gdzie
algorytm nie wyznaczył siatki.

## Context

Silnik lateral-partial v4 zapisuje dla poprawnego wyniku `symbolGridQuad` oraz
`automaticPartialProposal`, ale projekcja kolejki oznacza każdy odroczony slot
jako `needs_correction` i `manualGeometryRequired=true`. Reviewer pokazuje więc
automatyczną propozycję w tej samej ścieżce co brak wyniku i blokuje zwykłe
potwierdzenie całego zdjęcia.

## Dependencies / entry conditions

- Aktywny wariant `structured_lattice_v4_partial_sides` zapisuje
  `symbolGridQuad` i kwalifikację `pending_partial`.
- Automatyczna propozycja nadal wymaga ręcznego potwierdzenia i nie może zostać
  automatycznie zaakceptowana.
- Istniejący zapis geometrii całego źródła potrafi atomowo zmaterializować slot
  odroczony i zachować jego kwalifikację.

## Recommended execution

`gpt-6-astra`, reasoning `high`. Zmiana obejmuje semantykę kolejki, filtrowanie
SQL, liczniki, zapis całego źródła i zachowanie edytora, dlatego wymaga testów
API i Reviewera. Dodatkowy review nie jest potrzebny, jeżeli nie zmienią się
progi ani sam detektor.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`

## Scope

- Klasyfikować odroczony slot z kanonicznym `automaticPartialProposal` i
  poprawnym `symbolGridQuad` jako `needs_validation`.
- Zachować taki quad jako widoczną siatkę startową i ustawić
  `manualGeometryRequired=false`.
- Klasyfikować brak poprawnej propozycji jako `needs_correction`, z roboczym
  szablonem i `manualGeometryRequired=true`.
- Rozdzielić oba przypadki w filtrach i licznikach kolejki.
- Przy potwierdzeniu zdjęcia atomowo zmaterializować automatyczne propozycje
  istniejącą ścieżką zapisu całego źródła, wraz z kwalifikacją partial.
- Przy ręcznym uzupełnianiu zachować siatki, które już istnieją, i wyzerować
  wyłącznie sloty bez wyniku algorytmu.
- Dodać testy regresyjne API i Reviewera oraz zaktualizować dokumentację.

## Out of scope

- Zmiana detektora, progów obrazu, profilu uczenia lub fingerprintu silnika.
- Automatyczne zatwierdzanie propozycji bez akcji operatora.
- Przeliczanie istniejących jobów albo modyfikacja danych użytkownika.
- Zmiana kontraktu OpenAPI, jeśli istniejące pola wystarczą do pełnego pionu.

## Acceptance criteria

- [x] Poprawna automatyczna propozycja jest widoczna jako siatka i trafia do
      `Do walidacji`.
- [x] Propozycję można potwierdzić bez ręcznego ponownego wskazywania narożników.
- [x] Potwierdzenie zachowuje `pending_partial`, maskę brakujących pól i wymóg
      wykluczenia ze zwykłego uczenia geometrii.
- [x] Slot bez automatycznego quada pozostaje w `Do poprawy` i wymaga ręcznego
      wyznaczenia.
- [x] Rozpoczęcie ręcznego uzupełniania nie usuwa automatycznych ani już
      zapisanych siatek pozostałych plansz zdjęcia.
- [x] Filtry i liczniki rozdzielają walidację propozycji od ręcznej korekty.
- [x] Testy zmienionego pionu, typecheck, lint i build Reviewera przechodzą.

## Technical notes

Klasyfikacja ma być fail-closed: samo istnienie metadanych propozycji nie
wystarcza bez poprawnego czteropunktowego `symbolGridQuad`. Zwykłe potwierdzenie
źródła zawierającego pending slot użyje endpointu zapisu geometrii całego
źródła z bieżącymi quadami; dla automatycznego partiala kwalifikacja pochodzi z
`automaticPartialProposal.geometryQualification`. Źródło zawierające choć
jeden rzeczywisty brak geometrii nadal blokuje potwierdzenie do czasu ręcznego
uzupełnienia.

## Expected files

- `services/api/src/game_predictor_api/storage/image_grid_review_repository.py`
- `services/api/src/game_predictor_api/domain/image_grid_reviews.py`
- `services/api/tests/test_image_grid_review_api.py`
- `services/api/tests/test_virtual_grid_geometry_repository.py`
- `apps/reviewer/src/features/grid-reviews/grid-review-{actions,state,workspace,editor}.tsx`
- testy `apps/reviewer/test/`
- dokumentacja wskazana w `Relevant docs`

## Test cases

- Pending z propozycją i quadem → `needs_validation`, brak ręcznego szablonu,
  siatka startowa równa `symbolGridQuad`.
- Pending z metadanymi bez poprawnego quada → `needs_correction` i szablon
  ręczny.
- Filtr `needs_validation` pobiera propozycje, a `needs_correction` tylko
  rzeczywiste braki.
- Liczniki dodają propozycje do walidacji i nie odejmują ich drugi raz od
  ręcznych korekt.
- Potwierdzenie źródła z automatycznym partialem wywołuje atomowy zapis źródła
  z quadem i kwalifikacją propozycji.
- Ręczne rozpoczęcie uzupełniania zeruje tylko slot bez siatki.

## Verification

```powershell
pytest services/api/tests/test_image_grid_review_api.py services/api/tests/test_virtual_grid_geometry_repository.py
npm test --workspace @game-predictor/reviewer
npm run test:geometry --workspace @game-predictor/reviewer
npm run typecheck --workspace @game-predictor/reviewer
npm run lint --workspace @game-predictor/reviewer
npm run build --workspace @game-predictor/reviewer
```

## Risks / open questions

- Starsze rekordy z uszkodzonym lub niekompletnym payloadem pozostają
  bezpiecznie w ręcznej korekcie.
- Brak pytań blokujących: użytkownik jednoznacznie wskazał oczekiwane
  rozdzielenie walidacji i ręcznej geometrii.

## Outcome

- Repozytorium kolejki rozpoznaje wyłącznie propozycję z czterema skończonymi
  punktami jako gotową do walidacji. Liczniki i filtry nie mieszają jej z
  ręczną korektą.
- Reviewer zachowuje i nakłada automatyczny quad, w tym boczne współrzędne poza
  obrazem. Potwierdzenie materializuje go atomowym zapisem źródła wraz z
  kwalifikacją; brak quada pozostaje zablokowany do ręcznego uzupełnienia.
- Edytor źródła mieszanego czyści tylko szkice oznaczone przez API jako
  `manualGeometryRequired`; gotowe siatki pozostają bez zmian.
- Dodano regresje projekcji API, filtrów SQL, licznika, akcji potwierdzenia i
  zachowania szkiców Reviewera. Przeszły testy API, pełne testy Reviewera,
  testy geometrii, typecheck, lint i build produkcyjny.
- Nie zmieniono kontraktu OpenAPI, detektora ani danych użytkownika; nie
  uruchamiano istniejących jobów.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0537 — automatyczne niepełne siatki trafiają do walidacji | gpt-6-astra | high | Zmiana musi zachować spójność stanu kolejki, atomowego zapisu źródła i kwalifikacji partial bez zmiany detektora. | Nie; detektor i jego progi pozostają bez zmian. |
