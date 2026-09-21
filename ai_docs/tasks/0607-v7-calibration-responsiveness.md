---
id: TASK-0607
title: Responsywność i ergonomia kalibracji etykiet V7
status: todo
owner: Codex
---

# TASK-0607 — Responsywność i ergonomia kalibracji etykiet V7

## Goal

Usunąć opóźnienie widocznego zaznaczania i przełączania zdjęć, uprościć oznaczanie oraz zmierzyć czas wyboru reprezentantów na rzeczywistych korpusach.

## Relevant docs

- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/delivery/V7_DYNAMIC_LABEL_VIEWPORT_V2_EXECUTION_PLAN.md`
- `ai_docs/process/DECISION_LOG.md`

## User feedback to implement

1. Marker po kliknięciu pojawia się od razu po trwałym wpisie lokalnym, bez czekania na odpowiedź serwera; szybkie kolejne kliknięcia też pozostają widoczne.
2. Wybór pozycji 1–9, ocena cropa i checkbox zasłoniętego numeru są nad obrazem. Gotowość profilu jest poza główną ścieżką oznaczania.
3. Grupa ujęć to select `A/B/C`, nie pole dowolnego tekstu.
4. Podstawowa sesja wybiera pełne kadry. Trudne/przycięte/zasłonięte zdjęcia nie są automatycznie proponowane do podstawowej kalibracji.
5. Asset bieżący i sąsiady używają ograniczonego cache/prefetch w pamięci, bez blobów w IndexedDB; source drift pozostaje bezpiecznie wykrywany.
6. Benchmark raportuje osobno manifest/hash, decode, lokalizację/OCR, finalizację i zapis dla 100/300/500 niezależnych źródeł. Brak wystarczającej liczby plików daje `not_evaluable`.

## Scope and safety

Trwała kolejka serwera zachowuje kolejność i idempotency; optymistyczny marker nie jest potwierdzoną anotacją. Zmiana źródła, konflikt, porzucenie kolejki oraz restart muszą usunąć lub odtworzyć wyłącznie lokalne zamiary zgodnie z dotychczasową polityką. Nie utrwalać obrazów, ich ścieżek ani binariów w IndexedDB.

## Acceptance criteria

- [ ] Interakcje z zaznaczeniem nie czekają wizualnie na HTTP, a kolejka po reloadzie nadal zachowuje porządek.
- [ ] Interfejs realizuje wszystkie sześć punktów feedbacku powyżej.
- [ ] Cache ma ograniczenie liczby/rozmiaru oraz nie omija serwerowej kontroli tożsamości źródła.
- [ ] Benchmark nie używa holdoutu i nie powiela obrazów dla wyniku 500.
- [ ] Testy obejmują opóźnioną pierwszą odpowiedź, szybkie dwa kliknięcia, reload, zmianę assetu i pusty wariant benchmarku.

## Outcome

Oczekuje na TASK-0606.