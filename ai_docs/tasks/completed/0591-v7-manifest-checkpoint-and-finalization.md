---
title: TASK-0591 — V7 source manifest, checkpoint and finalization
status: done
last_updated: 2026-09-21
---

# TASK-0591 — Manifest źródeł, checkpoint i finalizacja V7

## Goal

Zapewnić trwały, odtwarzalny stan skanu V7, który przypina pełny manifest
źródeł, rozpoznaje drift dowolnego źródła i tworzy raz globalne propozycje po
kompletnym EOF — bez zapisu JPEG-ów.

## Context

T03 ma czysty tracker wystąpień, a T04 ranking jakości, lecz nie posiadają
tożsamości całego folderu ani jednego checkpointu obejmującego skan,
finalizację i rezultat. Bez tej warstwy restart mógłby utracić kandydatów lub
zatwierdzić wybór po zmianie nie wybranego JPEG-a.

## Dependencies / entry conditions

- TASK-0585–0590 są ukończone.
- `LocalSourceManifest` jest jedyną kolejnością i tożsamością lokalnych JPEG-ów.
- T05 nadal nie zatwierdził kalibracji, a T06 blokuje nowe starty V7. Ten task
  nie zmienia tej bramki i nie tworzy outputu.

## Recommended execution

`gpt-6-astra`, reasoning `high`: stan skanu łączy checkpoint, manifest i
idempotentne przejścia; przed commitem wymagany jest review `gpt-6-astra`
reasoning `medium`. Eskalacja do `xhigh` jest wymagana tylko, gdy istniejący
kontrakt persistence nie pozwoli zapisać stanu bez zmiany historycznych runów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/delivery/SEMI_AUTOMATIC_SELECTION_V7_EXECUTION_PLAN.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`

## Scope

- Dodać czysty, wersjonowany `V7ScanRunState`: przypięty manifest, tracker
  T03, wyniki jakości T04, błędy pojedynczych źródeł i niezmienne propozycje
  finalizacji.
- Przypisać stałe ID źródła do indeksu, względnej ścieżki, rozmiaru i SHA z
  manifestu; kopie o identycznej zawartości na innych pozycjach pozostają
  osobnymi źródłami.
- Utrwalić pełny checkpoint oraz przywracanie: `scanning`, `paused`,
  `cancelled`, `finalization_pending`, `finalized`, `blocked_source_drift`.
- Wymagać przejścia pełnego manifestu i EOF przed globalnym rankingiem,
  weryfikować manifest ponownie przed finalizacją oraz blokować dalsze
  automatyczne działanie przy dodaniu/usunięciu/zmianie/nazwie dowolnego JPEG-a.
- Rozróżnić niezmieniony, ale niedekodowalny JPEG jako lokalny `source_error`
  od naruszenia tożsamości manifestu. Propozycje w pamięci nie są operacjami
  zapisu; T08 przypisze im journal i target.

## Out of scope

- Mutacja plików, journal/recovery outputu, API/DB/UI, ręczny wybór, OCR,
  dekodowanie obrazu, kalibracja, zmiana aktywacji V7 oraz modyfikacja danych
  użytkownika.

## Acceptance criteria

- [ ] Checkpoint po restarcie zachowuje manifest, order, dowody, jakości,
  błędy źródeł, kursory i ewentualnie już zatwierdzone propozycje.
- [ ] Finalizacja bez EOF albo bez przetworzenia każdego indeksu kończy się
  błędem; EOF nie jest automatycznie równoznaczny z utworzeniem outputu.
- [ ] Powtórzona finalizacja daje identyczne propozycje, bez nowej generacji
  decyzji i bez dublowania zakresu.
- [ ] Zmiana nawet nie wybranego pliku, kolejności, nazwy, liczby albo
  checksumy źródeł blokuje automatyczną finalizację i późniejsze wznowienie.
- [ ] Niezmieniony uszkodzony JPEG jest zapisanym błędem pojedynczego źródła;
  nie ukrywa się i nie unieważnia całego manifestu.

## Technical notes

1. `V7PinnedSourceManifest` serializuje pełny `LocalSourceManifest` bez
   absolutnego outputu oraz przyjmuje aktualny manifest tylko przy równości
   selection ID, checksumy manifestu, fingerprintu i wszystkich wpisów.
2. `consume` przyjmuje dokładnie kolejny wpis manifestu. `source_error` ma
   no-proof oraz nie może otrzymać jakości; dowód ma jakość pełnego kadru.
   Tożsamość observera jest wyprowadzana, a nie podawana z zewnątrz.
3. Po przetworzeniu ostatniego źródła `complete_scan` tylko zamyka tracker i
   przechodzi do `finalization_pending`. `finalize(current_manifest)` najpierw
   sprawdza drift, następnie wywołuje globalny ranking T04 i utrwala wynik.
   Restart pomiędzy tymi krokami ponawia finalizację deterministycznie.
4. Pause zachowuje granice occurrence; cancel nie może zostać wznowiony ani
   sfinalizowany. Wybór podglądu pozostaje wyłącznie kursorem trackera.
5. T08 będzie wymagać sfinalizowanych propozycji i ponownie sprawdzi manifest
   przed każdą mutacją filesystemu; ten task nie udaje takiej ochrony zapisem.

## Expected files

- Nowe: `services/worker/src/game_predictor_worker/semi_automatic_selection/v7_run_state.py`
- Nowe: `services/worker/tests/test_v7_run_state.py`
- Istniejące: `ai_docs/requirements/IMAGE_SELECTION.md`
- Istniejące: `ai_docs/architecture/IMAGE_SELECTION.md`
- Istniejące: `ai_docs/process/CURRENT_STATE.md`
- Istniejące: `TEMP PLAN V7.md`

## Test cases

- Pełny skan `A → B → A`, quality dla późniejszego A, EOF → wybór późniejszego
  A, jeden rezultat dla zakresu i brak cofnięcia kursora.
- Pause → checkpoint → restore → resume → EOF → finalizacja; restart po EOF,
  ale przed finalizacją, oraz ponowiona finalizacja są deterministyczne.
- Niezmieniony niedekodowalny JPEG jest zliczany jako `source_error` i pozwala
  dokończyć skan innych źródeł.
- Zmiana nie wybranego pliku, dodanie/usunięcie/zmiana nazwy i checksumy po
  checkpointcie powoduje `V7_SOURCE_MANIFEST_DRIFT` i nie zwraca propozycji.
- Checkpoint z obcą jakością, pominiętym indeksem, niedopasowanym manifestem
  albo sfinalizowanym wynikiem niezgodnym z rankingiem jest odrzucony.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests/test_v7_run_state.py services/worker/tests/test_v7_occurrences.py services/worker/tests/test_v7_quality.py -q
.\.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection/v7_run_state.py services/worker/tests/test_v7_run_state.py
```

Wynik: wszystkie testy zielone, checkpoint jest JSON-serializowalny, a self-audyt
porównuje każdy punkt Definition of Done z wynikiem przed review Astra.

## Risks / open questions

- Bramka T06 nadal blokuje produkcyjny run V7, ponieważ T05 nie uzyskał
  pomiarowej geometrii. Nie jest to blocker implementacji stanu.
- T07 wykrywa drift po dostarczeniu bieżącego manifestu; T08 musi wykonywać tę
  kontrolę w tej samej krytycznej sekcji co publication.

## Outcome

### Changed

- Dodano czysty `V7ScanRunState` z pełnym, checksum-bound manifestem źródeł,
  stałym source ID, checkpointem JSON i odtwarzalnymi fazami skanu.
- Skan zachowuje jakość każdego zdekodowanego źródła, jawne `source_error`,
  occurrence T03 i kursory. `complete_scan` wymaga przetworzenia wszystkich
  wpisów, a `finalize` tworzy wyłącznie propozycje z rankingu T04.
- Finalizacja jest idempotentna i sprawdza kompletny bieżący manifest. Drift
  dowolnego wpisu blokuje automat, lecz zachowuje już utworzone historyczne
  propozycje wyłącznie do odczytu; restart odtwarza blokadę.

### Verification results

- `pytest services/worker/tests/test_v7_run_state.py services/worker/tests/test_v7_occurrences.py services/worker/tests/test_v7_quality.py -q` — 37 passed.
- `ruff format --check` oraz `ruff check` dla zmienionego modułu i testu — PASS.
- `mypy --ignore-missing-imports --follow-imports=skip .../v7_run_state.py` — PASS.
- Self-audyt sprawdził EOF, restart, pauzę/anulowanie, 3+3, źródło
  niedekodowalne, zmianę/rename/dodanie/usunięcie niewybranego JPEG-a oraz
  checksumę sfinalizowanych propozycji.
- Astra Medium znalazła P1: drift po wcześniejszej finalizacji dawał checkpoint
  nieodtwarzalny. Poprawiono stan `blocked_source_drift`, dodano test regresji;
  końcowy re-review Astra: APPROVED.

### Not completed

- Nie dodano operacji outputu, journala, locka katalogu, API/DB ani UI. T08
  podłączy stan do krytycznej sekcji publication i ponowi kontrolę manifestu
  pod lockiem. V7 pozostaje zablokowane przez gate T06/T12.

### Documentation updates

- Uzupełniono kontrakt trwałego skanu w wymaganiach i architekturze.
- Zaktualizowano `CURRENT_STATE.md` i `TEMP PLAN V7.md`.

### Recommended next task

- TASK-0592 / T08: journal pierwszego zapisu, generacje, właściciel targetu,
  wspólny lock i recovery po awarii.
