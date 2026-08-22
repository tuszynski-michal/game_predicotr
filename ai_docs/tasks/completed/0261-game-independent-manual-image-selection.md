---
title: TASK-0261 game-independent manual image selection
status: done
release: "0.7"
last_updated: 2026-08-22
---

# TASK-0261 — Ręczna selekcja niezależna od gry

## Goal

Zakładka `Ręczna selekcja` ma być dostępna bez wybrania gry, ponieważ działa
wyłącznie na lokalnych folderach i nie korzysta z domeny gry ani backendu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- usunięcie blokady wymagającej aktywnej gry,
- jeden stabilny, lokalny namespace sesji niezależny od nawigacji gry,
- niedestrukcyjne przejęcie najnowszej istniejącej sesji historycznie zapisanej
  pod grą,
- zachowanie manifestów v1, checksum, trace i File System Access API.

## Out of scope

- zmiana automatycznej selekcji zdjęć,
- zmiana API, OpenAPI, bazy PostgreSQL albo workerów,
- zmiana formatu plików `seq_*` lub algorytmu nawigacji.

## Acceptance criteria

- [x] zakładka otwiera workspace bez wybranej gry,
- [x] rozpoczęcie i wznowienie sesji nie zależy od `activeGame`,
- [x] najnowsza historyczna sesja per gra jest dostępna po zmianie namespace'u,
- [x] historyczny rekord nie jest usuwany podczas przejęcia,
- [x] testy Admina, typecheck, lint i format przechodzą.

## Outcome

Usunięto blokadę kontekstu gry i propsy gry z lokalnego workspace'u. Jedna
niezależna sesja zachowuje dotychczasowy format manifestów, a store kopiuje do
niej najnowszą historyczną sesję wraz z pasującymi zdarzeniami bez usuwania
źródła. Przeszło `229/229` testów Admina, typecheck, celowany ESLint bez błędów
oraz Prettier. Lokalny widok bez parametru `game` pokazuje wybór folderów i
start sesji zamiast blokady.
