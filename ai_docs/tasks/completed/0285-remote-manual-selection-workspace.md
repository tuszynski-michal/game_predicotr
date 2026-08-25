---
title: TASK-0285 - Zdalny workspace ręcznej selekcji
status: done
owner: Codex
version: 0.7
---

## Cel

Zaimplementować TASK 13 planu zdalnej ręcznej selekcji: pełny ekran pracy na
lokalnych JPEG-ach operatora, korzystający ze wspólnego silnika zakresów i
skrótów, z trwałym outboxem oraz jawnym rozróżnieniem stanu lokalnego,
potwierdzonego i zsynchronizowanego z hostem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/MANUAL_IMAGE_SELECTION.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (TASK 13 oraz sekcje 4, 6, 8, 10, 11, 18–20 i 22–24)
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`

## Zakres

- konfiguracja logicznej kolekcji i partii oraz rejestracja naturalnie
  posortowanego source manifestu;
- wspólne rozpoznawanie skrótów i zachowanie zakresu, skoku oraz kursora;
- local-only bounded preview, zoom, fullscreen i zachowanie pionowego scrolla;
- trwała, natychmiastowa decyzja lokalna połączona atomowo z outboxem;
- sync control plane i transfer wybranego JPEG-a w tle;
- jawne statusy `selected_local`, `pending`, `confirmed`, `synced` i `error`,
  liczniki, konflikt, permission/offline, warning zamknięcia oraz backpressure;
- odzyskiwanie workspace'u po refreshu bez przechowywania Blobów.

## Poza zakresem

- panel hosta Admina i lifecycle linków z TASK 14;
- finalizacja partii, output/trace manifest hosta i cleanup;
- nowe endpointy lub ręcznie utrzymywane kopie kontraktów backendu;
- automatyczna selekcja, OCR, import plansz i zmiana semantyki lokalnego fallbacku.

## Invarianty

- podgląd JPEG-a pozostaje wyłącznie lokalny i używa bounded Object URL cache;
- `selected_local` nigdy nie jest przedstawiany jako `synced`;
- decyzja wpływająca na wynik jest zapisana w IndexedDB razem z outboxem przed
  zmianą widoku;
- interakcja nie oczekuje na sieć ani upload;
- refresh zachowuje kursor, zakres, decyzje, outbox i transfer checkpoints;
- źródło jest tylko do odczytu, a Blob ani ścieżka absolutna nie trafia do IDB,
  odpowiedzi API lub UI;
- lokalny Admin zachowuje dotychczasowe skróty, manifesty i pracę bez API.

## Kryteria odbioru

- operator konfiguruje kolekcję/partię i zaczyna pracę po aktywacji manifestu;
- Enter/F, Tab, A/Ctrl+Z, strzałki, skok, zoom, fullscreen i scroll mają parity
  z lokalnym workspace'em;
- offline/retry/conflict/permission są widoczne, a decyzje nie giną;
- aktywny upload nie blokuje nawigacji ani kolejnych decyzji;
- status i liczniki nie utożsamiają lokalnego wyboru z materializacją hosta;
- cache podglądu i liczba aktywnych transferów pozostają ograniczone;
- Admin i Reviewer przechodzą testy, lint, typecheck i build.

## Outcome

- Dodano wspólny resolver skrótów używany bez regresji przez lokalny Admin i
  zdalny Reviewer.
- Reviewer tworzy kolekcję/partię, rejestruje source manifest i pokazuje pełny
  workspace local-only z bounded preview, scroll, zoom, fullscreen, kursorem i
  przeskokiem.
- Decyzja oraz outbox są atomowe. Sync, reconciliation i transfer działają w
  tle z jawnymi statusami, retry, konfliktem, permission, offline,
  backpressure i beforeunload.
- Testy: `manual-image-selection-core` 11/11, Reviewer 98/98, Admin 245/245;
  Reviewer i Admin lint/typecheck/build zaliczone. OpenAPI pozostaje bez zmian.
- Nie uruchomiono fizycznego scenariusza na dwóch komputerach; zgodnie z planem
  należy do rollout gate. Automatyczne testy izolują IndexedDB/taby i transport,
  ale obowiązkowy checkpoint przed TASK 14 pozostaje.
