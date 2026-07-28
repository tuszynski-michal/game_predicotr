---
title: Milestone 06 execution plan
status: in_progress
last_updated: 2026-07-28
---

# Plan wykonania Milestone 06 — Symbol classifier and review workflow

## Cel

Zbudować wersjonowany klasyfikator symboli, lokalną inferencję ONNX oraz pełny
manual review. Korekty administratora mają tworzyć audytowalny zbiór
oznaczonych przykładów, a nie bezpośrednio modyfikować opublikowane dane.

`ROADMAP.md` jest właścicielem granic milestone’u, a ten dokument jest
właścicielem kolejności podetapów, rezerwacji zadań i bramek jakości M6.

## Relevant docs

- `requirements/IMAGE_INGESTION.md`
- `requirements/ADMIN_APP.md`
- `architecture/SYSTEM_ARCHITECTURE.md`
- `architecture/DATA_MODEL.md`
- `architecture/API_CONTRACT.md`
- `architecture/TECH_STACK.md`
- `quality/TEST_STRATEGY.md`
- D-006, D-010, D-014, D-057–D-061 w `process/DECISION_LOG.md`

## Warunki wejścia

- M5 przechodzi G5.
- Q-017 jest zamknięte i dostępny jest wystarczający materiał na każdy symbol.
- Geometria wycinków ma zaakceptowany, wersjonowany kontrakt.

### Bieżący status

`active_whole_layout_bootstrap` — Q-017 pozostaje zamknięte, a OCR nadal działa
jako `manual_review_only`. Historyczne `board-cell-crops-v1` oraz detektorowy
wariant v2 pozostają w kwarantannie. TASK-0094–0096 zakończyły korektę M5.3:
skalibrowany korpus ma 5805 komórek, pełne pochodzenie profili,
`trainingAllowed = true` i P95 linii `1.8337 px`.

TASK-0097 zastępuje jednokafelkowy spike pełnolayoutowym review 5 × 3 i tworzy
pierwsze rzeczywiste decyzje potrzebne do dokończenia TASK-0059.
Warstwa techniczna TASK-0097 jest gotowa: deterministyczny inwentarz v2 ma
5805 skalibrowanych komórek, a loopback UI obsługuje 387 plansz. Zadanie
pozostaje aktywne do ręcznego oznaczenia pierwszej reprezentatywnej partii
15–30 plansz przez właściciela.

## Zasady realizacji

- podział train/validation/test odbywa się według zdjęcia źródłowego,
- wagi i modele są wersjonowane i dostępne lokalnie,
- metryki per symbol mają pierwszeństwo przed samą accuracy globalną,
- korekta manualna tworzy audyt i nową wersję datasetu treningowego,
- trening jest batchowy; pojedyncza decyzja nie mutuje aktywnego modelu,
- active learning może ustalać priorytet review, ale nie omija kalibracji
  auto-accept na held-out,
- staging i opublikowane dane nie są modyfikowane bez śladu,
- plik zadania powstaje bezpośrednio przed rozpoczęciem zakresu.

## M6.1 — Wersjonowany dataset symboli

### Zakres

- eksport wycinków i etykiet,
- bezetykietowy inwentarz cropów oraz osobny kontrakt decyzji review,
- stabilne powiązanie z source image,
- deduplikacja i checksumy,
- podział train/validation/test według zdjęcia źródłowego,
- manifest wersji datasetu,
- kontrola liczności i jakości per symbol.

### Zadania

- `TASK-0059 — Labeled symbol dataset export` — calibrated crops accepted;
  blocked only on reviewed labels from TASK-0097
- `TASK-0093 — Bootstrap symbol label review tool` — done 2026-07-28;
  technical spike retained, single-crop UX will be replaced
- `TASK-0097 — Whole-layout assisted symbol labeling` — in progress; software
  ready, awaiting the first owner-reviewed 15–30 boards
- `TASK-0060 — Dataset split, manifest and quality validation`

### Bramka G6.1

- żaden wycinek ze zdjęcia walidacyjnego nie występuje w treningu,
- etykiety wskazują stabilne symbole tej samej gry,
- liczność i źródła są raportowane per symbol,
- ponowny eksport tych samych decyzji daje ten sam logiczny dataset,
- brakujące klasy blokują trening wersji przeznaczonej do odbioru.

## M6.2 — Trening, ONNX i confidence

### Zakres

- powtarzalny trening PyTorch/torchvision,
- początkowy batch z orientacyjnie 15–30 pełnych layoutów pochodzących z
  różnych zdjęć i pozycji,
- zapis konfiguracji, seedów i wag,
- metryki per symbol oraz confusion matrix,
- eksport ONNX,
- test parytetu PyTorch–ONNX,
- lokalny adapter ONNX Runtime,
- kalibracja confidence i lista alternatyw,
- wersjonowany wybór najbardziej niepewnych albo reprezentatywnych przypadków
  do kolejnego batcha review.

### Zadania

- `TASK-0061 — Versioned batch symbol classifier baseline`
- `TASK-0062 — ONNX export and local inference parity`
- `TASK-0063 — Confidence calibration and active-learning review selection`

### Bramka G6.2

- wynik treningu wskazuje dataset, kod i konfigurację,
- metryki nie są liczone na przeciekającym zbiorze,
- ONNX daje wyniki zgodne w zaakceptowanej tolerancji,
- inferencja nie pobiera wag z sieci,
- progi auto-accept/review/reject są mierzalne i zapisane,
- wybór active-learning jest odtwarzalny dla tej samej wersji modelu i danych,
- decyzja człowieka trafia do następnego datasetu/modelu, a nie zmienia
  działającego modelu online,
- słaba klasa nie jest ukrywana przez samą accuracy globalną.

## M6.3 — Manual review end to end

### Zakres

- trwały `review_item`,
- oryginał, pełny layout 5 × 3, siatka i crop komórki,
- osobny tryb korekty geometrii przed decyzją symbolu,
- predicted value, confidence i alternatywy,
- approve/correct/reject,
- audyt rozwiązania,
- idempotentne zapisanie korekty,
- eksport korekt jako oznaczonych przykładów.

### Zadania

- `TASK-0064 — Review storage and Admin API`
- `TASK-0065 — Manual review administration UI`
- `TASK-0066 — Review corrections and labeled feedback export`

### Bramka G6.3

- administrator może odtworzyć kontekst każdej decyzji,
- nie można zapisać symbolu dla cropu z niezaakceptowaną geometrią,
- ta sama akcja nie tworzy dwóch korekt,
- odrzucony element nie trafia do publikacji,
- corrected symbol należy do właściwej gry,
- zmiana decyzji pozostawia audyt,
- dane treningowe są nową wersją, a nie mutacją starego zbioru.

## M6.4 — Zintegrowany odbiór klasyfikacji

### Zakres

- obraz → zaakceptowana geometria → cell crops → ONNX → review,
- raport jakości automatycznej i po review,
- czas inferencji i udział manual review,
- dokumentacja ponownego treningu i rollback modelu.

### Zadanie

- `TASK-0067 — Classifier and review vertical slice acceptance`

### Bramka G6

- pełny golden corpus przechodzi wersjonowaną inferencję,
- osiągnięte są zaakceptowane progi per symbol albo etap wraca do treningu,
- każdy wynik ma model version i confidence,
- manual review rozwiązuje wszystkie typy niepewności przewidziane kontraktem,
- korekty dają nową wersję datasetu treningowego,
- nie rozpoczęto jeszcze masowego, wielogodzinnego importu.

## Mapa zadań M6

| Podetap | Zadania | Liczba |
|---|---:|---:|
| M6.1 Dataset symboli | TASK-0059–0060, TASK-0093, TASK-0097 | 4 |
| M6.2 Model i ONNX | TASK-0061–0063 | 3 |
| M6.3 Manual review | TASK-0064–0066 | 3 |
| M6.4 Odbiór klasyfikacji | TASK-0067 | 1 |
| **Razem M6** | **TASK-0059–0067 + TASK-0093, TASK-0097** | **11** |

## Następny milestone

Po przejściu G6 i poleceniu właściciela obowiązuje
`MILESTONE_07_EXECUTION_PLAN.md`.
