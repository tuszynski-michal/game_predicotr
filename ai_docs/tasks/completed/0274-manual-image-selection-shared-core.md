---
title: TASK-0274 - Wspólny silnik ręcznej selekcji i adapter lokalny
status: done
owner: Codex
version: 0.7
---

# Cel

Wydzielić czystą domenę ręcznej selekcji zdjęć ze specyficznych dla przeglądarki
mechanizmów File System Access API. Dotychczasowy lokalny workspace ma zachować
identyczne zachowanie i korzystać z lokalnych adapterów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (TASK 2)

## Zakres

- dodać wspólny package z typami stanu, zakresami, decyzjami, naturalnym
  sortowaniem, polityką bounded preview oraz portami source/output/session;
- podłączyć istniejący Admin przez adaptery File System Access oraz IndexedDB;
- utrzymać format i semantykę publicznych typów oraz manifestów v1;
- dopisać testy czystego core i lokalnych adapterów.

## Poza zakresem

- zdalny UI, outbox, endpointy, API/OpenAPI, format v2;
- zmiana skrótów, zoomu, scrolla, UX lub modelu trwałości IndexedDB v2;
- migracja bazy danych.

## Kryteria odbioru

- lokalny workspace ma identyczne wyniki dla Enter/F, Tab, A/Ctrl+Z, strzałek,
  zoomu, scrolla, zakresu `+9` i checksum guard;
- core nie importuje React, IndexedDB ani File System Access API;
- listowanie JPEG-ów nadal nie otwiera ich danych, a preview jest ograniczony do
  bieżącego indeksu i trzech sąsiadów z każdej strony;
- output i trace manifesty v1 pozostają zgodne;
- source adapter nie zapisuje, a output usuwa tylko plik zarządzany o zgodnej
  checksumie;
- testy Admina i package, typecheck, lint oraz build Admina przechodzą.

## Outcome

Utworzono package `@game-predictor/manual-image-selection-core` z czystą
maszyną zakresów, manifestami v1, naturalnym porządkiem, bounded preview i
portami source/output/session. Local Admin wykorzystuje adaptery File System
Access oraz istniejący store IndexedDB v2 przez port sesji. Fasada v1 zachowuje
dotychczasowe eksporty lokalnego modułu.

Weryfikacja:

- `npm test --workspace @game-predictor/manual-image-selection-core` — 4/4;
- `npm run typecheck --workspace @game-predictor/manual-image-selection-core`;
- `npm run build --workspace @game-predictor/manual-image-selection-core`;
- `npm test --workspace @game-predictor/admin` — 245/245;
- `npm run typecheck --workspace @game-predictor/admin`;
- `npm run lint --workspace @game-predictor/admin`;
- `npm run admin:build`.

Nie dodano remote UI, API, outboxu ani formatu v2. Ręczny smoke z natywnym
pickerem nie był automatyzowany; kontrakty lokalnego adaptera są pokryte fake
uchwytami, bez użycia API.
