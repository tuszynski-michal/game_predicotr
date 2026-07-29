---
title: Milestone 06 execution plan
status: in_progress
last_updated: 2026-07-29
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

`reviewed_v16_label_bootstrap` — rzeczywiste etykietowanie obaliło generalizację
D-061. P95 `1.8337 px` mierzył dopasowanie na 27 anchorach użytych do budowy
profili, a nie pozostałe plansze. `board-cell-crops-v2-calibrated-v1` jest
wycofane z treningu.

TASK-0098 zbudował lokalne profile per source image, ale ręczna bramka `25/25`
ujawniła przecięcia symboli na 18 planszach, w tym na wszystkich 9 held-out.
TASK-0101 odrzucił produkcyjne v7 po pełnej kontroli właściciela. Kandydat
`expanded-frame-centered-symbol-mesh-spike-v4` przeszedł techniczny preflight
dla `385/387` plansz, ale właściciel wskazał dalsze błędy już w pierwszych 30
sekwencjach i przerwał kosztowny pełny przegląd. Spiki v5–v8 potwierdziły, że
nie każdą komórkę da się odzyskać geometrią: poszerzenie może wprowadzić
sąsiedni symbol albo kontrolkę interfejsu. Następna bramka klasyfikuje jakość
per komórka; tylko pełny i izolowany symbol jest training-eligible, a
clipped/occluded/interface-contaminated trafia do pełnolayoutowego review.
Właściciel zaakceptował pełny v16: 387 plansz, 5805 komórek i zero fallbacków.
TASK-0097 zakończył się reprezentatywną partią 416 etykiet z 24 kompletnych
plansz, 18 zdjęć i obu source sessions. TASK-0059 wydał niepusty dataset
`ready`. Zachowanych 56 decyzji v2 nie jest automatycznie migrowanych.
Następny TASK-0060 tworzy source-aware split i raport jakości; TASK-0099 doda
top-3 sugestie dopiero po pierwszym modelu i bez auto-accept.

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

- `TASK-0059 — Labeled symbol dataset export` — done 2026-07-29; accepted v16
  export contains 416 reviewed samples and 416 content-addressed assets
- `TASK-0093 — Bootstrap symbol label review tool` — done 2026-07-28;
  technical spike retained, single-crop UX will be replaced
- `TASK-0097 — Whole-layout assisted symbol labeling` — done 2026-07-29;
  24 complete boards across 18 source images and both sessions produced 416
  explicit accepted decisions; 56 v2 decisions remain preserved as history
- `TASK-0098 — Local image grid calibration and held-out gate` — superseded in
  production geometry by D-063; its immutable review evidence remains retained
- `TASK-0100 — Symbol-aware grid refinement spike` — done; owner accepted the
  25-board visual comparison
- `TASK-0101 — Production symbol-aware crops and geometry gate` — done;
  deterministic v7, v4 and experimental v5–v8 crops were rejected; a
  pixel-only v1 gate still produced 14 false accepts on the exact v4 feedback,
  and candidate v9 was rejected on sequence 29 because an axis-aligned wide
  frame discarded detector perspective. The accepted corrective sequence is:
  perspective-preserving detector-quad expansion, guarded 5 × 3 symbol-lattice
  homography, then a fixed-padding regression gate on selected failures and
  controls before any full-corpus run. Step 1 passes the sequence-29
  regression under immutable v11. Step 2 is implemented as
  `symbol-lattice-homography-ransac-v1`: sequence 29 has `14/15` reliable
  candidates, 13 inliers spanning 3 × 5 and P95 `7.6869 px`. It derives
  virtual corners from all inliers. Step 3 rectifies with a fixed `10 px`
  canonical inset and proves source-pixel support. Sequence 29 passed first,
  but the bounded gate passed only `13/20`: `7`, `30`, `3`, `11`, `16`, `17`,
  `28` stopped fail-closed, while visual inspection still rejects routed
  sequences `4` and `26`. The gate is rejected. The next correction replaces
  slot-local centre proposals with global candidates and explicit robust
  assignment to 5 × 3. V13 implements that assignment and composes the final
  warp back to the normalized source rather than treating the 500 × 300
  analysis plane as a pixel boundary. The required regression now passes
  `18/20`; `29` and all reported `4`, `6`, `7`, `26`, `30` pass with support
  `1.0`, while controls `3` and `11` remain fail-closed. V14 adds one bounded
  `boundingBox` analysis retry only for three global-locator failures; it does
  not use the rectangle as final cell geometry and keeps all homography and
  real-source support guards. The bounded gate now passes technically `20/20`,
  only `3` and `11` use the retry, and the other 18 cards are unchanged from
  v13. The owner accepted that gallery on 2026-07-29. The subsequent full
  preflight processed `387/387`, produced supported cells for `373` boards and
  failed closed on 14 sequences. Those 14 cases require a bounded correction
  before the required `5805/5805` production corpus and page-level review
- `TASK-0099 — Safe bootstrap symbol suggestions` — todo after TASK-0098
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
| M6.1 Dataset symboli | TASK-0059–0060, TASK-0093, TASK-0097–0099 | 6 |
| M6.2 Model i ONNX | TASK-0061–0063 | 3 |
| M6.3 Manual review | TASK-0064–0066 | 3 |
| M6.4 Odbiór klasyfikacji | TASK-0067 | 1 |
| **Razem M6** | **TASK-0059–0067 + TASK-0093, TASK-0097–0099** | **13** |

## Następny milestone

Po przejściu G6 i poleceniu właściciela obowiązuje
`MILESTONE_07_EXECUTION_PLAN.md`.
