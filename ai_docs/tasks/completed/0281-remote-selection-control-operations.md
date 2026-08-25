---
title: TASK-0281 - Operacje selekcji, rewizje i idempotencja HTTP
status: done
owner: Codex
version: 0.7
---

# Cel

Synchronizować małe operacje sterujące zdalnej ręcznej selekcji w ścisłej
kolejności, bez duplikatów, utraty decyzji ani cofnięcia nowszej generacji.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (sekcje 13-18 i TASK 9)
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0275-remote-manual-selection-domain-contracts.md`
- `ai_docs/tasks/completed/0276-remote-manual-selection-persistence.md`
- `ai_docs/tasks/completed/0278-remote-manual-selection-access-and-writer-lease.md`
- `ai_docs/tasks/completed/0279-remote-manual-selection-reviewer-ingress.md`
- `ai_docs/tasks/completed/0280-remote-source-adapter-indexeddb-outbox.md`

## Zakres

- idempotentne utworzenie kolekcji, partii i stronicowanych source items;
- aktywacja partii dopiero po walidacji kompletnego, niezmiennego manifestu;
- transakcyjne zastosowanie operacji z blokadą wiersza, rewizją i generacją;
- lease-scoped authorization oraz bezpieczny odczyt state delta;
- publiczne endpointy control, OpenAPI i zamknięta allowlista proxy;
- sekwencyjny drain/replay outboxu Reviewera oraz kontrolowane konflikty;
- testy fault injection, współbieżności, restartu i skali 15 000 operacji.

## Poza zakresem

- binarny upload JPEG, materializacja i finalizacja partii;
- deselect skutkujący fizycznym usunięciem pliku;
- pełny produkcyjny workspace zdalnej selekcji i UI hosta.

## Invarianty

- exact retry zwraca ten sam zapisany wynik i nie zwiększa rewizji;
- luka client sequence, nieaktualna rewizja i luka generacji są konfliktami;
- starsza generacja nie nadpisuje nowszego stanu;
- mutacja wymaga aktywnego writer lease w tej samej transakcji;
- utracona odpowiedź może zostać bezpiecznie odtworzona przez ten sam opId;
- source manifest po aktywacji jest niezmienny;
- outbox usuwa wyłącznie jawnie potwierdzony operationId;
- odpowiedzi, logi i audyt nie ujawniają host base path ani sekretów;
- publiczne proxy nie otwiera Admina, uploadu, finalizacji ani arbitralnego API.

## Plan wykonania

1. Dodać application service i brakujące repozytoryjne operacje transakcyjne.
2. Dodać schematy, endpointy control oraz zamkniętą allowlistę proxy.
3. Dodać Reviewer sync adapter i atomowe przejścia outbox/state delta.
4. Pokryć retry, konflikty, lease, zakresy obce, restart i skalę testami.
5. Uruchomić bramki jakości, zaktualizować dokumentację i wykonać checkpoint.

## Outcome

- Dodano transakcyjny application service i repozytoria dla kolekcji, partii,
  immutable source manifest, operacji oraz bounded state delta.
- Publiczne endpointy są dostępne tylko przez purpose-scoped cookie, client ID,
  writer lease dla nowych mutacji i zamkniętą allowlistę Reviewera. Nie dodano
  żadnej trasy binarnej ani materializacji.
- IndexedDB synchronizator wysyła outbox sekwencyjnie, akceptuje wyłącznie
  zgodny outcome i usuwa dokładnie potwierdzone `operationId`. Network failure
  zachowuje pending; conflict zachowuje wpis oraz pobiera stan kanoniczny.
- Testy pokrywają lost response, refresh/restart, exact retry po utracie lease,
  stale revision, scope, rate limit, immutable manifest, 15 000 rekordów i
  loopback select/skip/undo.
- Bramka końcowa: top-level API `526 passed, 2 skipped`, PostgreSQL `13 passed`,
  Reviewer `85 passed`; Ruff, OpenAPI, klient, lint, typecheck i build są
  zielone. Monolityczne zebranie całego katalogu API nadal ma wcześniejszy
  konflikt dwóch modułów testowych o tej samej nazwie, dlatego testy uruchomiono
  w rozłącznych grupach i osobno dla integracji PostgreSQL.
