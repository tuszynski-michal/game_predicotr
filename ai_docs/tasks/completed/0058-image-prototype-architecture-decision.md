---
title: TASK-0058 Image prototype architecture decision
status: done
last_updated: 2026-07-28
---

# TASK-0058 — Image prototype architecture decision

## Status

`done`

## Goal

Zamknąć prototyp M5 jawną decyzją architektoniczną opartą na TASK-0057:
określić zachowywane kontrakty i adaptery, odrzucone warianty, zakres reworku
oraz warunki, które muszą być spełnione przed rozpoczęciem M6.

## Context

Obecny korpus ma 12 zdjęć jednej gry i sesji. Klasyczna geometria wykrywa
12/12 stron i komplet plansz, ale bez niezależnych golden pozycji/narożników
nie da się zmierzyć pełnej accuracy. OCR osiąga `62.9630%`, kontrola surowego
cropu `42.5926%`, a pięć błędnych wyników baseline ma confidence co najmniej
0.8. Progi są nadal `proposed`, Q-016/Q-017 pozostają otwarte, a G5 nie przeszło.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/project/OPEN_QUESTIONS.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/delivery/ROADMAP.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/delivery/MILESTONE_06_EXECUTION_PLAN.md`
- `ai_docs/quality/m5-image-benchmark-report.json`
- D-010, D-050 i D-053–D-055 w `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- decyzja o Python/Pillow/OpenCV/NumPy i granicach lokalnego workera,
- decyzja o kontraktach discovery, normalizacji, geometrii, cropów i OCR,
- osobny status dla kontraktu OCR i jego aktualnej implementacji,
- reguła manual review dla niezaakceptowanego OCR,
- katalog wariantów odrzuconych lub odłożonych,
- mierzalny plan reworku bez strojenia na obecnym golden corpus,
- status M5/G5 i jawna bramka przed M6,
- aktualizacja Decision Log, wymagań, architektury, roadmapy i Current State.

## Out of scope

- implementacja nowego modelu OCR,
- zebranie lub ręczne oznaczenie dodatkowych zdjęć,
- akceptacja progów bez decyzji właściciela,
- trening klasyfikatora symboli,
- rozpoczęcie M6/M7,
- zmiana schematu bazy, API albo panelu.

## Acceptance criteria

- [x] Każdy adapter/kontrakt ma status `retain`, `experimental` albo `rework`.
- [x] Decyzja rozróżnia działanie na wspieranym wariancie od generalizacji.
- [x] Błędy OCR z wysokim confidence blokują automatyczną akceptację.
- [x] M5 i G5 mają jednoznaczny status bez ukrywania brakujących goldenów.
- [x] Warunki przed M6 są mierzalne i powiązane z Q-016/Q-017.
- [x] Nie dodano ciężkiej technologii ani finalnego modelu bez pomiaru.
- [x] Decision Log, wymagania, architektura, plan i Current State są spójne.
- [x] Kontrola raportu benchmarkowego oraz dokumentacji przechodzi.

## Expected files

- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/architecture/TECH_STACK.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/delivery/MILESTONE_05_EXECUTION_PLAN.md`
- `ai_docs/delivery/ROADMAP.md`
- `ai_docs/process/CURRENT_STATE.md`

## Outcome

Zaakceptowano D-056. Kontrakty discovery, normalizacji, artefaktów, portów i
benchmarku pozostają. Geometria/cropy są eksperymentalne poza wariantem 3 × 3,
a obecny adapter OCR wymaga reworku. Ze względu na pięć błędów z confidence
`>= 0.8` każdy wynik OCR wymaga manual review; nie ustalono auto-accept.

M5 ma status `completed_with_rework`, G5 `not_passed`, a TASK-0051 jest
`blocked`. M6/TASK-0059 nie rozpoczyna się przed reprezentatywnym korpusem
minimum 20 zdjęć, odpowiedziami Q-016/Q-017, niezależnymi goldenami geometrii,
akceptacją progów i OCR spełniającym je na held-out source images. Nie dodano
nowej biblioteki ani finalnego modelu.

Weryfikacja objęła deterministyczny `m5:benchmark --check`, walidację korpusu,
kontrolę spójności statusów/odnośników i `git diff --check`.
