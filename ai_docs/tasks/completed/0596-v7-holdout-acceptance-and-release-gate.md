---
title: V7 holdout acceptance, recovery and release gate audit
status: done
last_updated: 2026-09-21
---

# TASK-0596 — odbiór holdoutu i bramka wydania V7

## Status

`done` — release pozostaje `blocked`.

## Goal

Wykonać końcowy, checksum-bound odbiór V7 na niezależnym holdoucie, recovery i
historycznej kompatybilności. Udokumentować jeden z dwóch wyłącznych wyników:
`accepted` dopuszczający świadomą aktywację albo `blocked` z mierzalnym powodem.
Nie aktywować V7 przy pustym mianowniku, nieudanej kalibracji, braku niezależnej
anotacji albo nieprzejściu testów bezpieczeństwa.

## Context

T05 zakończył się `not_evaluable`: brak ręcznych anotacji geometrii i ground
truthu pozostawił wszystkie mianowniki odbioru puste. T11 potwierdził ograniczony
runtime, ale nie kalibruje dowodu ani nie zastępuje holdoutu. T06 nadal blokuje
`v7_selection` po stronie API przed pobraniem źródła, utworzeniem joba lub
zużyciem tokenu. Ten task nie może zamienić braku danych w syntetyczny sukces.

## Dependencies / entry conditions

- T00–T11 są zakończone; `v7_selection` pozostaje `blocked`.
- Korpus i inventory T01 są dostępne przez lokalny manifest w `.runtime`; ich
  ścieżka nie jest zapisywana w kodzie ani w raporcie wersjonowanym.
- `rells_big` jest jedynym current holdout case. Nie istnieje checksum-bound
  anotacja jego zakresów, reprezentantów ani warningów, więc bieżący wynik ma
  obowiązek być `blocked`, o ile audyt tego nie obali.

## Recommended execution

`gpt-6-astra`, reasoning `high`. Zadanie rozstrzyga gotowość produkcyjną i musi
odróżnić brak dowodu od negatywnego wyniku. Po self-audycie wymagany jest
niezależny review `gpt-6-astra`, reasoning `medium`; każde znalezisko wymaga
poprawki i pełnej ponownej weryfikacji przed commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/V7_T11_RUNTIME_PERFORMANCE.json`
- `ai_docs/tasks/0596-v7-holdout-acceptance-and-release-gate.md`

## Scope

- Wykonać istniejący, read-only evaluator kalibracji na przypiętym manifeście i
  pustej checksumowanej anotacji T05, aby potwierdzić rzeczywisty status
  geometrii i metryk zamiast przepisać go z dokumentacji.
- Uruchomić komplet celowanych testów V7: konfigurację, proof, occurrence,
  ranking/quality, kalibrację, checkpoint/finalizację, writer/recovery,
  uporządkowany runtime, API gate i migrację. Uruchomić regresję Admina dla
  formularza/podglądu i historycznego outputu.
- Zbudować raport T12 powiązany z fingerprintem manifestu, wynikami komend i
  mianownikami kalibracji/odbioru. Raport ma osobno wskazać coverage zakresu,
  błędne automatyczne zakresy, reprezentantów, warnings góra/dół, false positive
  i manual review; brak danych ma zostać `not_evaluable`.
- Zweryfikować fail-closed release gate: capabilities ma `blocked` i
  `startEnabled=false`, a start V7 kończy się przed źródłem/jobem/tokenem.
  Sprawdzić, że historyczne workflowy i output acknowledgement nadal przechodzą
  swój kontrakt.
- Uaktualnić dokumentację i `TEMP PLAN V7.md` o wynik odbioru. Jeżeli wszystkie
  bramki nie przejdą, utrzymać blokadę i zapisać konkretny zestaw danych potrzebny
  do ponownego T12.

## Out of scope

- Ręczne oznaczanie w imieniu operatora, wytwarzanie truthu z OCR, strojenie
  modelu do holdoutu, obniżenie progów 95%/95%/zero błędów/100% i aktywacja API
  bez niezależnego wyniku.
- Zapisy JPEG-ów, tworzenie katalogów `cut`, migracje danych użytkownika,
  trening, instalacja CUDA/GPU oraz nowe usługi.

## Acceptance criteria

- [ ] Raport zawiera aktualny fingerprint manifestu, źródło danych, mianownik i
  status każdego progu; `not_evaluable` nigdy nie jest `passed`.
- [ ] Aktywacja może być zaproponowana tylko gdy geometria jest `passed`, zakres
  i reprezentant mają co najmniej 95%, błędne automatyczne zakresy wynoszą 0,
  oba recall warningów góra/dół wynoszą 100%, a dowody pochodzą wyłącznie z
  holdoutu poza development/calibration/validation.
- [ ] Aktualny brak takich anotacji zostaje udokumentowany jako `blocked`, a API
  pozostaje zablokowane przed źródłem i jobem.
- [ ] Testy recovery obejmują first-write, manual first/no-OCR/replace, restart
  po publikacji, supersede/cancel, owner history i wyścig generacji; testy
  historycznych workflowów, migracji oraz UI przechodzą bez regresji.
- [ ] Raport wymienia ograniczenia pomiaru T11 i nie przedstawia go jako jakości
  OCR, kalibracji ani zgody na produkcyjny start.

## Technical notes

T12 nie zmienia stanu bramki na podstawie samego pliku raportu. W tym stanie
repozytorium stale zakodowana blokada API jest poprawnym fail-closed mechanizmem,
bo żaden niezależny holdout nie został oznaczony. Do przyszłego ponownego odbioru
operator musi dostarczyć checksum-bound anotację dla `rells_big`: każdy
automatycznie odzyskiwalny zakres z własnymi źródłami dowodu, kwalifikowalność
reprezentanta, oznaczenia top/bottom i zamrożone predykcje automatu przed ręczną
korektą. Geometria nadal wymaga pięciu niezależnych źródeł calibration na każdą
pozycję; holdout nie może jej kalibrować.

## Expected files

- Nowe: `ai_docs/quality/V7_T12_ACCEPTANCE.md` — wynik odbioru i dokładna
  przyczyna braku aktywacji albo dowód przejścia.
- Istniejące: `ai_docs/process/CURRENT_STATE.md`,
  `ai_docs/requirements/IMAGE_SELECTION.md`,
  `ai_docs/architecture/IMAGE_SELECTION.md`, `TEMP PLAN V7.md`.
- Testy i production code pozostają bez zmian, chyba że audyt ujawni rzeczywistą
  regresję zakresu T00–T11; taka poprawka dostaje test odtwarzający.

## Test cases

- Pusta anotacja T05 → geometria i wszystkie metryki `not_evaluable`,
  `productionActivation=blocked`; wynik nie może zostać policzony jako zero
  błędów i sukces.
- Start V7 z niepoprawnym tokenem → `SEMI_AUTOMATIC_SELECTION_V7_BLOCKED`, bez
  utworzenia runu lub identity.
- Pełny pakiet writer/recovery → first write, replace O1→O2→O3, restart po
  publish, conflict, cancel/supersede i stale generation.
- Historyczne `selection` / `filename_verification`, ich API capabilities i
  output acknowledgement zachowują poprzedni kontrakt.
- Formularz/podgląd V7 zachowuje blokadę, a legacy output picker i viewer
  przechodzą regresję.

## Verification

```powershell
# C:\Users\tuszy\Documents\game_predicotr, maks. 120 s na krok
.\.venv\Scripts\python.exe scripts\evaluate_v7_calibration.py --manifest .runtime\v7-corpus-manifest.local.json --inventory artifacts\v7-selection\t01-corpus-inventory.json --annotations .runtime\v7-t05-empty-annotations.json --output .runtime\v7-t12-calibration-recheck.json
.\.venv\Scripts\python.exe -m pytest services\worker\tests\test_v7_configuration.py services\worker\tests\test_v7_label_locator.py services\worker\tests\test_v7_range_proof.py services\worker\tests\test_v7_occurrences.py services\worker\tests\test_v7_quality.py services\worker\tests\test_v7_calibration.py services\worker\tests\test_v7_run_state.py services\worker\tests\test_v7_output_writer.py services\worker\tests\test_v7_ordered_runtime.py services\worker\tests\test_evaluate_v7_calibration_script.py -q
.\.venv\Scripts\python.exe -m pytest services\api\tests\test_semi_automatic_image_selections.py services\api\tests\test_semi_automatic_selection_migration.py -q
Push-Location apps\admin
node --experimental-strip-types --test test\v7-selection-form.test.mjs test\manual-local-image-selection.test.mjs test\semi-automatic-selection-output.test.mjs test\semi-automatic-selection-workspace-contract.test.mjs
Pop-Location
```

## Risks / open questions

- Brak ręcznej anotacji holdoutu i niezaliczona kalibracja są oczekiwanym
  krytycznym blockerem aktywacji, ale nie blokują wykonania samego audytu.
- Wersja CPU-only może ograniczać przepustowość, lecz T11 nie jest progiem
  odbioru jakości. Nie instalować GPU builda podczas T12.

## Outcome

Wykonano read-only ponowną ocenę T05 na przypiętym manifeście T01. Fingerprint
manifestu i inventory nadal wynosi
`604185fbe5d8bbfe071788dd38a9bf6cf764d16561415afcf4e29b70d54ffda9`, lecz
geometria oraz wszystkie mianowniki odbioru są `not_evaluable`: brak ręcznych
anotacji geometrycznych i brak prawdy/predykcji dla zakresów. W szczególności
zero błędnych automatycznych zakresów przy `0 / 0` nie zalicza progu. Case
`rells_big` nie jest gotowym holdoutem, bo D-404 wyłącza jego wcześniej oglądany
plik, którego manifest obecnie nie odfiltrowuje.

Audyt kodu potwierdził twardą blokadę `v7_selection` przed źródłem, jobem i
tokenem. Odkrył również materialny brak implementacyjny: komponenty V7 z T02–T11
nie są wywoływane przez `SemiAutomaticImageSelectionJobHandler`. Usunięcie
blokady API przekazałoby run do legacy flow, dlatego aktywacja byłaby błędna
nawet po dostarczeniu anotacji. Nie zmieniono production code ani statusu gate.

Weryfikacja końcowa: worker V7/recovery `113 passed`; API/migracja `30 passed`
z jednym ostrzeżeniem deprecacyjnym Starlette; Admin `59 passed`, typecheck i
lint bez błędów. Pierwsza próba testu Admina użyła złego katalogu i nie wykonała
testów; poprawione polecenie z `apps/admin` wykonało pełne 59 testów. Raport:
`ai_docs/quality/V7_T12_ACCEPTANCE.md`.

T12 jest ukończonym audytem z negatywnym werdyktem wydania. Do nowej próby
potrzebne są: nowy niezależny holdout albo manifest wykluczający plik D-404,
pięć niezależnych calibration sources na każdą pozycję, ręczne ground truth i
zamrożone predykcje holdoutu oraz osobny, testowany pion integrujący V7 z
workerem/API bez zmiany historycznego handlera.
