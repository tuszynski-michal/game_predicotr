---
title: Recover local Reviewer process start
status: done
task_id: TASK-0436
last_updated: 2026-09-04
---

# TASK-0436 — Przywrócenie uruchamiania lokalnego Reviewera

## Goal

Usunąć regresję, przez którą `Otwórz lokalnie` przechodzi bezpośrednio na
`127.0.0.1:3001`, mimo że proces Reviewera nie został uruchomiony.

## Scope

- przed końcową nawigacją wywołać istniejący, ograniczony endpoint
  `POST /api/v1/admin/reviewer-local/start`;
- zachować brak assignmentu, sesji, kodu i tunelu;
- zachować synchronicznie przygotowane okno, a po osiągnięciu gotowości ponowić
  nawigację na dokładny scope gry i importu;
- obsłużyć loading, błąd startu i popup zablokowany przez przeglądarkę;
- dodać test regresyjny obejmujący zatrzymany lub nieaktualny proces.

## Out of scope

- zmiany backendu, OpenAPI lub wygenerowanego klienta;
- uruchamianie Reviewera na danych użytkownika;
- przywracanie lokalnych lub online assignmentów;
- zmiany geometrii, importów i danych domenowych.

## Relevant docs

- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Definition of Done

- kliknięcie uruchamia istniejący lifecycle lokalnego Reviewera i akceptuje
  wyłącznie gotowy proces pod dokładnym targetem loopback;
- po odpowiedzi `reviewerReady = true` przygotowane okno ponownie przechodzi na
  scoped URL, dzięki czemu wcześniejsze `ERR_CONNECTION_REFUSED` nie pozostaje
  ekranem końcowym;
- błąd startu nie pozostawia martwego popupu, a blokada popupu udostępnia link
  dopiero po gotowości procesu;
- podwójny submit jest zablokowany;
- testy Admina, lint, typecheck i build przechodzą;
- dokumentacja i `CURRENT_STATE.md` opisują przywrócony kontrakt.

## Outcome

- Launcher wywołuje istniejący `startLocalReviewer` z zamkniętą komendą
  `local-reviewer` i akceptuje wyłącznie gotowy target
  `http://127.0.0.1:3001` bez publicznego originu.
- Okno nadal otrzymuje od razu docelowy scoped URL, ale po zakończeniu startu
  procesu nawigacja jest ponawiana. Usuwa to końcowy ekran
  `ERR_CONNECTION_REFUSED` dla wcześniej zatrzymanego procesu.
- Błąd startu zamyka przygotowane okno, zablokowany popup udostępnia ręczny link
  dopiero po gotowości, a stan i synchroniczny guard blokują podwójny submit.
- Nie zmieniono backendu, OpenAPI, wygenerowanego klienta, assignmentów, danych
  ani procesu Reviewera na komputerze użytkownika.
- Weryfikacja:
  - `npm run test --workspace @game-predictor/admin` — 393 passed;
  - `npm run lint --workspace @game-predictor/admin` — passed;
  - `npm run typecheck --workspace @game-predictor/admin` — passed;
  - `npm run admin:build` — passed;
  - skoncentrowany Prettier — passed;
  - `git diff --check` — passed.
