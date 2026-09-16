---
title: TASK-0328 experimental Structured Geometry config v2
status: done
last_updated: 2026-08-30
---

# TASK-0328 — Eksperymentalna konfiguracja Structured Geometry v2

## Goal

Wydzielić wersjonowany kontrakt konfiguracji kandydata Structured OpenCV, który
usuwa nieaudytowalne stałe pikselowe, traktuje LSD jako jeden z dowodów i może
być bezpiecznie użyty w kolejnym read-only feasibility spike'u bez zmiany
produkcji.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/quality/STRUCTURED_GEOMETRY_FEASIBILITY_SPIKE_V1.md`
- `ai_docs/tasks/completed/0323-read-only-structured-geometry-feasibility-spike.md`
- `ai_docs/tasks/completed/0327-virtual-cell-renderer-contract-corrections.md`
- `ai_docs/process/DECISION_LOG.md` — D-266
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- addytywny `structured-geometry-config-v2` o statusie
  `experimental_measurement_only` i z jawnym zakazem aktywacji;
- adaptacyjna skala analizy zachowująca minimalny rozmiar lokalnego ROI;
- błędy reprojekcji wyrażane jako ułamek przekątnej komórki;
- osobne, wersjonowane wagi i progi wieloźródłowego dowodu;
- opcjonalne, deterministyczne profile gry bez ukrytych wartości domyślnych;
- czysta ocena kandydata, w której LSD nie jest wyłączną bramką, a mocna ramka,
  znany układ i regularność mogą skompensować słabe linie wewnętrzne;
- twarde, nieusuwalne bramki homografii, source support, alignment, kolejności
  i braku nakładania;
- deterministyczny payload i checksumę pełnej konfiguracji.

## Out of scope

- bez zmiany produkcyjnych progów v1 i jego fingerprintów;
- bez podłączenia v2 do `StructuredOpenCvGeometryEngine`, pipeline'u i jobów;
- bez `structured_default`, rolloutu, backfillu, migracji, API i UI;
- bez strojenia na niepełnym korpusie, deklaracji 95/98 i przebiegu na danych
  użytkownika;
- bez segmentacji, keypoint activation i zmian renderera.

## Acceptance criteria

- [x] Identyczna konfiguracja zawsze ma identyczny canonical payload i SHA-256.
- [x] Skala analizy jest adaptacyjna i zachowuje minimalny lokalny ROI, o ile
      jest to fizycznie możliwe bez upscalingu.
- [x] Zmiana profilu gry zmienia checksumę, a profile są jednoznaczne.
- [x] Brak LSD nie jest samodzielnym hard failure przy mocnej ramce, znanym
      układzie i regularności.
- [x] Samo LSD bez niezależnych dowodów nie może dać automatycznego wyniku.
- [x] Naruszenie source support, alignment, kolejności albo overlapu zawsze
      kończy się fail-closed.
- [x] Publiczne zachowanie i testy konfiguracji v1 pozostają niezmienione.
- [x] Testy, Ruff i scoped mypy przechodzą.

## Planned commit

`v0.10.21 - add experimental structured geometry config v2`

## Outcome

Dodano addytywny
`structured-opencv-geometry-config-v2-multi-evidence-experimental-v1`.
Kontrakt jawnie wersjonuje adaptacyjną skalę, progi znormalizowane względem
przekątnej komórki, wagi sygnałów oraz opcjonalne profile gry. Canonical payload
i jego SHA-256 zmieniają się wraz z każdą zmianą profilu lub polityki.

Czysty evaluator zachowuje twarde bramki bezpieczeństwa, ale nie wymaga LSD
jako wyłącznego dowodu. Mocna ramka, znany układ i regularność mogą utworzyć
automatycznego kandydata bez LSD; samo LSD bez dwóch niezależnych rodzin dowodu
kończy się korektą ręczną. Wynik jest kandydatem pomiarowym, nie decyzją
produkcyjną.

Konfiguracja wymusza `experimental_measurement_only`,
`activationAllowed=false` i rozdzielenie źródeł strojenia od oceny. Nie została
zaimportowana przez produkcyjny engine ani pipeline, nie zmieniono progów v1,
fingerprintów, bazy, API, UI i rolloutu. Rozszerzenie korpusu D-266 pozostaje
warunkiem następnej integracji shadow/read-only.

Weryfikacja:

- 35 testów konfiguracji v2, feasibility spike'a, inicjalizacji i refinera —
  passed;
- Ruff format/check zmienionych modułów i testu — passed;
- scoped strict mypy konfiguracji v2 — passed;
- `git diff --check` — passed z istniejącymi ostrzeżeniami CRLF niezwiązanych
  plików worktree.
