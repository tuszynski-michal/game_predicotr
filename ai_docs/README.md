---
title: AI documentation index
status: active
last_updated: 2026-08-02
---

# Dokumentacja AI Driven Development

## Cel

Dokumentacja dzieli produkt na niezależne obszary, dzięki czemu model AI może
realizować małe iteracje bez utraty kontekstu i bez przypadkowego łączenia
niegotowych części systemu.

## Wejście do zadania

Przed rozpoczęciem pracy czytaj w tej kolejności:

1. ten indeks,
2. [Current State](process/CURRENT_STATE.md),
3. aktywne zadanie znajdujące się bezpośrednio w `ai_docs/tasks/`,
4. wyłącznie dokumenty wskazane w sekcji `Relevant docs` tego zadania.

Materiały archiwalne i ukończone zadania nie są domyślnym kontekstem
implementacyjnym.

## Aktywna dokumentacja

### Projekt

- [Project brief](project/PROJECT_BRIEF.md) — cel, użytkownicy, zakres i ograniczenia.
- [Glossary](project/GLOSSARY.md) — jednoznaczne pojęcia domenowe.
- [Open questions](project/OPEN_QUESTIONS.md) — pytania otwarte i indeks
  ostatnich rozstrzygnięć.
- [Traceability](project/TRACEABILITY.md) — mapa wymaganie → dokument → milestone.

### Wymagania

- [Mobile app](requirements/MOBILE_APP.md)
- [Admin app](requirements/ADMIN_APP.md)
- [Admin app 0.2 proposal](requirements/ADMIN_APP_V0_2.md)
- [Algorithms](requirements/ALGORITHMS.md)
- [Image ingestion](requirements/IMAGE_INGESTION.md)
- [Fast representative image selection](requirements/IMAGE_SELECTION.md)
- [Local manual image selection](requirements/MANUAL_IMAGE_SELECTION.md)
- [Manual data import](requirements/MANUAL_DATA_IMPORT.md)
- [Iterative supervised model improvement](requirements/SUPERVISED_MODEL_IMPROVEMENT.md)
- [Vision lab requirements](requirements/VISION_LAB.md) — zatwierdzenia
  laboratoryjne, podziały, topologie i granice integracji (D-447).

### Architektura

- [Tech stack](architecture/TECH_STACK.md)
- [System architecture](architecture/SYSTEM_ARCHITECTURE.md)
- [Data model](architecture/DATA_MODEL.md)
- [Virtual geometry schema ownership](architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md)
- [API contract](architecture/API_CONTRACT.md)
- [Supervised model improvement architecture](architecture/SUPERVISED_MODEL_IMPROVEMENT.md)
- [Vision lab architecture](architecture/VISION_LAB.md) — izolacja,
  kontrakty, eksport, UI i środowisko treningowe.
- [Fast representative image selection architecture](architecture/IMAGE_SELECTION.md)
- [Local manual image selection architecture](architecture/MANUAL_IMAGE_SELECTION.md)
- [Remote manual image selection proposal](architecture/REMOTE_MANUAL_IMAGE_SELECTION.md)
  — analiza wykonalności, bezpieczeństwa, synchronizacji i breakdown wdrożenia;
  dokument ma status `proposed`.
- [Grid engine v3 proposal](architecture/GRID_ENGINE_V3_PROPOSAL.md)
  — silnik siatek bez wzorca per gra (model ekranu 3 × 3, siatka z rozrzutu
  między planszami); prototyp TASK-0648, status `proposed`.

### Dostarczanie

- [Roadmap](delivery/ROADMAP.md)
- [Milestone 01](delivery/MILESTONE_01_MOCKED_MOBILE.md)
- [Milestone 01 execution plan](delivery/MILESTONE_01_EXECUTION_PLAN.md)
- [Milestone 02 execution plan](delivery/MILESTONE_02_EXECUTION_PLAN.md)
- [Milestone 03 execution plan](delivery/MILESTONE_03_EXECUTION_PLAN.md)
- [Milestone 04 execution plan](delivery/MILESTONE_04_EXECUTION_PLAN.md)
- [Milestone 05 execution plan](delivery/MILESTONE_05_EXECUTION_PLAN.md)
- [Milestone 06 execution plan](delivery/MILESTONE_06_EXECUTION_PLAN.md)
- [Milestone 06.5 execution plan](delivery/MILESTONE_06_5_EXECUTION_PLAN.md)
- [Milestone 06.6 execution plan](delivery/MILESTONE_06_6_EXECUTION_PLAN.md)
- [Milestone 07 execution plan](delivery/MILESTONE_07_EXECUTION_PLAN.md)
- [Milestone 07.0 image selection execution plan](delivery/MILESTONE_07_0_EXECUTION_PLAN.md)
- [Milestone 08 execution plan](delivery/MILESTONE_08_EXECUTION_PLAN.md)
- [Global geometry library v1 execution plan](delivery/GLOBAL_GEOMETRY_LIBRARY_EXECUTION_PLAN.md)
- [Vision lab execution plan](delivery/VISION_LAB_EXECUTION_PLAN.md) —
  zaakceptowany plan P00/T01–T13 i punkty STOP A–E.
- [Legacy public store removal execution plan](delivery/LEGACY_PUBLIC_STORE_REMOVAL_EXECUTION_PLAN.md) —
  zaakceptowane przejście na V2-only; DDL wymaga odrębnej zgody operacyjnej.
- [V2 readiness remediation plan](delivery/V2_READINESS_REMEDIATION_PLAN.md) —
  naprawy po `no-go` T08 oraz blokująca propozycja decyzji TASK-0698.
- [Version 0.1 release plan](delivery/VERSION_0_1_RELEASE_PLAN.md)
- [Version 0.2 execution plan](delivery/VERSION_0_2_EXECUTION_PLAN.md)
- [Version 0.3 execution plan](delivery/VERSION_0_3_EXECUTION_PLAN.md)
- [Version 0.4 execution plan](delivery/VERSION_0_4_EXECUTION_PLAN.md)
- [Version 0.5 execution plan](delivery/VERSION_0_5_EXECUTION_PLAN.md)
- [Version 0.6 execution plan](delivery/VERSION_0_6_EXECUTION_PLAN.md)

### Proces i jakość

- [AI workflow](process/AI_DRIVEN_DEVELOPMENT.md)
- [Definition of Done](process/DEFINITION_OF_DONE.md)
- [Decision log](process/DECISION_LOG.md)
- [Current state](process/CURRENT_STATE.md)
- [Task template](process/TASK_TEMPLATE.md)
- [Standard planów](process/PLAN_STANDARD.md) — obowiązkowy odczyt przed
  planowaniem, aktualizacją lub wykonaniem planu.
- [Test strategy](quality/TEST_STRATEGY.md)
- [Version 0.3 Mobile acceptance](quality/V0_3_MOBILE_ACCEPTANCE.md)
- [Board-cell geometry v19 rollout closure](quality/BOARD_CELL_GEOMETRY_V19_ROLLOUT.md)
- [Virtual geometry 0.10 cutover acceptance](quality/V0_10_VIRTUAL_GEOMETRY_CUTOVER.md)
- [Keypoint geometry fallback 0.10](quality/V0_10_KEYPOINT_GEOMETRY_FALLBACK.md)
- [Fast symbol verification acceptance](quality/SYMBOL_REVIEW_FAST_PAGE_ACCEPTANCE.md)
- [Semi-automatic range OCR v3 performance](quality/SEMI_AUTOMATIC_SELECTION_RANGE_OCR_V3_PERFORMANCE.md)
- [Theoretical symbol-cell review scalability analysis](quality/SYMBOL_CELL_REVIEW_SCALABILITY_ANALYSIS.md)
  — analiza granic pamięci i transakcji TASK-0294; nie jest pomiarem czasu.
- [Remote source browser capability spike](quality/REMOTE_SOURCE_BROWSER_CAPABILITY_SPIKE.md)
  — wynik TASK-0273 i bramka przed zdalnym modułem ręcznej selekcji.

### Bezpieczeństwo

- [Model zagrożeń zdalnego Reviewera](security/REMOTE_REVIEWER_THREAT_MODEL.md)

### Instrukcje operatorskie

- [Lokalne uruchamianie i instalacja](guides/LOCAL_OPERATION_GUIDE.md) —
  środowisko Windows, aplikacja mobilna, panel Admin i aplikacja Reviewer.
- [Usunięcie legacy public game store](guides/LEGACY_PUBLIC_STORE_REMOVAL.md)
  — preflight, odrębne approval, apply i postflight migracji `0125`.
- [Eksport snapshotu do laboratorium wizji](guides/VISION_LAB_EXPORT.md) —
  manifest wejściowy, uruchomienie eksportera i format wyniku.

### Materiały warunkowe

- [Analiza aplikacji referencyjnej](reverse_engineering/REFERENCE_APP_ANALYSIS.md)
  — używać dopiero po rozstrzygnięciu Q-020.

## Historia

- [Archiwum dokumentacji](archive/README.md)
- [Ukończone zadania](tasks/completed/README.md)

Historia wyjaśnia pochodzenie decyzji, ale nie zastępuje aktualnych wymagań,
architektury ani Decision Log.

## Zasada pojedynczego źródła prawdy

| Rodzaj informacji     | Dokument właścicielski  |
| --------------------- | ----------------------- |
| Cel produktu i zakres | `PROJECT_BRIEF.md`      |
| Zachowanie ekranów    | pliki w `requirements/` |
| Model danych          | `DATA_MODEL.md`         |
| Endpointy             | `API_CONTRACT.md`       |
| Stos technologiczny   | `TECH_STACK.md`         |
| Bieżący etap          | `CURRENT_STATE.md`      |
| Historia decyzji      | `DECISION_LOG.md`       |
| Kryteria ukończenia   | `DEFINITION_OF_DONE.md` |

Nie kopiuj pełnej reguły do kilku dokumentów. W dokumentach pomocniczych podaj
krótkie podsumowanie i link do właściciela reguły.

## Statusy

### Dokumenty

- `draft` — materiał roboczy,
- `proposed` — propozycja oczekująca na zatwierdzenie,
- `accepted` — obowiązujące źródło prawdy,
- `active` — dokument procesowy utrzymywany na bieżąco,
- `superseded` — dokument historyczny zastąpiony nowszym źródłem.

### Zadania

- `todo` — gotowe do rozpoczęcia,
- `in_progress` — aktualnie realizowane,
- `blocked` — nie może być kontynuowane bez decyzji lub zmiany stanu,
- `done` — ukończone i przenoszone do `tasks/completed/`.

## Reguła aktualizacji

Zmiana zachowania produktu aktualizuje właściwy plik wymagań. Zmiana techniczna
wpływająca na strukturę systemu aktualizuje dokument architektury i, jeżeli
jest istotna, `DECISION_LOG.md`.
