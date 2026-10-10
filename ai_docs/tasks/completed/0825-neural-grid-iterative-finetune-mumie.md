---
title: TASK-0825 — iteracyjne doszkalanie neural_grid na Mumiach (run 3) i automatyczne zamykanie zdjęć
status: done
last_updated: 2026-10-02
---

# TASK-0825 — iteracyjne doszkalanie neural_grid na Mumiach

## Status

`done`

## Goal

Pętla „operator akceptuje porcję zdjęć Mumii → krótkie doszkolenie modelu
runu 1 → nowe propozycje dla pozostałych zdjęć → pomiar” działa jedną
komendą na iterację, mieści wszystkie doszkolenia w 4 godzinach GPU
trzeciego runu i raportuje po każdej iteracji wynik na odłożonych zdjęciach
Mumii oraz na development 777.

## Context

D-490 z uzupełnieniem z 2026-10-02: run 3 to iteracyjne doszkalanie na
Mumiach (Blazing i Gang wypadają z tej tury). Operator anotuje w narzędziu
TASK-0824 (`http://127.0.0.1:8105`); ma już kilka zdjęć z zaakceptowanymi
wszystkimi planszami, ale bez potwierdzonego zamknięcia zdjęcia.

## Dependencies / entry conditions

- Model runu 1: run `43933ac8d7d443c8b9079630a83de2e6`, najlepszy stan
  (runda 3), eksport `exports\2cd19738367121e6-round3`.
- Snapshot 777 v2 `production-geometry-snapshots\286f2e37…df59`.
- Magazyn anotacji labu z `assisted_photos` (TASK-0824); eksport kompletnych
  zdjęć i adapter `write_reader_snapshot`.
- Budżet D-481: dwa runy treningowe wykorzystane (A, B); trzeci run = ten
  iteracyjny, łącznie do 14 400 s.
- GPU może być zajęte runem 2 do ok. 20:30 — wykonawca nie używa GPU,
  dopóki run 2 jest aktywny.

## Recommended execution

`claude-opus-5-5`, reasoning `high`. Zmiana protokołu runów (jeden run,
wiele iteracji, trwały budżet), doszkalanie bez zapominania 777 i uczciwy
pomiar na odłożonych zdjęciach. Audyt zawieszony decyzją operatora
(2026-10-01).

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/DECISION_LOG.md` (D-490, D-481, D-483, D-484)
- `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`
- `ai_docs/tasks/0802-neural-grid-whole-screen-network.md`,
  `ai_docs/tasks/completed/0824-lab-assisted-complete-photo-annotation.md`
- `ai_docs/guides/VISION_LAB_LOCAL.md`

## Scope

1. **Narzędzie anotacji:** zdjęcie zamyka się automatycznie, gdy operator
   zaakceptował wszystkie jego plansze (wszystkie nieodrzucone propozycje i
   dodane plansze są zaakceptowane, brak cofniętych akceptacji) i przechodzi
   do następnego zdjęcia; liczba plansz = liczba zaakceptowanych. Jawne
   potwierdzenie liczby (`C`) zostaje jako możliwość korekty. Jednorazowa
   komenda zamykająca zdjęcia, które już spełniają ten warunek (istniejąca
   praca operatora), z podglądem. Kolejka i liczniki ograniczone do Mumii
   (Blazing i Gang ukryte przełącznikiem, dane nietknięte).
2. **Preset D (doszkalanie):** start z wag najlepszego stanu runu 1; dane
   iteracji = zdjęcia Mumii roli „train” + próbka 777 z roli `training`
   snapshotu v2 (żeby nie zapomnieć 777); zapisany fingerprint; parametry
   (LR, liczba kroków albo czas iteracji, proporcja Mumie:777, augmentacje)
   ustalone przed pierwszą iteracją.
3. **Podział zdjęć Mumii:** deterministyczny — co piąte zakończone zdjęcie
   (według stabilnego klucza, nie kolejności klikania) trafia do roli
   „holdout” i nigdy do doszkalania; przydział raz nadany jest trwały.
4. **Protokół:** trzeci run budżetu jako jeden run z wieloma iteracjami;
   `used_seconds` trwałe między iteracjami; twardy limit 14 400 s łącznie;
   każda iteracja ma własny checkpoint i raport; wznowienie po przerwaniu.
5. **Komenda iteracji** (jedna): eksport kompletnych zdjęć → snapshot
   iteracji → doszkolenie (domyślnie do 15 minut) → ocena → eksport ONNX →
   nowe propozycje dla zdjęć jeszcze niekompletnych → raport.
6. **Pomiar po iteracji:** na holdoucie Mumii (metryki D-483 względem
   siatek operatora), na development 777 (brak pogorszenia względem runu
   1), oraz „trafność propozycji”: dla zdjęć zaakceptowanych w ostatniej
   porcji — jaki odsetek plansz operator przyjął bez zmian, a jaki
   poprawił (z pochodzenia etykiet), jako miara, czy kolejne porcje idą
   szybciej.
7. Raport i wpis w przewodniku.

## Out of scope

- Blazing, Gang, Reels, Treasure; rola `gold`; symbole; aplikacja
  produkcyjna; pobieranie wag z internetu; TASK-0804.

## Acceptance criteria

- [ ] Automatyczne zamykanie zdjęcia działa i nie zamyka zdjęcia z
      niezaakceptowaną albo cofniętą planszą; istniejące zdjęcia spełniające
      warunek zamyka komenda z podglądem; test.
- [ ] Holdout Mumii jest deterministyczny, trwały i nigdy nie trafia do
      danych doszkalania (strażnik + test).
- [ ] Budżet: suma czasu wszystkich iteracji ≤ 14 400 s, egzekwowana kodem;
      nie da się uruchomić czwartego runu ani iteracji po wyczerpaniu
      budżetu; smoke nie zużywa budżetu i ma ≤ 50 kroków.
- [ ] Iteracja jest wznawialna i idempotentna (powtórzenie po przerwaniu
      nie liczy czasu podwójnie i nie gubi checkpointu).
- [ ] Raport iteracji zawiera trzy pomiary ze Scope pkt 6; ocena na
      development 777 pokazuje różnicę względem runu 1.
- [ ] Nowe propozycje są osobnym, niezmiennym zbiorem z identyfikatorem
      modelu; narzędzie pokazuje najnowszy zbiór dla zdjęć niekompletnych, a
      zaakceptowane plansze zachowują pochodzenie ze swojego zbioru.
- [ ] Runy 1 i 2, ich eksporty i snapshoty nietknięte.
- [ ] Laboratorium nadal nie importuje `storage` ani `psycopg`.
- [x] Osobny commit, `Outcome`, `CURRENT_STATE.md`.

## Technical notes

- Przy małej liczbie zdjęć Mumii (10–100) doszkalanie łatwo przeucza:
  mały LR (rząd 1e-4), mieszane wsady z 777, pełne augmentacje presetu B,
  wybór stanu iteracji według holdoutu Mumii pod warunkiem braku
  pogorszenia development 777 o więcej niż 0,5 pkt proc. zdjęć kompletnych
  i poprawnych; gdy holdout jest pusty albo ma < 3 zdjęcia (pierwsza
  iteracja), bierz stan końcowy i zaznacz to w raporcie.
- Stopień 1 (ekran) na zdjęciach Mumii: wszystkie plansze zdjęcia są
  oznaczone (zdjęcie kompletne), więc brak etykiety = tło — dlatego do
  doszkalania wchodzą tylko zdjęcia zamknięte.
- Kolejne iteracje startują z najlepszego stanu poprzedniej iteracji.
- Serwer narzędzia anotacji trzyma blokadę magazynu przy zapisie; eksport
  musi czytać stan bez konfliktu z działającym serwerem (krótka blokada z
  ponowieniem albo odczyt przez API serwera) — nie wymagaj zatrzymania
  pracy operatora na czas całej iteracji. Odświeżenie propozycji w
  działającym serwerze: przeładowanie zbioru bez restartu albo jawny,
  szybki restart opisany w raporcie.
- Sprzęt: RTX 4050 6 GB; rozmiar wsadu jak w presetach A/B.

## Expected files

- Istniejące: `vision_lab/neural_grid_protocol.py`, `neural_grid_training.py`,
  `neural_grid_runs.py`, `neural_grid_data.py`, `assisted_annotation.py`,
  `assisted_annotation_page.py`, `scripts/vision_lab_assisted_annotation.ps1`.
- Nowe (proponowane): `vision_lab/neural_grid_presets/D.json`,
  `vision_lab/neural_grid_finetune.py`, testy, sekcja w
  `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest services/worker/tests -q -p no:cacheprovider -k "neural_grid or assisted_annotation or no_production_storage_imports"
.\.venv\Scripts\python.exe -m ruff check services scripts
```

Smoke doszkalania na GPU (≤ 50 kroków) dopiero po zakończeniu runu 2.

## Risks / open questions

- Holdout z pierwszych porcji będzie bardzo mały; wyniki pierwszych
  iteracji mają szeroki margines.

## Outcome

Wykonano 2026-10-02 (implementer, worktree `grid-engine-v3`, bez commita).

### Changed

- `vision_lab/neural_grid_protocol.py`: preset D (`FinetunePreset`, `FinetuneInit`,
  pole `Preset.finetune` tylko dla D, `pretrained` = wagi runu 1), fingerprint D w
  `FROZEN_PRESET_FINGERPRINTS`, `NeuralGridRunRequest.preset` przyjmuje D. A/B/C,
  `METRIC_DEFINITION` i `admit_run` bez zmian zachowania.
- Nowy `vision_lab/neural_grid_presets/D.json` (fingerprint
  `b94a9627df4c2d0886b43776f1a80b406de5d124c36c997ada2b5f93c5d1cbd9`).
- Nowy `vision_lab/neural_grid_finetune.py`: reguły (holdout, wybór stanu, czas
  iteracji, mieszane wsady, trafność propozycji), ledger, worker iteracji (GPU),
  komendy `iterate` i `status`.
- `neural_grid_runs.py`: worker runu D wykonuje iterację (`run_iteration_attempt`);
  `neural_grid_training.train_run` odmawia presetu D.
- `assisted_annotation.py`: `completion_readiness`, automatyczne zamykanie po
  akceptacji (`Decision.auto_complete`, `Workspace.decide_with_auto`), komenda
  `close-finished` (podgląd / `--apply`), `read_store_state` (krótka blokada),
  wiele zbiorów propozycji (`generation`, `merge_proposal_sets`, `open_proposals`,
  przeładowanie bez restartu), `--games`, `write_export(..., games)`,
  `proposalSetId` w eksporcie, idempotentny `write_reader_snapshot`.
- `assisted_annotation_page.py`: auto-zamykanie i przejście dalej, ukryte gry,
  generacja propozycji, opis `C` jako korekty.
- `scripts/vision_lab_assisted_annotation.ps1`: `-Games` (domyślnie `mumie`),
  `-Action CloseFinished [-Apply]`.
- Testy: nowy `services/worker/tests/test_vision_lab_neural_grid_finetune.py`,
  3 nowe testy w `test_vision_lab_assisted_annotation.py`.

### Verification results

- `pytest services/worker/tests -k "neural_grid or assisted_annotation or no_production_storage_imports"`:
  38 passed (w tym 8 nowych testów doszkalania, z testem całej komendy `iterate` na CPU:
  dwie iteracje, wznowienie po `--no-wait`, odmowa bez nowych danych, holdout poza
  treningiem, osobny zbiór propozycji; 3 nowe testy strony). Regresja
  `test_vision_lab_runs.py` + `test_vision_lab_hybrid.py`: 30 passed.
- `ruff check services scripts`: jedyny błąd to istniejący wcześniej E501 w
  `test_page_geometry_preflight.py:345`. `mypy --strict` zmienionych modułów: bez błędów
  w `vision_lab` (zgłoszenia tylko w niezwiązanych modułach API). JS strony: `node --check`
  OK. `check_powershell_syntax.ps1`: OK.
- Smoke GPU po zakończeniu runu 2 (kopie w `%TEMP%\ng825`): run smoke
  `cf04f19d…`, 40 kroków, 174 s, checkpoint iteracji, eksport ONNX z parity PASS,
  zbiór propozycji generacji 1 (226 zdjęć, 55 s), raport. Szczegóły w raporcie
  jakości, sekcja „Run 3”.
- Strona na 8106 (kopie, tylko Mumie): 236 zdjęć, ukryte Blazing i Gang, nowy zbiór dla
  niezamkniętych, bazowy dla zamkniętych; proces zatrzymany.
- Prawdziwe dane: katalog propozycji ma nadal jeden zbiór; katalog runów bez nowych
  wpisów; magazyn czytany tylko przez kopię pod krótką blokadą (0,03 s).

### Not completed

- Commit, `CURRENT_STATE.md`, przeniesienie taska — orkiestrator.
- Pierwsza prawdziwa iteracja (zużywa budżet runu 3) — orkiestrator po porcji
  operatora.
- Decyzje wykonawcze do potwierdzenia: (1) automatyczne zamknięcie wymaga co najmniej
  jednej planszy zaakceptowanej w narzędziu — 11 zdjęć Mumii wyłącznie z wcześniejszą
  pracą labu nie jest zamykanych (`ASSISTED_NO_WORKFLOW_ACCEPTANCE`); (2) czas treningu
  iteracji rośnie z liczbą zdjęć (60 s/zdjęcie, 300–900 s) zamiast stałych 15 min;
  (3) gdy żaden kandydat nie spełnia warunku 777, stan poprzedni zostaje, a eksport i
  propozycje są pomijane; (4) iteracja bez nowych zamkniętych zdjęć jest odrzucana
  (`--allow-same-data` wymusza).
- Strona 8105 operatora działa na kodzie `v1.7.170`: nowe zachowanie wymaga jej
  restartu (Stop/Start skryptem).

### Documentation updates

- `ai_docs/quality/GRID_V3_NEURAL_GRID_RUNS_20261002.md`: sekcja „Run 3 (preset D)”.
- `ai_docs/guides/VISION_LAB_LOCAL.md`: podsekcja TASK-0825 w części o kompletnych
  zdjęciach i sekcja „Iteracyjne doszkalanie neural_grid na Mumiach”.

### Recommended next task

- Restart strony z nowym kodem, `CloseFinished`, pierwsza iteracja po ok. 10
  zamkniętych zdjęciach Mumii.

### Preset E (uzupełnienie po iteracji 1, D-490)

- Iteracja 1 presetu D (run `5bc981568c3f42bd96f6f9238e57aedc`, 682 s z 14 400 s):
  wszyscy trzej kandydaci odrzuceni przez strażnik D (development 777 91,0–91,5% przy
  progu 91,83%), stan runu 1 bez zmian. Operator przyjął nowe reguły po obejrzeniu
  wyniku (D-490, „Zmiana reguł doszkalania po iteracji 1”).
- Nowy preset reguł `neural_grid_presets/E.json`, fingerprint
  `f8f8559be24eae43f483380ad87b81715480ce16983ee27a9c91938e5765a7bc`: identyczny z D
  poza `finetune.guard_777` — (a) poziom B development 777 ≥ run 1 (298/300) − 0,5 pkt
  proc., (b) image-macro ≤ 0,0028703064783595768, (c) wykrycie 100% i 0 fałszywych;
  wybór: najniższe image-macro holdoutu Mumii (mały holdout: ta sama reguła z
  oznaczeniem w raporcie). A–D i metryki D-483 bez zmian.
- Ciągłość budżetu: E nigdy nie jest presetem runu (`NEURAL_GRID_RULES_PRESET_NOT_A_RUN`);
  iteracja 2 to kolejna próba tego samego runu D, `used_seconds` przechodzi,
  `admit_run` dalej odmawia czwartego runu. Ledger zapisuje `rules_revisions` przy
  planowaniu iteracji 2, plan i historia niosą `rules`, worker sprawdza zamrożony
  fingerprint E i równoważność treningu z D. Iteracja po iteracji bez wybranego stanu
  może użyć tych samych zdjęć (`same_data`, powód `previous_iteration_selected_no_state`).
- Testy: 6 nowych (preset E, każdy warunek strażnika osobno, wybór po image-macro
  holdoutu, liczby iteracji 1, ciągłość runu i budżetu przy D→E, komenda `iterate` na
  CPU: iteracja 2 na tych samych danych pod E w tym samym runie); zestaw
  `neural_grid or assisted_annotation or no_production_storage_imports`: 44 passed.
- Sprawdzenie tylko do odczytu na historii checkpointu iteracji 1: poziom B 300/300 u
  wszystkich kandydatów, strażnik E dopuściłby wszystkich, wybór → kandydat 3.
  Iteracja 2 nieuruchomiona.

### Preset F (uzupełnienie po iteracji 3, D-490)

- W iteracji 3 wszyscy kandydaci byli na holdoucie gorsi od stanu początkowego
  (image-macro 0,00274 → 0,00330 / 0,00337 / 0,00336), a preset E wybrał kandydata 1.
- Nowy zamrożony preset reguł `neural_grid_presets/F.json`, fingerprint
  `821bcdca5b9dcaedcb245f7097fb9101f903852d4448744ccfd72c91b0d59d72`: jak E, ale
  kandydat jest wybierany tylko, gdy jego image-macro holdoutu jest ściśle niższe niż
  stanu początkowego tej samej iteracji; inaczej poprzedni stan zostaje
  (`previous_state_kept_no_holdout_improvement`), bez eksportu ONNX i bez nowych
  propozycji; raport to zapisuje, mała próba (< 3 zdjęć) jest oznaczana jak w E.
- F obowiązuje od iteracji 4 tego samego runu i budżetu (mechanizm D→E: wpis
  `rules_revisions` z fingerprintami F i E oraz powodem, plan niesie `rules`); nie może
  być presetem runu. Iteracje 1–3 i presety A–E bez zmian.
- Testy: 4 nowe (preset F zamrożony i równoważny treningowo, odrzucenie bez poprawy,
  wybór poprawiającego kandydata, przełączenie E→F od iteracji 4 z ciągłością budżetu);
  zestaw `neural_grid or assisted_annotation or no_production_storage_imports`:
  48 passed; ruff check/format i mypy --strict zmienionych modułów bez błędów.
  Żadna iteracja pod F nie została uruchomiona.
