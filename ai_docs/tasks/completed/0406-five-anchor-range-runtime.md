---
title: TASK-0406 — Runtime OCR pięciu anchorów zakresu
status: done
created: 2026-09-02
---

# TASK-0406 — Runtime OCR pięciu anchorów zakresu

## Goal

Połączyć gotowy lokalizator i proof v6 w odizolowany, recognition-only runtime:
`EXIF source → pięć source-direct cropów → bounded Paddle OCR → exact/unknown`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/tasks/completed/0404-five-anchor-range-label-locator.md`
- `ai_docs/tasks/completed/0405-five-anchor-range-proof.md`

## Scope

- Dodać fingerprintowany runtime v6 oraz kontrakt batcha źródeł.
- Kanonizować EXIF dokładnie raz i przekazywać wyłącznie kanonizowane RGB do
  lokalizatora v6.
- Stosować lekki, lokalny gate czytelności cropów przed OCR. Niejakościowy crop
  kończy się `unknown`, bez próby naprawiania cyfr.
- Użyć istniejącego recognition-only adaptera Paddle, z maksymalnie dziewięcioma
  cropami na wewnętrzny batch i maksymalnie sześcioma źródłami na batch runtime'u.
- Zwracać stabilny `RangeEvidenceResult`, telemetryczne diagnostyki i
  observation key, zachowując kolejność źródeł.
- Dodać testy mapowania pięciu cropów, batchingu, EXIF, clippingu/blur/conflictu,
  stabilności fingerprintu i izolacji od joba/geometrii/symboli.

## Out of scope

- Rejestracja fingerprintu w durable jobie, checkpoint, grouping, rollout,
  feature flag, API i UI.
- Zmiana v1–v5, ich fingerprintów albo historycznych retry.
- Board detection, geometria plansz/komórek, cropper plansz lub symbol inference.

## Invariants

- Runtime nie zna nazwy pliku, expected filename, source indexu jako dowodu ani
  sąsiadów; expected table służy wyłącznie proofowi ustalonemu z granic runu.
- Każdy wynik jest `exact` wyłącznie przez resolver TASK-0405 albo jest
  reason-coded `unknown`.
- Pełne zdjęcie nie jest trwale zapisywane; runtime nie wykonuje I/O poza
  otrzymanymi bajtami i nie tworzy jobów.
- Nieczytelność, niekompletność albo konflikt nie jest zamieniany w inferencję
  zakresu.

## Acceptance criteria

- [x] Bounded batch zwraca source-ordered exact/unknown dla pięciu anchorów.
- [x] Każdy wynik posiada nowy fingerprint i checksum-bound observation key.
- [x] OCR nie jest wykonywany dla cropów, które nie przechodzą lokalnej bramki
  czytelności, a znane conflict/blur pozostają manualne.
- [x] Testy potwierdzają brak wywołań jobów, geometrii, croppera i inferencji
  symboli.

## Verification

```powershell
.venv\Scripts\python.exe -m pytest services/worker/tests/test_five_anchor_range_runtime.py services/worker/tests/test_five_anchor_range_proof.py services/worker/tests/test_five_anchor_range_label_locator.py -q
.venv\Scripts\python.exe -m ruff check services/worker/src/game_predictor_worker/semi_automatic_selection services/worker/tests/test_five_anchor_range_runtime.py
.venv\Scripts\python.exe -m mypy services/worker/src/game_predictor_worker/semi_automatic_selection/five_anchor_range_runtime.py
```

## Outcome

Ukończono 2026-09-02. Runtime v6 zwraca wyłącznie source-ordered evidence
z pięciu cropów. Ma niezależny fingerprint, observation key oraz bounded
batching: sześć źródeł i maksymalnie dziewięć cropów Paddle jednocześnie.
Źródło z niewyraźnym cropem kończy się przed OCR jako `LOCAL_BLUR`; conflict
OCR pozostaje manualnym `unknown`.

Nie zmieniono durable joba, checkpointu, registry fingerprintów, API ani UI.
Historyczne v1–v5 nie są przez ten kod importowane lub przełączane.
