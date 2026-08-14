---
title: TASK-0242 image selection v10.11 derived range recovery
status: in_progress
release: "0.6"
last_updated: 2026-08-14
---

# TASK-0242 — Image selection v10.11 derived range recovery

## Status

`in_progress`

## Goal

Odzyskać czytelne zakresy oraz poprawne granice grup z historycznego runu bez
mutowania jego decyzji, ponownego uploadu ani pełnego skanu źródeł.

## Context

Run v10.9 `6c6afaf9-e144-4d5d-9cc6-8dc30a395bbd` zachowuje 748 grup
`range_required`. Kontrola rzeczywistych JPEG-ów potwierdziła, że część numerów
jest czytelna, a sąsiednie grupy mogą przedstawiać ten sam zakres. Samo ponowne
OCR bieżącego reprezentanta nie wystarcza: stara granica grupy, reprezentant,
false split albo false merge również mogą być błędne.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`
- `ai_docs/tasks/0241-image-selection-v1010-label-lattice-safety-recovery.md`
- `ai_docs/tasks/completed/0239-image-selection-v109-partial-layout-range-recovery.md`
- `ai_docs/tasks/completed/0240-image-selection-pending-output-directory-isolation.md`

## Scope

- dodać niezmienny `fast-image-selector-v10.11`, zachowując historyczne
  fingerprinty i fabryki v10.10 oraz starszych,
- nadać niezależnej siatce etykiet pierwszeństwo przed niejednoznaczną
  częściową geometrią; mocny konflikt nadal pozostaje fail-closed,
- agregować słaby dowód wyłącznie pomiędzy różnymi checksumami i zgodnymi
  pozycjami lokalnej siatki,
- tworzyć idempotentny run pochodny wskazujący run źródłowy, jego rewizję i
  fingerprint v10.11,
- kopiować pewne grupy oraz decyzje użytkownika z jawnym pochodzeniem,
- dla maksymalnych bloków `range_required` ponownie walidować kotwice,
  spłaszczać wszystkich kandydatów do kolejności źródłowej i od nowa wyznaczać
  grupy, zakresy oraz reprezentantów,
- nigdy nie przypisywać zakresu do JPEG-a, którego własny dowód go nie
  potwierdza; niewyjaśniony przypadek zachować do review,
- umożliwić zmianę JPEG-a podczas ustalania zakresu, podawanie tylko pierwszego
  numeru i opcjonalny krótki zakres końcowy,
- otwierać modal bez blokującego uzgadniania wszystkich historycznych plików;
  decyzja zapisuje synchronicznie tylko bieżący JPEG,
- wykonać dry-run wszystkich 748 grup przed utworzeniem runu pochodnego.
- po niezaliczonym dry-runie v10.11 dodać niezmienny v10.12 z dwucyfrowym
  konsensusem dwóch JPEG-ów i globalnym uzgadnianiem duplikatów zakresu.
- po analizie projekcji v10.12 dodać niezmienny v10.13, który zapisuje pełne
  granice sekwencji, wylicza oczekiwaną liczbę grup po dziewięć i uzgadnia całą
  projekcję z tą licznością bez zmiany decyzji użytkownika.

## Out of scope

- mutowanie lub usuwanie historycznego runu i jego audytu,
- ponowny upload albo pełny skan 32 079 źródeł,
- rozstrzyganie dowolnego skoku wyłącznie z oczekiwanego kursora,
- automatyczne naprawianie pozostałych zakończonych runów przed odbiorem
  właściciela,
- Redis, Celery, chmura lub dodatkowy worker lane.

## Acceptance criteria

- [x] V10.10 zachowuje dokładny fingerprint i zachowanie po resolverze.
- [x] Niezależna siatka rozpoznaje znane regresje `1_013145.jpg`,
      `00002809.jpg` i `00005282.jpg` bez przesunięcia zakresu.
- [x] Przebudowa obsługuje błędnego reprezentanta, false split i false merge,
      a żaden kandydat nie jest użyty jako reprezentant dwóch wyników.
- [x] Dry-run 748 grup pozostawia najwyżej 14 czytelnych grup bez zakresu.
- [ ] Znane decyzje właściciela i warstwowa próba co najmniej 100 wyników mają
      zero błędnych zakresów.
- [ ] Run źródłowy pozostaje byte-for-byte logicznie niezmieniony, a run
      pochodny zachowuje pochodzenie każdej skopiowanej lub przebudowanej grupy.
- [ ] Modal z istniejącym uprawnieniem folderu otwiera się do 2 sekund, a zapis
      pojedynczej decyzji trwa do 3 sekund bez pełnego reconcile przed modalem.
- [x] Migracja upgrade/downgrade, worker, API, OpenAPI i Admin przechodzą.
- [x] Projekcja zakresu `1–19809` zawiera dokładnie 2201 logicznych właścicieli
      i ciąg `1–9`, `10–18`, ..., `19801–19809`; dodatkowe fragmenty są jedynie
      jawnymi duplikatami wskazującymi właściciela.
- [x] Każdy z 2201 logicznych właścicieli ma co najmniej jeden JPEG obecny w
      źródłowym manifeście; pusta grupa lub checksum spoza manifestu blokują
      automatyczną bramkę.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/`
- `services/api/src/game_predictor_api/{domain,application,storage,schemas,api}/image_selections.py`
- `services/api/alembic/versions/0042_image_selection_derived_recovery.py`
- `services/api/alembic/versions/0043_image_selection_sequence_bounds.py`
- `apps/admin/src/features/image-selection/`
- dokumentacja image selection i raporty `artifacts/`

## Operational constraints

- Bieżącego runu v10.10 nie przerywać.
- Kontrolery następnych etapów pozostają zatrzymane podczas implementacji.
- Recovery nie startuje przed dry-runem i przejściem bram jakości.
- Pierwszy wynik docelowy używa katalogu
  `C:\Users\user\Documents\1 - 19809 new` z kontrolą checksum i bez
  nadpisywania kolizji.

## Outcome

Pierwszy pion dodał domyślny `fast-image-selector-v10.11` o fingerprintcie
`a3c3fcb1c36a1fe9e5a95b242aaa2d7d31ec067b28f1a16fe3f29ecb7318bc0c`.
Niezależna siatka jest oceniana przed częściową geometrią, trzy zgodne pozycje
tworzą wyłącznie słaby dowód wymagający drugiego JPEG-a, a konflikt dwóch
rozwiązanych tras pozostaje fail-closed. V10.10 zachowuje fingerprint
`282b08df4c3368c60e60048ac846d95bc41392631ebdeaf069f3afbdef9e4c7f`.

Skupione testy adaptera, selektora i joba przechodzą `168/168`; Ruff przechodzi.

Commity `v0.6.6` i `v0.6.7` dodały migrację 0042, snapshot-bound run pochodny,
przebudowę bloków z zachowanych kandydatów, jawne `origin_group_id` oraz szybką
ścieżkę review. W ustalaniu zakresu można zmienić JPEG, podać sam początek
(`+8` domyślnie), podać krótszy koniec albo odrzucić grupę. Pełne uzgadnianie
historycznego folderu nie blokuje otwarcia modala.

Etap `v0.6.8` wyodrębnił jedną funkcję `evaluate_recovery`, używaną identycznie
przez worker i dry-run. Naprawiono lokalne kotwiczenie: blok zachowuje globalną
siatkę modulo 9, lecz jego pierwsza grupa nie jest traktowana jako pierwsza
grupa całego zbioru. Dodatkowa bramka wymaga własnego zgodnego OCR wybranego
JPEG-a i odrzuca zakresy pochodzące wyłącznie z kotwicy albo inferencji luki.

Narzędzie `scripts/run_image_selection_range_recovery_dry_run.py` jest fail-closed:
odmawia startu przy migracji starszej niż 0042 albo aktywnym jobie selekcji,
kontroluje manifest i snapshot przed/po, unikalność JPEG-ów i zakresów,
pochodzenie, ochronę decyzji użytkownika oraz przygotowuje deterministyczną
próbę 100 wyników do audytu właściciela. Bez kompletnego audytu `0` błędów nie
ustawia `readyForRecoveryCreation=true`.

Walidacja: 690/690 testów workera; 332/332 wykonanych testów API, 2 pominięte
testy symlinków Windows; 2/2 testy izolowanego PostgreSQL, w tym rzeczywisty
upgrade/downgrade migracji 0042; 198/198 testów Admina; skupiony Ruff i mypy;
OpenAPI oraz typecheck Admina. Zaktualizowano golden manifestu image pipeline.

Run v10.10 `200557 - 222912` zakończył 42 422 / 42 422 bez błędów, a żywa baza
została podniesiona do migracji 0042. Pełny, tylko do odczytu dry-run v10.11
przeanalizował 748 grup i 32 079 zachowanych JPEG-ów w 39 blokach. Pozostawił
283 przypadki `range_required` oraz wykrył jeden `DUPLICATE_OUTPUT_RANGE`, więc
zgodnie z bramką nie utworzył runu pochodnego i nie zmienił źródłowego snapshotu.

Analiza pokazała 282 przypadki `RANGE_LABEL_LATTICE_INCOMPLETE`: 252 bez żadnej
alternatywnej hipotezy i 31 z jedną zgodną słabą hipotezą. Etap v10.12 dodaje
dwucyfrowy dowód wyłącznie przy dwóch niezależnych checksumach oraz globalne
uzgadnianie zakresów pomiędzy blokami. Fingerprint v10.12 to
`d1f482ef3b52f62d478e9bcd3c06777d0e62eb118bb639a854fbb2cb594b0727`;
v10.11 pozostaje niezmienny.

Walidacja v10.12: 696 testów przeszło w pełnym przebiegu workera; jedyny test
HTTP przerwany chwilowym `WinError 10053` przeszedł `1/1` przy natychmiastowej
powtórce. Przeszły też 332 wykonane testy API i 24 świadomie pominięte
integracje, 198/198 testów Admina, skupiony Ruff i mypy, aktualny OpenAPI,
ESLint oraz typecheck Admina. Powtórny dry-run v10.12, audyt 100 wyników i
utworzenie właściwego runu pochodnego nadal pozostają do wykonania w tej
kolejności.

Analiza projekcji przed kolejnym wykonaniem wykazała błąd liczności, którego
OCR nie mógł sam wykryć: run źródłowy ma 2295 fizycznych fragmentów i 128
`skipped_existing_range`, czyli tylko 2167 logicznych właścicieli. Deklarowany
przedział `1–19809` zawiera 19 809 layoutów, a więc dokładnie 2201 grup po
dziewięć. Poprzednia projekcja odrzuciła o 34 fragmenty za dużo; 26 zachowanych
zakresów automatycznych było też przesuniętych względem globalnej siatki.

Etap v10.13 dodaje pełny, inkluzywny kontrakt `first_sequence_number` +
`last_sequence_number`, migrację 0043 oraz oczekiwaną liczność
`ceil((abs(last-first)+1)/9)`. Nazwa wybranego folderu `pierwszy - ostatni`
ustawia koniec automatycznie; ostatnia grupa może być krótsza niż dziewięć.
Globalne programowanie dynamiczne wybiera dokładnie jednego właściciela każdej
pozycji siatki. Decyzji użytkownika nie wolno pominąć ani przesunąć, a duże
wcześniej pominięte fragmenty i zakresy spoza siatki wracają do ponownej
segmentacji zamiast otrzymać tylko zmieniony numer. Fingerprint v10.13 to
`b52b09737bf59eae712f7757c8e368fbfaf52e56f351889fbd3aa873a3d5fd30`;
wyniki weryfikacji v10.12 są zgodnym cache'em, ponieważ sam OCR się nie zmienił.
Reconciler preferuje JPEG z własnym zgodnym OCR, potem JPEG bez rozstrzygnięcia;
nie nadpisuje automatycznie kandydata, którego własny OCR wskazuje inny zakres.

Ostateczny dry-run v10.13 dla zachowanych 32 079 JPEG-ów przeanalizował 50
bloków i 24 684 kandydatów. Projekcja ma 2298 fizycznych fragmentów: 2181
`auto_selected`, 15 `manual_required`, 5 `range_confirmed` i 97
`skipped_existing_range`, czyli dokładnie 2201 logicznych właścicieli. Nie ma
`range_required`, błędów skanu ani problemów strukturalnych; automatyczne bramki
przeszły. Powtórka na pełnym cache'u 7840 weryfikacji trwała 105,395 s.

Końcowa bramka pokrycia potwierdziła `2201/2201` logicznych grup z co najmniej
jednym JPEG-em obecnym w niezmiennym manifeście 32 079 plików. Nie wykryto pustej
grupy ani referencji do obrazu spoza manifestu. Raport zapisano w
`artifacts/image-selection-v1013-range-recovery-final-dry-run-6c6afaf9.json`.

`readyForRecoveryCreation` pozostaje `false` wyłącznie dlatego, że
deterministyczna próba 100 wyników oczekuje audytu właściciela. Run pochodny i
kolejka następnych folderów pozostają wstrzymane do audytu z zerem błędnych
zakresów.

Etap `v0.6.12` domyka operatorski kontrakt pełnego rerunu z historycznego
stagingu: endpoint, runner i kontrolowany launcher przyjmują jawny koniec
sekwencji. Rerun `1–19809` nie może już utracić oczekiwanej liczności 2201 grup
tylko dlatego, że źródłowy run powstał przed migracją 0043.

Walidacja etapu: 334 testy API przeszły, 24 integracje zależne od środowiska
zostały pominięte; pełny Ruff format/lint, parser 33 skryptów PowerShell, mypy
327 modułów, OpenAPI i kontrola wygenerowanego klienta przeszły.
