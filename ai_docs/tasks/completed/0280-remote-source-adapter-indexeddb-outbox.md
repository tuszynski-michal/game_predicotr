---
title: TASK-0280 - Remote source adapter i trwały IndexedDB outbox
status: done
owner: Codex
version: 0.7
---

# Cel

Czytać lokalne JPEG-i operatora w zdalnym Reviewerze i zachowywać kursor,
uchwyt, source manifest oraz niepotwierdzone operacje w trwałym IndexedDB bez
kopiowania obrazów do storage.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (sekcje 10-18 i TASK 8)
- `ai_docs/quality/REMOTE_SOURCE_BROWSER_CAPABILITY_SPIKE.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0273-remote-source-browser-capability-spike.md`
- `ai_docs/tasks/completed/0274-manual-image-selection-shared-core.md`
- `ai_docs/tasks/completed/0275-remote-manual-selection-domain-contracts.md`
- `ai_docs/tasks/completed/0279-remote-manual-selection-reviewer-ingress.md`

## Zakres

- remote File System Access source adapter z read-only permission i bezpiecznym
  capability fallbackiem;
- stronicowane wyliczanie JPEG-ów w naturalnej kolejności i source manifest bez
  trwałego kopiowania Blobów;
- IndexedDB remote schema v1: sessions, batches, sourceItems, outbox, transfer
  checkpoints i client instance, z jawną migracją;
- trwały append/ack outbox odróżniający lokalną decyzję od host-confirmed;
- wznowienie po refresh/crash, permission recovery i rygorystyczny relink;
- koordynacja kart przez BroadcastChannel z drugim tabem read-only;
- `navigator.storage.persist()` jako best effort;
- testy migracji, FSA, outboxu, relinku, koordynacji kart i skali.

## Poza zakresem

- HTTP zastosowanie operacji i host state delta z TASK 9;
- binarny upload, materializacja, finalizacja oraz host DB;
- pełny workspace zdjęć i ostateczny UX produkcyjny;
- zmiany semantyki lokalnej ręcznej selekcji lub jej IndexedDB v2.

## Invarianty

- IndexedDB i pamięć aplikacji nie przechowują trwałych Blobów JPEG całej partii;
- źródło jest otwierane tylko read-only;
- source manifest i naturalna kolejność są deterministyczne;
- local pending i server-confirmed pozostają rozróżnione;
- handle/permission loss nie usuwa kursora ani outboxu;
- ack usuwa wyłącznie jawnie potwierdzone operation IDs;
- relink innego lub niekompatybilnego manifestu działa fail-closed;
- jedna karta jest writerem, kolejne pozostają read-only;
- lokalny Admin IDB v2 i jego zachowanie pozostają bez zmian.

## Plan wykonania

1. Zamrozić remote IDB v1, migrację i port trwałości.
2. Dodać paged FSA adapter, permission recovery i manifest.
3. Dodać trwały append/list/ack outbox oraz crash restore.
4. Dodać relink validation, fallback i best-effort persistence.
5. Dodać BroadcastChannel/tab coordination i bounded workspace integration.
6. Uruchomić testy, build, Chrome fixture i benchmark; zaktualizować dokumentację.

## Outcome

- Dodano osobny IndexedDB v1 Reviewera z jawną migracją sześciu store'ów,
  metadata-only source items, trwałym kursorem, exact outboxem i transfer
  checkpoints bez Blobów.
- Adapter FSA używa wyłącznie `mode: read`, buduje naturalnie sortowany manifest,
  obsługuje permission recovery, sesyjny fallback i rygorystyczny relink.
- `BroadcastChannel` zapewnia jedną lokalną kartę zapisującą; druga pozostaje
  read-only. `navigator.storage.persist()` jest wyłącznie best effort.
- Testy: 79/79 Reviewer, 9/9 shared core; lint, typecheck i production build
  Reviewera oraz typecheck core przeszły. Skala objęła 1000 source metadata i
  15 000 rekordów outboxu.
- Fixture Chromium potwierdził zapis/odczyt uchwytu IndexedDB oraz restore po
  reload. Zewnętrzny Chrome nie był dostępny w sesji, więc jego ręczny odbiór
  pozostaje przed publicznym rolloutem.
- Nie dodano HTTP apply, uploadu ani pełnego workspace'u; to pozostaje zakresem
  TASK 9, 10 i 13.
