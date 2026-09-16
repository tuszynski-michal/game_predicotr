---
title: TASK-0524 — Usunięcie pozostałych gier i dowód pustego stanu
status: done
last_updated: 2026-09-09
---

# TASK-0524 — Usunięcie pozostałych gier i dowód pustego stanu

## Status

`done`

## Goal

Usunąć ostatnią grę i jej dane zależne po wiążącym preview, pozostawiając
zarządzane pliki, katalog operatora i archiwum starej gry.

## Dependencies / entry conditions

- TASK-0519–TASK-0523 ukończone.
- Wiążący preview SHA-256:
  `c4fc91bc2140fc70e889d6e4394bb77d9162ac4e8094d3780419af30d5ece0b7`.
- Dokładne potwierdzenie operatora otrzymano 2026-09-09.

## Recommended execution

`gpt-6-astra` z reasoning `high`; operacja na rzeczywistych danych wymagała
ścisłego związania celu, preview, receipt i końcowego audytu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`

## Scope

- Gra `777` (`new-siedem`), ID
  `03d64bfe-4d29-47dd-9153-76bd99b3b5d9`.
- Rekordy game-owned w `public`.
- Bez fizycznego usuwania managed assets.

## Out of scope

- `C:\Users\user\Documents\777`.
- `artifacts/legacy-chat-search/777-v0.1-layouts.sqlite3`.
- Globalne joby bez `game_id` oraz globalne wykonania plikowe.
- Fizyczny GC zarządzanych artefaktów.

## Acceptance criteria

- [x] Katalog gier jest pusty.
- [x] Nie istnieją bezpośrednie ani zależne rekordy należące do gry.
- [x] Nie istnieją aktywne joby gry ani stagingi gry.
- [x] Managed assets nie zostały usunięte.
- [x] Katalog operatora i archiwum SQLite pozostały dostępne.

## Outcome

### Changed

- Aktywowano write fence związany z potwierdzonym preview.
- Usunięto 2 479 490 rekordów należących do `new-siedem` w trwałych,
  wznawialnych partiach.
- Receipt `game_deletion_operations` zakończył się statusem `database_done`;
  journal ma 1 947 zatwierdzonych partii.
- Fizyczne artefakty pozostawiono do osobno zatwierdzanego GC.

### Verification results

- `games = 0`.
- Tabele z bezpośrednim niepustym `game_id = 0`.
- Jednopoziomowe zależności od game-owned rodziców = 0.
- Aktywne joby celu przed usunięciem = 0.
- `C:\Users\user\Documents\777` istnieje po operacji.
- Archiwum SQLite istnieje po operacji i ma 19 808 256 bajtów.
- Globalne rekordy bez właściciela gry zostały zachowane.

### Not completed

- Nie wykonano GC 7 826 niewspółdzielonych referencji artefaktów; zgodnie z
  potwierdzeniem `DO NOT DELETE MANAGED ASSETS` jest to osobny etap.

### Documentation updates

- Dodano raport `ai_docs/quality/TASK_0524_EMPTY_CATALOG_AUDIT.md`.
- Zaktualizowano `ai_docs/process/CURRENT_STATE.md`.

### Recommended next task

- TASK-0525 — greenfield cutover na `game_data_v2`.
