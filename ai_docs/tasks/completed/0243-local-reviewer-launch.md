---
title: TASK-0243 code-free local Reviewer launch
status: done
release: "0.6"
last_updated: 2026-08-15
---

# TASK-0243 — Code-free local Reviewer launch

## Status

`done`

## Goal

Pozwolić właścicielowi uruchomić i otworzyć osobną aplikację Reviewer lokalnie
z sekcji `Gry → Zatwierdzanie`, bez Internetu, tunelu HTTPS, tworzenia sesji i
przepisywania kodu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/guides/LOCAL_OPERATION_GUIDE.md`
- `ai_docs/quality/TEST_STRATEGY.md`

## Scope

- dodać osobny przycisk `Otwórz lokalnie`,
- uruchamiać istniejący build Reviewera wyłącznie na
  `http://127.0.0.1:3001`, bez Cloudflare,
- otwierać wybraną grę i import bez sesji oraz kodu tylko dla żądania strony
  przychodzącego przez loopback,
- zachować dotychczasowy zdalny link, kod, revoke i publiczny tunnel bez zmian,
- utrzymać jawny scope `gameId + importJobId` i brak dostępu przez publiczny
  origin do trybu lokalnego.

## Acceptance criteria

- [x] lokalny start nie wykonuje połączenia do Cloudflare,
- [x] odpowiedź kontrolera z publicznym albo obcym adresem jest odrzucana,
- [x] jedno kliknięcie otwiera właściwą grę/import bez formularza kodu,
- [x] publiczny host z parametrami trybu lokalnego nadal pokazuje bramkę kodu,
- [x] brak builda, błąd startu i blokada popupu mają czytelny fallback,
- [x] testy API, klienta, Admina i Reviewera oraz lint/typecheck przechodzą.

## Outcome

- Dodano stały, ograniczony kontroler `start_local_reviewer.ps1` i chroniony
  endpoint Admin API, który uruchamia gotowy build tylko pod
  `http://127.0.0.1:3001` i nie dotyka tunelu Cloudflare.
- Admin ma oddzielny przycisk `Otwórz lokalnie`; zdalny link, sesja, kod i revoke
  zachowują wcześniejszy kontrakt.
- Reviewer dopuszcza tryb bez kodu wyłącznie dla hosta loopback na porcie 3001
  oraz poprawnego scope `gameId + importJobId`. Dla obcego hosta te same
  parametry nadal prowadzą do bramki kodu.
- Rzeczywisty test przeglądarkowy otworzył jednym kliknięciem grę `777` i import
  `50cfdcad` bez formularza kodu; workspace pobrał 63 plansze i pokazał pierwszą
  pozycję do zatwierdzenia. Admin i aplikacja nie zgłosiły błędów aplikacyjnych.
- Walidacja: 332 testy API zaliczone i 25 integracyjnych pominiętych; cztery
  testy dotknięte limitem długości ścieżki Windows zaliczone osobno z krótkim
  `basetemp`; 200 testów Admina, 24 Reviewera i 38 klienta zaliczone; Ruff,
  mypy (327 plików), ESLint, typecheck, OpenAPI, parser 34 skryptów PowerShell
  oraz produkcyjne buildy Admina i Reviewera zaliczone.
