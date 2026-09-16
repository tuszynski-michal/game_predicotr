---
title: TASK-0533 — Oddzielny profil uczenia niepełnych siatek
status: done
last_updated: 2026-09-14
---

# TASK-0533 — Oddzielny profil uczenia niepełnych siatek

## Status

`done`

## Goal

Zapisywać jawnie wskazane ręczne geometrie bocznie uciętych siatek 3×5 w
oddzielnej puli i używać jej deterministycznego, wersjonowanego profilu do
rozstrzygania bezpiecznych automatycznych propozycji, zawsze wymagających
ręcznej weryfikacji.

## Context

Istniejący wariant v0.10.4 potrafi przygotować boczną niepełną propozycję na
podstawie obrazu, lecz nie uczy się z ręcznych korekt. Trzecie pole pod planszą
jest obecnie tylko nieaktywną informacją. Operator polecił zamienić je w jawny
opt-in do osobnej puli, bez dopuszczania tych próbek do zwykłego profilu
geometrii ani kotwic stron.

## Dependencies / entry conditions

- Aktywny pełny tor geometrii pozostaje `structured_lattice_v3`, a niepełny
  wariant v0.10.4 jest włączany jawnie dla runu.
- `manual-geometry-qualification-v1` nadal musi być odczytywany bez zmiany
  historycznych checksum.
- Istniejąca kolejka ręcznej korekty niepełnych siatek pozostaje właścicielem
  potwierdzenia automatycznej propozycji.

## Recommended execution

`gpt-6-astra high`; zmiana przecina domenę, migrację, API, generowany klient,
Admin i worker oraz wymaga zachowania odtwarzalności starych jobów. Eskalować
do dodatkowego review `gpt-6-astra xhigh`, jeżeli test odtworzenia wykryje drift
historycznej polityki v1 lub nie da się utrzymać twardego rozdzielenia kohort.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/architecture/ITERATIVE_IMAGE_IMPORT.md`

## Scope

- Wersja v2 kwalifikacji geometrii z polem
  `includeInPartialGridTraining`; v1 pozostaje zgodne w odczycie.
- Aktywny checkbox wyłącznie dla niepełnej planszy; wyłączenie niepełności
  automatycznie usuwa opt-in.
- Oddzielna, wyliczana z najnowszych rewizji ręcznych korekt pula z deduplikacją
  po checksumie źródła; tylko boczne maski obejmujące całe kolumny i wszystkie
  trzy wiersze są dozwolone.
- Deterministyczny profil większości masek z bramką co najmniej trzech różnych
  źródeł. Profil może wyłącznie rozstrzygnąć między propozycjami, które przeszły
  dotychczasowe bramki obrazu, geometrii i ochrony treści.
- Wersjonowany snapshot v2 przypięty do nowego preflightu i joba; historyczny
  snapshot v1 odtwarza się bez zmian.
- Każda propozycja z profilem pozostaje `pending_partial`, jest wykluczona ze
  zwykłego treningu i kotwic oraz trafia do istniejącej ręcznej kolejki.
- Diagnostyka pokazuje liczbę próbek, różnych źródeł i gotowych wzorców osobnej
  puli.

## Out of scope

Sieć neuronowa, automatyczne zatwierdzanie propozycji, pionowe ucięcia,
generowanie brakujących pikseli, zmiana detektora pełnych siatek oraz ponowne
przeliczanie historycznych jobów bez jawnego nowego runu.

## Acceptance criteria

- [x] Checkbox zapisuje v2 wyłącznie dla poprawnej niepełnej bocznej siatki.
- [x] Próbka z opt-in nie pojawia się w zwykłej kohorcie ani kotwicach.
- [x] Najnowsza rewizja jest źródłem prawdy; odznaczenie usuwa próbkę z
      kolejnego profilu bez kasowania historii.
- [x] Trzy różne źródła tworzą gotowy wzorzec; mniej nie zmienia wyniku
      automatycznego algorytmu.
- [x] Profil nie omija istniejących bramek obrazu i nie zatwierdza geometrii.
- [x] Snapshot v1 jest zgodny bajtowo, a v2 odrzuca zmianę payloadu lub checksumy.
- [x] API/OpenAPI/klient i Admin używają jednego kontraktu.
- [x] Testy domeny, migracji, API, workera oraz interakcji UI przechodzą.

## Technical notes

Źródłem prawdy są najnowsze rekordy `image_page_geometry_overrides`; pool nie
otrzymuje równoległej tabeli mutable. `manual-geometry-qualification-v2`
zachowuje obowiązkowe `excludeFromGeometryTraining=true`, a nowe pole jest
niezależną, pozytywną zgodą tylko dla oddzielnego algorytmu. Profil grupuje
próbki według kanonicznej maski brakujących bocznych kolumn i liczy różne
checksumy źródeł. W nowym preflighcie cały profil i jego checksum są częścią
snapshotu. Retry czyta ten snapshot, a nie bieżący pool.

Przy wielu zaakceptowanych hipotezach worker wybiera dokładnie jedną tylko,
gdy odpowiada ona jedynemu gotowemu wzorcowi o najwyższym poparciu. Remis,
brak wzorca albo mniej niż trzy źródła zachowuje `ambiguous_column_indices`.

## Expected files

- Istniejące: kwalifikacja domenowa i schemat API, page override service,
  modele SQLAlchemy, migracje, lateral partial contract/refinement, JobService,
  diagnostyka kalibracji, generowany klient i oba widoki korekty.
- Nowe: `services/worker/src/game_predictor_worker/images/partial_grid_learning.py`
  i migracja `0111_partial_grid_training_qualification.py`.

## Test cases

- v1 round-trip zachowuje dawny payload; v2 round-trip przenosi opt-in.
- Pełna, pionowo ucięta, pusta albo niespójna maska z opt-in jest odrzucana.
- Dwie próbki nie tworzą gotowego wzorca; trzy różne checksumy tworzą; wiele
  plansz z jednego zdjęcia nie zawyża pokrycia.
- Nowsza rewizja z odznaczeniem wyłącza źródło z nowego snapshotu.
- Wyuczony wzorzec rozstrzyga tylko wieloznaczność; jednoznaczny stary wynik i
  pełna siatka pozostają identyczne.
- Propozycja v2 ma wymagane potwierdzenie i istniejąca kolejka ją zlicza.

## Verification

```powershell
npm test --workspace @game-predictor/manual-image-selection-core
npm test --workspace @game-predictor/admin-api-client
npm run test:geometry --workspace @game-predictor/admin
.venv\Scripts\python.exe -m pytest services/api/tests services/worker/tests -q
npm run openapi:check
npm run typecheck
```

Pełny zbiór testów może zostać zawężony do zmienionych modułów przed szerszą
kontrolą. Zaliczenie wymaga regresji starego snapshotu, migracji offline oraz
interakcji checkbox → zapis → nowy preflight → propozycja do review.

## Risks / open questions

- Pierwsza wersja uczy statystyczny profil masek, a nie cechy wizualne sieci
  neuronowej. Jest to świadomie ograniczony wariant dopuszczony przez operatora.
- Gotowość wzorca wymaga trzech różnych zdjęć, aby dziewięć plansz jednego
  źródła nie dawało pozornej pewności.

## Outcome

Dodano kwalifikację v2 z jawnym opt-inem, osobny deterministyczny profil masek
oraz snapshot polityki v2 przypinany do nowego preflightu i importu. Profil
korzysta wyłącznie z najnowszych page override'ów, deduplikuje gotowość po
checksumie źródła i może rozstrzygnąć tylko wieloznaczną propozycję, która
przeszła wcześniejsze bramki. Automatyczny wynik nadal jest
`pending_partial`, wykluczony ze zwykłego treningu i kotwic oraz wymaga ręcznej
weryfikacji.

Admin zapisuje checkbox i pokazuje diagnostykę puli. OpenAPI oraz klient są
wygenerowane z backendu. Migracja 0111 została zastosowana do lokalnej bazy i
potwierdzona w nowym procesie jako `head`.

Walidacja: 166 skupionych testów API/workera, 11 testów pełnego przepływu v1/v2,
93 testy wspólnego modułu UI, 456 testów Admina, 3 testy interakcji geometrii,
183 testy Reviewera i 57 testów klienta API przeszły. OpenAPI check, typecheck
trzech pakietów UI oraz scoped mypy dziewięciu zmienionych modułów przeszły.
Pełne testy Python nie dały wyniku końcowego i zostały przerwane po obowiązkowym
limicie 120 sekund, dlatego nie są używane jako dowód odbioru. Pełny
repozytoryjny mypy nadal ma wcześniejsze błędy w skryptach narzędziowych i
module półautomatycznej selekcji; zmienione moduły są czyste.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0533 | `gpt-6-astra` | `high` | Zmiana wielowarstwowego kontraktu z wymaganiem kompatybilności jobów, rozdzielenia danych treningowych i testów regresji. | `gpt-6-astra xhigh` tylko przy wykrytym drifcie v1 lub niejednoznacznym rozdzieleniu kohort |
