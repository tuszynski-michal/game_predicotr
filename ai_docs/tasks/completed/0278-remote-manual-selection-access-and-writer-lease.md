---
title: TASK-0278 - Purpose-scoped sesja, kod i writer lease
status: done
owner: Codex
version: 0.7
---

# Cel

Dodać trwałą, odwoływalną sesję zdalnej ręcznej selekcji zdjęć z osobnym
kodem, rotowanym tokenem i dokładnie jednym aktywnym writer lease, bez
rozszerzania scope istniejącego Reviewera `game/import`.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/architecture/REMOTE_MANUAL_IMAGE_SELECTION.md` (sekcje 10–17 i TASK 6)
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/tasks/completed/0275-remote-manual-selection-domain-contracts.md`
- `ai_docs/tasks/completed/0276-remote-manual-selection-persistence.md`
- `ai_docs/tasks/completed/0277-remote-manual-selection-host-path-safety.md`

## Zakres

- wydzielenie współdzielonych primitives code/salt/PBKDF2/token bez zmiany
  zachowania istniejących sesji Reviewera;
- utworzenie sesji przez lokalny Admin po jednorazowym zużyciu host base
  capability, lista/detail bez sekretów i natychmiastowy revoke;
- publiczne unlock oraz context z tokenem wyłącznie w `HttpOnly`, `Secure`,
  `SameSite=Strict` cookie o ścieżce `/selection-api`;
- maksymalnie pięć trwałych prób kodu, TTL 5 minut–24 godziny, rotacja tokenu i
  hash-only persistence;
- jeden writer lease per sesja, heartbeat tego samego klienta oraz jawny
  takeover dopiero po wygaśnięciu lease;
- append-only audyt bez kodu, tokenu, lease tokenu i ścieżki hosta;
- testy restartu, współbieżności PostgreSQL, brute force, replay, redakcji i
  regresji istniejącego Reviewera.

## Poza zakresem

- route i proxy Reviewera, Quick Tunnel oraz cookie forwarding z TASK 7;
- UI Admina i zdalny workspace;
- kolekcje, partie, operacje zdjęć, transfer binarny i materializacja;
- game/import scope lub reuse istniejącej sesji `reviewer_access_sessions`.

## Invarianty

- kod jest zwracany tylko w odpowiedzi create, token nigdy nie jest polem JSON;
- baza przechowuje wyłącznie PBKDF2 code hash i SHA-256 token hash;
- link i publiczny context nie zawierają sekretu, host path, `gameId` ani
  `importJobId`;
- piąta błędna próba trwale blokuje sesję i usuwa aktywny token/lease;
- unlock rotuje token; revoke natychmiast usuwa token i lease;
- aktywny lease innego klienta jest read-only i nie może zostać przejęty przed
  expiry; heartbeat nie przyjmuje ani nie ujawnia fencing tokenu;
- istniejący Reviewer zachowuje dotychczasowe kody, hashe, TTL i API.

## Plan wykonania

1. Zamrozić regresję istniejącego Reviewera i wydzielić credential primitives.
2. Rozszerzyć repozytorium sesji zdalnej o transakcyjne auth/list/revoke/audit.
3. Dodać access service z TTL, lockout, rotacją i writer lease.
4. Dodać Admin/public HTTP, cookie contract, OpenAPI i klient generowany.
5. Przeprowadzić testy jednostkowe, loopback, PostgreSQL i security; domknąć
   dokumentację i checkpoint przed TASK 7.

## Outcome

- Wydzielono wspólne primitives kodu, soli, PBKDF2 i token hash. Istniejący
  Reviewer zachował alfabet, format kodu, `210000` iteracji, TTL i kontrakt API;
  jego regresje przeszły bez zmian funkcjonalnych.
- Dodano osobny access service/repository dla zdalnej selekcji. Create zużywa
  jednorazową base capability, kod występuje tylko w pierwszej odpowiedzi, a
  lista/detail nie ujawniają sekretów ani host path.
- Unlock rotuje hash-only token i ustawia go wyłącznie jako cookie
  `HttpOnly/Secure/SameSite=Strict` z `Path=/selection-api`. Context nie zawiera
  `gameId/importJobId`; piąta błędna próba oraz revoke usuwają token i lease.
- Jeden 45-sekundowy writer lease używa host-only fencing tokenu. Heartbeat
  tego samego klienta jest idempotentny, aktywny obcy lease jest read-only, a
  takeover ma dokładnie jednego zwycięzcę dopiero po expiry.
- Append-only audyt nie zawiera code/token/salt/lease token/path. Create i
  revoke zostały objęte local-owner intent oraz exact high-impact target.
- Nie dodano migracji: migracja 0056 zawiera wszystkie aktywowane pola i
  constrainty. Nie dodano proxy, ingressu, UI, operacji zdjęć ani uploadu.
- Weryfikacja: 108/108 celowanych testów API/security/regresji i 12/12
  testów PostgreSQL integration. Równoległy unlock, pięć współbieżnych błędnych prób,
  restart oraz exactly-one-winner takeover przeszły. PBKDF2 kosztował średnio
  około 103 ms/hash na pięciu próbkach.
- Przeszły Ruff/format, focused mypy dla sześciu modułów, OpenAPI/generated
  client oraz client typecheck. Pełny historyczny pytest API osiągnął 55% bez
  błędu, ale został przerwany po limicie 120 s; osierocony proces zakończono.
- TASK 7 nie został rozpoczęty. Przed jego implementacją obowiązuje osobny
  checkpoint bezpieczeństwa kontraktu cookie/proxy.
