---
title: TASK-0310 — Strukturalna inicjalizacja geometrii OpenCV
status: done
last_updated: 2026-08-29
---

# TASK-0310 — Strukturalna inicjalizacja geometrii OpenCV

## Goal

Dodać ograniczoną do globalnej inicjalizacji implementację
`StructuredOpenCvGeometryEngine`. Wynik ma wyznaczać początkowe ROI wyłącznie
dla aktywnego prefiksu slotów strony, bez uznawania ich za finalną geometrię.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/tasks/completed/0307-v0-10-attested-virtual-geometry-contracts.md`
- `ai_docs/tasks/completed/0308-v0-10-virtual-geometry-provenance.md`
- `ai_docs/tasks/completed/0309-v0-10-virtual-cell-source-extraction.md`

## Scope

- kontrakt globalnej inicjalizacji związany z kanonicznym źródłem, topologią,
  poświadczonym zakresem oraz wersjonowaną konfiguracją;
- aktywne sloty będące wyłącznie prefiksem `0..N-1`;
- ORB/RANSAC na istniejącym profilu zatwierdzonych stron;
- deterministyczny wybór anchora po inlierach, ratio, błędzie i checksumie;
- fallback bez profilu wykorzystujący czerwone ramki, gradienty grayscale i
  LSD do dopasowania oczekiwanej struktury aktywnych slotów;
- globalna homografia i początkowy quad/ROI każdego aktywnego slotu;
- kontrolowany wynik `needs_manual_review`, gdy dowód jest niewystarczający;
- golden testy pełnych i częściowych stron, różnych perspektyw, braku profilu
  oraz deterministyczności.

## Out of scope

- finalne lokalne dopasowanie linii i finalny quad planszy (TASK-0311);
- hard gates i finalne confidence plansz;
- integracja z pipeline'em, bazą, API, UI albo rolloutem gry;
- keypoint fallback, segmentacja, ML, GPU i nowy worker lane;
- zapis bitmap, cropów lub zmian danych użytkownika.

## Invariants

- globalna homografia jest wyłącznie inicjalizacją, nigdy finalnym dowodem
  geometrii;
- częściowa strona nie syntetyzuje nieaktywnych slotów;
- numer sekwencji wynika tylko z poświadczonego zakresu i indeksu slotu;
- analiza używa RGB po pojedynczym EXIF transpose i pracuje w skali 50%;
- brak wystarczającego dowodu kończy się fail-closed;
- istniejący `VerifiedPageRegistrar.register()` i pipeline v20 pozostają
  odtwarzalne oraz nie zostają przełączone na nową ścieżkę.

## Outcome

Dodano `StructuredOpenCvGeometryEngine` ograniczony do globalnej inicjalizacji.
Kontrakt wiąże źródło, checksumę kanonicznych pikseli, przypiętą topologię,
attested zakres i dokładny prefiks aktywnych slotów. Wynik przechowuje metodę,
checksumę konfiguracji, globalną homografię, początkowe quady oraz metryki, ale
celowo nie ma finalnego quada planszy.

Istniejący `VerifiedPageRegistrar` otrzymał osobny, niewalidujący finalnej
geometrii wynik inicjalizacyjny. ORB/RANSAC pracuje na obrazie 50%, używa do
siedmiu dotychczasowych zatwierdzonych anchorów i wybiera remis
deterministycznie po inlierach, ratio, błędzie oraz rosnącej checksumie.
Dotychczasowy `register()` nadal wykonuje pełną kontrolę dziewięciu czerwonych
ramek i nie został przełączony na nowy kontrakt.

Cold start bez profilu wykrywa kandydatów czerwonych ramek, wymaga jednocześnie
dowodu gradientów grayscale i LSD, porządkuje oczekiwany prefiks, dopasowuje
globalny model strony i zwraca tylko początkowe ROI. Brak dowodu kończy się
`needs_manual_review` bez syntetycznych slotów i bez częściowego wyniku.

Weryfikacja:

- `pytest test_page_geometry_registration.py test_structured_geometry_global_initialization.py`
  — 12 passed;
- sąsiednie testy detekcji strony, preflightu, topologii, wirtualnego renderera
  i normalizacji — 40 passed;
- scoped Ruff — passed;
- scoped strict mypy z pominięciem importowanego grafu — passed;
- pełne śledzenie importów mypy nie zgłosiło błędu w zmienionych modułach, ale
  nadal kończy się na dwóch wcześniejszych błędach w `image_imports.py:430`
  oraz `image_job_repository.py:122`, odnotowanych już po TASK-0308.

Nie podłączono silnika do pipeline'u, bazy, API ani UI. Finalne lokalne
dopasowanie linii, hard gates i per-board confidence pozostają wyłącznie
zakresem TASK-0311.
