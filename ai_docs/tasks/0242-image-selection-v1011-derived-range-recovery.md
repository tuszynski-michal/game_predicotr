---
title: TASK-0242 image selection v10.11 derived range recovery
status: in_progress
release: "0.6"
last_updated: 2026-08-13
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
- [ ] Dry-run 748 grup pozostawia najwyżej 14 czytelnych grup bez zakresu.
- [ ] Znane decyzje właściciela i warstwowa próba co najmniej 100 wyników mają
      zero błędnych zakresów.
- [ ] Run źródłowy pozostaje byte-for-byte logicznie niezmieniony, a run
      pochodny zachowuje pochodzenie każdej skopiowanej lub przebudowanej grupy.
- [ ] Modal z istniejącym uprawnieniem folderu otwiera się do 2 sekund, a zapis
      pojedynczej decyzji trwa do 3 sekund bez pełnego reconcile przed modalem.
- [x] Migracja upgrade/downgrade, worker, API, OpenAPI i Admin przechodzą.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/`
- `services/api/src/game_predictor_api/{domain,application,storage,schemas,api}/image_selections.py`
- `services/api/alembic/versions/0042_image_selection_derived_recovery.py`
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

Dry-run 748 grup i właściwy run pochodny pozostają świadomie niewykonane.
Aktywny v10.10 nadal działa, a żywa baza pozostaje na 0041; zgodnie z ograniczeniem
operacyjnym nie wykonano migracji ani równoległego OCR. Po zakończeniu v10.10:

1. wykonać migrację 0042 i uruchomić aktualne API,
2. uruchomić dry-run źródła `6c6afaf9-e144-4d5d-9cc6-8dc30a395bbd`,
3. zatwierdzić 100-elementową próbę właściciela i powtórzyć dry-run z plikiem
   decyzji,
4. utworzyć run pochodny tylko przy zaliczonych wszystkich bramkach.
