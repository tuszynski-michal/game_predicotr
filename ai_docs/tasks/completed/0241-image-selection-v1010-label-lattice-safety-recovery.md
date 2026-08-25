---
title: TASK-0241 image selection v10.10 label lattice safety recovery
status: done
release: "0.6"
last_updated: 2026-08-21
---

# TASK-0241 — Image selection v10.10 label lattice safety recovery

## Status

`done`

## Goal

Przywrócić skuteczne i bezpieczne rozpoznawanie zakresów na czytelnych ekranach
3 × 3 bez akceptowania przesunięcia o jeden rząd po błędnej rekonstrukcji ramek.

## Context

Run `f861f3b6-ab6a-4085-b504-da4885d72e09` na źródle
`E:\777 zd\200557 - 222912` został anulowany na żądanie właściciela po
24 896 z 42 422 zdjęć. Staging pozostaje zachowany, a dalsza kolejka jest
wstrzymana. Diagnostyka wykazała, że większość kolejki ręcznego ustalenia
zakresu miała czytelne liczby, lecz ogólny fallback OCR pomijał górny rząd.
Jednocześnie częściowa rekonstrukcja siatki potrafiła umieścić syntetyczny rząd
na tabeli wypłat i zaakceptować zakres przesunięty o trzy numery.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/tasks/0157-image-selection-scale-quality-and-owner-acceptance.md`
- `ai_docs/tasks/completed/0239-image-selection-v109-partial-layout-range-recovery.md`
- `ai_docs/tasks/completed/0240-image-selection-pending-output-directory-isolation.md`

## Scope

- dodać niezmienny manifest `fast-image-selector-v10.10`, zachowując dokładne
  odtwarzanie v10.9 po fingerprintcie,
- priorytetyzować etykiety ze wszystkich trzech rzędów widocznej siatki,
- dopasowywać osie siatki tylko z kandydatów przypominających etykiety zakresu,
- odzyskiwać zakres z czterech kolejnych, przestrzennie osadzonych etykiet,
- nie ufać częściowej kotwicy, która nie ma żadnej faktycznie wykrytej planszy
  w górnym rzędzie; taki przypadek ma przejść do niezależnej siatki etykiet,
- zachować fail-closed przy remisie, niezgodnej geometrii i zbyt słabym OCR,
- wykonać ograniczoną regresję na rzeczywistych plikach przed nowym pełnym runem,
- po zaliczeniu bramki uruchomić świeży run na zachowanym stagingu, bez wznawiania
  anulowanego joba, a następnie przywrócić wstrzymaną kolejkę.

## Out of scope

- zmiana uploadu albo schematu bazy,
- zmiana grupowania zdjęć bez osobnego pomiaru,
- użycie cursora poprzedniego zakresu do rozstrzygania OCR,
- osłabienie dowodu do dwóch samodzielnych etykiet,
- usuwanie zachowanego stagingu lub wyników bez osobnej zgody właściciela.

## Acceptance criteria

- [ ] V10.9 zachowuje wersję, fingerprint i dotychczasową fabrykę adapterów.
- [ ] V10.10 rozpoznaje poprawnie realne regresje `000056`, `004140`, `012042`,
      `012051` i `012062`.
- [ ] V10.10 nie zwraca przesuniętych zakresów `208087–208095` ani
      `208105–208113` dla dwóch znanych regresji.
- [ ] Syntetyczny górny rząd bez obserwowanej planszy nie może samodzielnie
      zakotwiczyć automatycznego zakresu.
- [ ] Cztery kolejne etykiety wymagają jednoznacznych pozycji row-major oraz
      poprawnej geometrii; remis pozostaje nierozstrzygnięty.
- [ ] Skupione testy workera, Ruff i mypy przechodzą.
- [ ] Ograniczony profil rzeczywisty ma zero błędnych zakresów przed startem
      pełnego runu.

## Expected files

- `services/worker/src/game_predictor_worker/images/selection/adapters.py`
- `services/worker/src/game_predictor_worker/images/selection/manifest.py`
- `services/worker/src/game_predictor_worker/images/selection/job.py`
- `services/worker/src/game_predictor_worker/images/selection/engine.py`
- `services/worker/src/game_predictor_worker/cli.py`
- `services/worker/tests/test_image_selection_adapters.py`
- `services/worker/tests/test_fast_image_selector.py`
- `services/worker/tests/test_image_selection_job.py`
- `ai_docs/requirements/IMAGE_SELECTION.md`
- `ai_docs/architecture/IMAGE_SELECTION.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md`

## Verification

Wyniki komend oraz rzeczywistej regresji zostaną zapisane w `Outcome`.

## Risks / open questions

- Sam wzrost skuteczności zakresów nie naprawia potencjalnego false split
  grupowania. Telemetria nowego runu musi nadal osobno pokazywać liczbę grup.
- Pełny run może rozpocząć się dopiero po bramce realnych przykładów; anulowany
  job nie będzie wznawiany jako v10.10, ponieważ jego fingerprint jest v10.9.

## Outcome

W toku.

## Closure

Zamknięto jako zastąpione 2026-08-21. Nieukończone bramki dotyczą selektora
v10.10; późniejsze wersje oraz ręczny workflow zmieniły ten tor. Historyczny
manifest pozostaje odtwarzalny, ale nie jest planem dla wersji 0.7.
