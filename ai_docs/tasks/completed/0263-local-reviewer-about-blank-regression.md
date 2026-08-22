---
title: TASK-0263 local Reviewer about blank regression
status: done
release: "0.7"
last_updated: 2026-08-22
---

# TASK-0263 — Regresja `about:blank` przy lokalnym Reviewerze

## Goal

Przycisk `Otwórz lokalnie` zawsze rozpoczyna próbę otwarcia assignmentu i nie
pozostawia nowej karty na `about:blank`, również gdy przeglądarka blokuje zmianę
`window.opener`.

## Context

- Dotychczasowy launcher tworzył `about:blank` i ustawiał `opener = null` poza
  obsługą błędów oraz przed wywołaniem API.
- Błąd bezpieczeństwa przeglądarki przerywał handler: w logu nie było żądania
  `openLocalReviewerWork`, a utworzona karta pozostawała pusta.
- Poprzednia regresja sprawdzała kolejność tekstu w pliku, ale nie wykonywała
  przygotowania okna z odrzuconą zmianą `opener`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- otwierać od razu przewidywany, loopback-only URL wybranego scope'u,
- nie przerywać lokalnego startu po błędzie izolowania `opener`,
- ponowić nawigację zwróconym, zwalidowanym URL po gotowości API,
- zawsze zachować ręczny link do poprawnie otwartej pracy,
- dodać wykonywalną regresję zachowania popupu.

## Out of scope

- zmiana API, assignmentów, sesji lub Quick Tunnel,
- zmiana kolejki i decyzji review,
- uruchamianie albo zatrzymywanie workerów i jobów.

## Acceptance criteria

- [x] Lokalna karta nie jest tworzona z URL `about:blank`.
- [x] Błąd zapisu `opener = null` nie przerywa dalszego przepływu.
- [x] URL zwrócony przez API ponawia nawigację przed odświeżeniem overview.
- [x] Blokada popupu lub nawigacji pozostawia widoczny link ręczny.
- [x] Testy Admina, lint, typecheck, build i formatowanie przechodzą.

## Outcome

- Launcher otwiera bezpośrednio przewidywany URL Reviewera na porcie 3001,
  wyliczony wyłącznie dla loopbackowego Admina. Nie tworzy już `about:blank`.
- Zmiana `opener` ma osobną obsługę błędu, a nawigacja po odpowiedzi API używa
  dozwolonego również między originami settera `location.href`.
- Poprawny URL jest utrwalany w stanie UI przed próbą ponownej nawigacji, więc
  ręczny fallback jest zawsze dostępny.
- Przeszło `237/237` testów Admina, typecheck, ESLint bez błędów (dwa istniejące
  ostrzeżenia `<img>`), Prettier i produkcyjny build Next.js.
- Rzeczywiste, idempotentne otwarcie aktywnego assignmentu zwróciło
  `created=false`, `ready=true`; zwrócona strona Reviewera odpowiedziała HTTP
  200. Nie uruchomiono ani nie zatrzymano workerów i nie zmieniono decyzji.
