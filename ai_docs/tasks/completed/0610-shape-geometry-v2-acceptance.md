---
title: Niezależny odbiór acceptance wspólnej geometrii shape v2
status: done
task_id: TASK-0610
---

# TASK-0610 — niezależny odbiór acceptance wspólnej geometrii shape v2

## Status

`done`

## Goal

Dostarczyć deterministyczny, local-only evaluator G08, który odbiera wyłącznie zamrożony corpus `acceptance` względem przypiętego rdzenia, profilu i łańcucha G05/G07 albo zwraca jawne `not_evaluable` bez aktywacji.

## Context

G00 rozdziela executor i acceptance, G02/G03 dostarczają deterministyczne lokalne sprawdzenie pikseli, a G05 i G07 wiążą kandydata z raportem replayu, regresji i transferu. Brakuje niezależnej bramki końcowej działającej poza corpusami development/calibration. Rzeczywiste artefakty acceptance są operator-owned i nie występują w repozytorium; brak nie może zostać zinterpretowany jako zaliczenie.

## Dependencies / entry conditions

- G00 (`v0.10.338`) dostarcza manifesty executor/acceptance, frozen inventory i kontrolę wycieku checksum/family.
- G02 (`v0.10.345`) i G03 (`v0.10.347`) dostarczają wersjonowany rdzeń oraz parser zamrożonego profilu preflight.
- G05 (`v0.10.350`) dostarcza checksummowany raport pilota, a G07 (`v0.10.349`) descriptor-only raport kwalifikacji.
- Założenie techniczne: jeden plik wejścia odbioru zawiera zamrożony profil preflight, wersję i konfigurację rdzenia, pełny input i anotacje G05, jego raport, raport G07 oraz acceptance truth przypięty do identyfikatorów i SHA źródeł. Brak wszystkich artefaktów acceptance zwraca `not_evaluable`; częściowy zestaw jest błędem uruchomienia, a niespójny kompletny zestaw jest odrzucony.

## Recommended execution

gpt-6-astra, xhigh — zadanie tworzy niezależną bramkę odbioru i musi zachować izolację splitów, powiązanie całego łańcucha snapshotów oraz deterministyczny replay. Niezależny audyt gpt-6-astra, medium jest obowiązkowy po implementacji; P0/P1 zatrzymuje plan, a P2/P3 trzeba naprawić i poddać re-audytowi przed zamknięciem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/SHAPE_GEOMETRY_V2_EXECUTION_PLAN.md` (G08)
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/corpus.py`
- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/preflight.py`
- `services/worker/src/game_predictor_worker/images/shape_geometry_v2/pilot.py`
- `services/api/src/game_predictor_api/domain/global_geometry_qualification.py`

## Scope

- Dodać zamknięty kontrakt wejścia i wynik lokalnego odbioru: acceptance truth, zamrożona wersja/konfiguracja rdzenia, profil preflight, pełny input i anotacje G05, jego raport oraz raport G07.
- Ponownie materializować oba frozen inventory, wymuszać `acceptance` po stronie odbioru, potwierdzać brak wspólnego checksum i capture family z executorem oraz odrzucać źródło poza zamrożonym truth.
- Zweryfikować ciąg G05 → G07 → preflight: ponownie uruchomiony G05 na przypiętym inputcie i anotacjach musi dać bajtowo identyczny pełny raport; kandydat pilota, raport kwalifikacji i profil preflight muszą wskazywać tę samą checksumę profilu, a raport G07 pilota i artefakt wejścia muszą być identyczne i checksummowane.
- Wykonać lokalną weryfikację pikseli na każdym źródle acceptance, porównać wynik z przypiętym truth, dwukrotnie odtworzyć raport oraz udostępnić command do zapisu/replay-check lokalnego raportu.
- Gdy operator nie dostarczył żadnych artefaktów acceptance, wyprodukować deterministyczny `not_evaluable`; evaluator nie zapisuje do bazy i nie wywołuje aktywacji G07.

## Out of scope

- Publikacja lub zmiana statusu profilu, import, source revisions, `game_data_v2`, endpoint, UI, migracja, dodanie rzeczywistych obrazów acceptance do repozytorium.
- Zmiana progów rdzenia, profilu G06/G07, corpusów executor, danych development/calibration lub mechanizmu korekt G05.

## Acceptance criteria

- [x] Evaluator używa wyłącznie źródeł i truthu `acceptance`; weryfikuje oba inventory i blokuje wyciek checksum lub family między executorem a acceptance.
- [x] Pełny łańcuch G05 → G07 → profil preflight → wersja i konfiguracja rdzenia jest checksummowany i zgodny: G05 jest ponownie wykonany z przypiętego inputu i anotacji, a jego pełny raport musi być bajtowo identyczny; drift lub niespójność zwraca fail-closed `rejected`.
- [x] Każde źródło acceptance jest ponownie przetwarzane przez istniejący verifier pikselowy, a wynik musi dokładnie odpowiadać truthowi przypiętemu do SHA.
- [x] Dwa replaye identycznych artefaktów dają bitowo identyczny raport; brak kompletu acceptance daje `not_evaluable`, nigdy `passed`.
- [x] Polecenie nie łączy się z bazą i nie aktywuje profilu. Testy, lint, typecheck i audyt Astra Medium potwierdzają zmianę.

## Technical notes

Nowy moduł workerowy będzie właścicielem wyłącznie lokalnego odbioru. Najpierw sprawdza komplet argumentów, następnie manifesty i inventory, granicę splitów, zamrożone wejście i cały łańcuch checksumm. Ponownie uruchamia G05 z przypiętymi anotacjami executora i porównuje cały raport kanonicznie przed odczytem acceptance. Dopiero po tych kontrolach odczytuje bajty obrazu, dekoduje je do RGB i wywołuje `verify_shape_geometry_v2_profile`. Wykonuje drugi replay w tym samym zamrożonym zakresie i porównuje kanoniczne raporty. `passed` oznacza wyłącznie zgodność odbioru — nie jest komendą aktywacji. Wyciek, konflikt profilu, dryf lub niezgodność truthu daje `rejected`; nieobecny komplet danych daje `not_evaluable`.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/images/shape_geometry_v2/acceptance.py`, `scripts/run_shape_geometry_v2_acceptance.py`, `services/worker/tests/test_shape_geometry_v2_acceptance.py`.
- Istniejące: `ai_docs/architecture/DATA_MODEL.md`, `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`, `ai_docs/process/DECISION_LOG.md`, `ai_docs/process/CURRENT_STATE.md`.

## Test cases

- Pełne, rozdzielone corpusy i identyczny truth → `passed`, stabilne checksumy raportu i drugi replay bez różnicy.
- Brak wszystkich argumentów acceptance → `not_evaluable`; podanie tylko części artefaktów → stabilny błąd uruchomienia.
- Wyciek SHA/family, drift inventory, niezgodny profil G05/G07/preflight, inna wersja lub konfiguracja rdzenia oraz niepełny truth → `rejected` bez uruchomienia aktywacji.
- Rozbieżność prawdziwego wyniku pikselowego względem truthu → `rejected`; command `--check` wykrywa zmianę istniejącego raportu.

## Verification

```powershell
# C:\Users\tuszy\.codex\worktrees\shape-geometry-v2\game_predicotr
# timeout: maks. 120 s na komendę
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m pytest services\worker\tests\test_shape_geometry_v2_acceptance.py services\worker\tests\test_shape_geometry_v2_pilot.py -q --basetemp .runtime\pytest-shape-v2-g08
C:\Users\tuszy\Documents\game_predicotr\.venv\Scripts\python.exe -m ruff check services\worker\src\game_predictor_worker\images\shape_geometry_v2\acceptance.py scripts\run_shape_geometry_v2_acceptance.py
```

## Risks / open questions

- Bez operator-owned manifestu, inventory, truthu i zamrożonych raportów evaluator zwróci `not_evaluable`; nie jest to odbiór rzeczywistego materiału ani zgoda na aktywację.
- Acceptance truth opisuje oczekiwany werdykt istniejącego bezpiecznego verifiera, nie jest treningiem modelu ani automatycznym potwierdzeniem geometrii importowej.

## Outcome

Wypełnia agent po pracy.

### Changed

- Dodano local-only evaluator G08 oraz command do zapisu i replay-check raportu.
  Zamrożone wejście przypina wersję i konfigurację rdzenia, profil preflight,
  pełny input i anotacje G05, raport G05, raport G07 oraz truth acceptance.
- Przed odczytem bajtów acceptance evaluator ponownie uruchamia G05 na
  przypiętych artefaktach i wymaga kanonicznej, bajtowej zgodności całego
  raportu. Następnie blokuje wyciek checksum/capture family, dryf inventory,
  rozbieżność łańcucha, źródeł lub truthu; nie zapisuje do bazy ani nie
  aktywuje profilu.
- Dodano regresje dla odtworzenia raportu G05, brakującej korekty, dryfu
  pełnego payloadu verifiera, zmian bajtów po zamrożeniu oraz obu wycieków
  splitów.

### Verification results

- `python -m pytest services\worker\tests\test_shape_geometry_v2_acceptance.py services\worker\tests\test_shape_geometry_v2_pilot.py -q --basetemp .runtime\pytest-shape-v2-g08-final` — 30 passed.
- Ruff check i `ruff format --check` dla modułu, commandu i testu — passed.
- Ograniczony mypy dla `acceptance.py` — passed.
- Re-audyt Astra Medium po poprawkach: brak P0–P3.

### Not completed

- Repozytorium nie zawiera operator-owned manifestu, inventory, anotacji,
  raportów i truthu rzeczywistego corpus acceptance. Bez nich command zwraca
  `not_evaluable`; nie wykonano ani nie autoryzowano aktywacji profilu.

### Documentation updates

- Uaktualniono `DATA_MODEL.md`, `VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`,
  `DECISION_LOG.md` i `CURRENT_STATE.md` o pełne odtworzenie G05 oraz granicę
  G08.

### Recommended next task

- Brak zadania implementacyjnego: G00–G08 są ukończone. Następny krok
  operacyjny to dostarczenie rzeczywistych, operator-owned artefaktów do
  niezależnego odbioru; nie jest to zgoda na aktywację.
