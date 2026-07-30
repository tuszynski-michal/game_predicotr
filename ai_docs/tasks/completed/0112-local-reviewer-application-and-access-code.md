---
title: Local reviewer application and access code
status: done
last_updated: 2026-07-30
---

# TASK-0112 — Local reviewer application and access code

## Status

`done`

## Goal

Wydzielić stanowisko zatwierdzania z panelu admina do osobnej lokalnej
aplikacji przeglądarkowej. Administrator ma utworzyć sesję ograniczoną do gry
i importu, otrzymać link oraz unikalny kod, a recenzent ma zobaczyć stanowisko
dopiero po podaniu kodu.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_06_5_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`

## Scope

- osobne `apps/reviewer` z własnym portem i komendami Windows,
- launcher w panelu admina wybierający grę i image import job,
- lokalna, wygasająca sesja z losowym identyfikatorem i kodem
  przechowywanym wyłącznie jako hash,
- kod nieobecny w linku i ekran wejścia przed pobraniem danych,
- stanowisko ograniczone do gry/importu sesji,
- przeniesienie obecnego użytecznego widoku, korekty symboli i geometrii,
- pojedynczy `Enter` lub kliknięcie zapisuje bez modala potwierdzającego,
- zachowanie idempotencji, blokady powtórzonego eventu i optimistic revision.

## Out of scope

- binding poza loopback,
- tunel/VPN, HTTPS i udostępnienie przez Internet,
- pełny threat model, limit prób, unieważnianie i audyt zdalnych aktorów,
- zmiana modelu danych review albo treningu.

## Acceptance criteria

- [x] panel admina pokazuje link i osobno unikalny kod dla wybranej gry/importu,
- [x] osobna aplikacja pod własnym adresem nie pokazuje danych przed kodem,
- [x] poprawny kod otwiera wyłącznie kontekst zapisany w sesji,
- [x] błędny albo wygasły kod nie otwiera stanowiska,
- [x] ekran zatwierdzania nie jest już osadzony w głównym panelu,
- [x] pojedynczy `Enter` i kliknięcie zapisują bez modala,
- [x] testy API/UI, typecheck, lint i oba buildy przechodzą.

## Technical notes

- Lokalna sesja jest etapem UX i przygotowaniem granicy API. Nie wolno opisywać
  jej jako gotowego zabezpieczenia internetowego.
- Kod jest ujawniany tylko w odpowiedzi tworzącej sesję.
- Każda potencjalnie ciężka komenda ma timeout nie większy niż 120 sekund.

## Outcome

### Changed

- Dodano osobne `apps/reviewer` działające lokalnie na porcie 3001 i przeniesiono
  do niego operacyjne zatwierdzanie, korektę symboli oraz edytor geometrii.
- Panel admina zawiera wyłącznie launcher wybierający aktywną grę i jej image
  import job. Utworzenie zwraca link i osobno kod ważny domyślnie osiem godzin.
- FastAPI utrzymuje procesową sesję z losowym UUID, datą wygaśnięcia oraz
  PBKDF2 salt/hash kodu. Kod jawny nie trafia do URL ani pamięci sesji.
- Gate Reviewera nie pobiera danych plansz przed poprawnym kodem. Po unlock
  selektory gry/importu są zablokowane na scope sesji.
- Usunięto modal potwierdzenia. Jeden `Enter` albo kliknięcie wywołuje zapis
  całej planszy, a key repeat, trwający zapis i pola edycyjne pozostają
  zabezpieczone.
- Poprawiono kodowanie polskich etykiet edytora geometrii po przeniesieniu.

### Verification

- `22 passed` — sesje aplikacyjne, HTTP, konfiguracja i CORS,
- `15 passed` — akcje, stan klawiatury i kontrakt UI Reviewera,
- TypeScript strict dla Admin i Reviewer,
- ESLint zmienionych części,
- produkcyjne buildy Next.js obu aplikacji,
- aktualny OpenAPI i generowany klient TypeScript,
- browser smoke: launcher wybiera `Blazing Hot 7 Deluxe`, błędny kod jest
  odrzucany bez danych, poprawny otwiera wyłącznie import
  `8188e320-dbfe-4bc8-beb1-f90d71ebfb21`, a panel admina nie osadza workbencha.

### Known limitation

Sesja TASK-0112 jest lokalną bramą UX, przechowywaną w pamięci procesu API.
Nie ma jeszcze trwałej autoryzacji każdego requestu, limitu prób, odwołania ani
HTTPS i nie może być wystawiona poza loopback. Ten zakres pozostaje w
TASK-0113–0115.
