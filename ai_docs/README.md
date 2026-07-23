---
title: AI documentation index
status: active
last_updated: 2026-07-24
---

# Dokumentacja AI Driven Development

## Cel

Dokumentacja dzieli produkt na niezależne obszary, dzięki czemu model AI może realizować małe iteracje bez utraty kontekstu i bez przypadkowego łączenia niegotowych części systemu.

## Mapa dokumentacji

### Projekt

- [Requirements review](project/REQUIREMENTS_REVIEW.md) — analiza i korekty pierwotnego opisu.
- [Project brief](project/PROJECT_BRIEF.md) — cel, użytkownicy, zakres i ograniczenia.
- [Glossary](project/GLOSSARY.md) — jednoznaczne pojęcia domenowe.
- [Open questions](project/OPEN_QUESTIONS.md) — pytania wymagające decyzji właściciela produktu.
- [Traceability](project/TRACEABILITY.md) — mapa wymaganie → dokument → milestone.

### Wymagania

- [Mobile app](requirements/MOBILE_APP.md)
- [Admin app](requirements/ADMIN_APP.md)
- [Algorithms](requirements/ALGORITHMS.md)
- [Image ingestion](requirements/IMAGE_INGESTION.md)

### Architektura

- [Tech stack](architecture/TECH_STACK.md)
- [System architecture](architecture/SYSTEM_ARCHITECTURE.md)
- [Data model](architecture/DATA_MODEL.md)
- [API contract](architecture/API_CONTRACT.md)

### Dostarczanie

- [Roadmap](delivery/ROADMAP.md)
- [Milestone 01](delivery/MILESTONE_01_MOCKED_MOBILE.md)
- [Milestone 01 execution plan](delivery/MILESTONE_01_EXECUTION_PLAN.md)

### Proces i jakość

- [AI workflow](process/AI_DRIVEN_DEVELOPMENT.md)
- [Definition of Done](process/DEFINITION_OF_DONE.md)
- [Decision log](process/DECISION_LOG.md)
- [Current state](process/CURRENT_STATE.md)
- [Task template](process/TASK_TEMPLATE.md)
- [Test strategy](quality/TEST_STRATEGY.md)

### Dodatkowe materiały

- [Analiza istniejącej aplikacji](reverse_engineering/REFERENCE_APP_ANALYSIS.md)
- [Task 0001](tasks/0001-architecture-clarification.md) — ukończone wyjaśnienie architektury.

## Zasada pojedynczego źródła prawdy

Nie kopiuj tej samej reguły do kilku plików. Zamiast tego linkuj do dokumentu, który jest jej właścicielem.

| Rodzaj informacji | Dokument właścicielski |
|---|---|
| Cel produktu i zakres | `PROJECT_BRIEF.md` |
| Zachowanie ekranów | pliki w `requirements/` |
| Model danych | `DATA_MODEL.md` |
| Endpointy | `API_CONTRACT.md` |
| Stos technologiczny | `TECH_STACK.md` |
| Bieżący etap | `CURRENT_STATE.md` |
| Historia decyzji | `DECISION_LOG.md` |
| Kryteria ukończenia | `DEFINITION_OF_DONE.md` |

## Statusy dokumentów

- `draft` — materiał roboczy.
- `proposed` — konkretna propozycja oczekująca na zatwierdzenie.
- `accepted` — obowiązujące źródło prawdy.
- `superseded` — dokument zastąpiony nowszą decyzją.

## Reguła aktualizacji

Każda zmiana zachowania produktu musi aktualizować odpowiedni plik wymagań. Każda zmiana techniczna wpływająca na strukturę systemu musi aktualizować dokument architektury i, jeśli jest istotna, `DECISION_LOG.md`.
