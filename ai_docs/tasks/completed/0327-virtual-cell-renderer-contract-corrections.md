---
title: TASK-0327 virtual cell renderer contract corrections
status: done
last_updated: 2026-08-30
---

# TASK-0327 — Korekty kontraktu VirtualCellRenderer

## Status

`done`

## Goal

Wzmocnić niezmienny kontrakt source-direct renderera po utrwaleniu pól v2:
nowy render ma jawnie i samosprawdzalnie wiązać occurrence źródła, topologię,
geometrię, konfigurację, logical-cell v1/v2 i render identity v1/v2, a
checksuma przepisu oraz checksuma wynikowych pikseli pozostają rozłączne.

## Relevant docs

- `ai_docs/requirements/IMAGE_INGESTION.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/VIRTUAL_GEOMETRY_SCHEMA_OWNERSHIP.md`
- `ai_docs/tasks/completed/0321-logical-cell-identity-v2.md`
- `ai_docs/tasks/completed/0325-additive-virtual-geometry-schema-corrections.md`
- `ai_docs/tasks/completed/0326-bounded-additive-virtual-geometry-backfill.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- Dodać nową, addytywną wersję render specu z jawnym occurrence, snapshotem
  topologii, wersją geometrii, checksumą znormalizowanych pikseli oraz wersją
  polityki checksummy RGB.
- Walidować nowy spec fail-closed względem obu logical-cell identity i obu
  render identity przed udostępnieniem renderu konsumentom.
- Zachować dokładnie jeden source-direct warp na komórkę, jeden decode źródła,
  brak trwałych PNG i bitową parity pikseli z cropperem v19.
- Traktować checksumę render specu jako tożsamość przepisu, a checksumę RGB jako
  niezależny dowód wyniku; uniknąć cyklicznego umieszczania checksummy pikseli
  wewnątrz checksummowanego specu.
- Zachować odczyt historycznych speców; nowa walidacja dotyczy nowych renderów.

## Out of scope

- Bez zmiany progów i konfiguracji Structured OpenCV.
- Bez włączania `structured_default`, rolloutu, backfillu ani cutoveru.
- Bez migracji, zmian bazy, canonical ownership, API publicznego i UI.
- Bez tolerant parity i automatycznego przenoszenia training approval.
- Bez zmian atlasu/cache poza naprawą rozdzielenia checksummy specu i pikseli.
- Bez dołączania niezwiązanych zmian importu v20 i stagingu z worktree.

## Acceptance criteria

- [x] Spec nowego renderu samodzielnie potwierdza occurrence i topologię.
- [x] Logical-cell v1/v2 i render identity v1/v2 są niezależnie przeliczane i
      rozbieżność kończy się stabilnym błędem.
- [x] Checksumy specu i pikseli są rozłączne oraz obie są weryfikowane.
- [x] Identyczne piksele z dwóch importów mają ten sam pixel checksum, ale inne
      logical-cell-v2 i render identity v2.
- [x] Błąd ostatniej komórki zatrzymuje całą partię przed pierwszym warpem.
- [x] Dokładna parity v19 i brak trwałych bitmap pozostają bez regresji.
- [x] Testy workera/API, Ruff i scoped mypy przechodzą z odnotowanymi dwoma
      istniejącymi błędami transitive mypy poza zakresem zadania.
- [x] Nie wykonano operacji na danych użytkownika ani rolloutu.

## Planned commit

`v0.10.20 - harden virtual cell render provenance`

## Outcome

Nowe rendery emitują `virtual-cell-render-spec-v3-complete-provenance-v1`.
Spec jawnie zapisuje payload occurrence i topologii, wersję geometrii,
normalized-pixel checksum oraz wersję checksummy RGB. Runtime przelicza z
niego oba logical-cell identity oraz oba render identity i odrzuca rozbieżność
stabilnym `IMAGE_VIRTUAL_CELL_RENDER_SPEC_INVALID`.

Checksuma specu identyfikuje przepis, a checksuma pikseli pozostaje osobnym
dowodem wyniku. Skorygowano konsumenta preview, który wcześniej wymagał
checksummy RGB wewnątrz specu. Historyczne specy nadal są obsługiwane.

Testy potwierdzają dokładną parity z v19, jeden warp na komórkę, rozróżnienie
occurrence przy identycznych pikselach, wykrycie tamperingu i walidację całej
partii przed pierwszym warpem. Nie uruchomiono migracji, joba, backfillu ani
operacji na danych użytkownika.
