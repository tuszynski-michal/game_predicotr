---
title: Administration access control and audit hardening
status: done
last_updated: 2026-07-31
---

# TASK-0079 — Administration access control and audit hardening

## Status

`done`

## Goal

Utrwalić zaakceptowany model jednego lokalnego właściciela: Admin i Admin API
pozostają loopback-only, a mutacje wysokiego wpływu wymagają serwerowo
zweryfikowanej intencji, jednoznacznego celu i append-only audytu aktora
`local-owner` bez ujawniania sekretów.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DECISION_LOG.md` — D-097
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md`
- `ai_docs/architecture/DATA_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`
- `ai_docs/delivery/MILESTONE_08_EXECUTION_PLAN.md`
- `ai_docs/quality/TEST_STRATEGY.md`
- `ai_docs/tasks/completed/0078-local-administration-threat-model-q019-decision.md`

## Scope

- dodać wspólny serwerowy guard lokalnych mutacji administracyjnych,
- odrzucać żądania spoza loopback i niedozwolone konteksty cross-origin,
- wymagać dla operacji wysokiego wpływu typowanego potwierdzenia intencji oraz
  jednoznacznego identyfikatora celu,
- zapisywać append-only audyt z aktorem `local-owner`, operacją, celem, wynikiem
  i bezpiecznymi metadanymi,
- zapewnić redakcję kodów, tokenów i innych sekretów w audycie oraz logach,
- uzupełnić OpenAPI, wygenerowany klient i UI dla wybranego pierwszego pionu,
- dodać regresję loopback, cross-origin, potwierdzenia i audytu.

## Out of scope

- konta użytkowników, hasła i role lokalnego Admina,
- publiczny lub LAN binding Admina i Admin API,
- udostępnienie pełnego Admina mechanizmem Reviewera,
- zewnętrzny system IAM, reverse proxy albo chmura.

## Acceptance criteria

- [x] Admin API odrzuca chronioną mutację, gdy klient nie jest loopback,
- [x] Admin API odrzuca niedozwolony `Origin` dla chronionej mutacji,
- [x] operacja wysokiego wpływu bez poprawnego potwierdzenia i celu nie zmienia
      danych,
- [x] udana i odrzucona operacja tworzą append-only zdarzenie audytowe z
      aktorem `local-owner`,
- [x] audyt i logi nie zawierają kodów dostępu, bearer tokenów ani sekretów,
- [x] OpenAPI i wygenerowany klient opisują sygnał intencji bez rozbieżnych
      ręcznych typów,
- [x] testy regresyjne potwierdzają loopback-only i ochronę cross-origin,
- [x] dokumentacja operatorska i architektura opisują rzeczywisty mechanizm.

## Verification

```powershell
npm run api:test
npm run openapi:check
npm run admin:test
```

Każda komenda musi mieć jawny timeout. Testy zmienionych modułów uruchamiamy
przed pełnymi pakietami.

## Risks / open questions

- Guard musi zachować testowalność ASGI bez osłabiania zachowania produkcyjnego.
- Zakres „wysokiego wpływu” musi być jawnie mapowany; nie wolno traktować
  wszystkich zapisów identycznie ani pozostawić nowych destrukcyjnych tras poza
  ochroną przez przypadek.
- Audyt odrzuconego żądania nie może sam stać się źródłem danych wrażliwych.

## Outcome

Dodano centralny `LocalAdminSecurityMiddleware` dla wszystkich niebezpiecznych
metod pod `/api/v1/admin/*`. Rzeczywisty request musi pochodzić z loopback,
mieć dozwolony albo nieobecny `Origin` oraz stały sygnał
`X-Admin-Intent: local-owner`. Trzy jawnie allowlistowane mutacje Reviewera z
Bearer tokenem zachowują własny, scope-bound model autoryzacji.

Operacje wysokiego wpływu mają jedną jawną mapę akcji. Wymagają dodatkowo
`X-Admin-Confirmation: confirmed` i dokładnego `X-Admin-Target`, który jest
porównywany z identyfikatorem w ścieżce albo stałym celem operacji. Wspólny
klient Admin API dodaje intencję i typowane potwierdzenie automatycznie po
świadomej akcji istniejącego UI. OpenAPI publikuje `LocalAdminIntent` jako
api-key header oraz wymagane nagłówki operacji wysokiego wpływu; klient został
zregenerowany.

Każda odrzucona mutacja i każda autoryzowana próba z końcowym wynikiem trafia
append-only do `artifacts/admin-audit/local-admin-events.jsonl`. Zdarzenie ma
serwerowego aktora `local-owner`, akcję, cel, wynik i stabilny kod przyczyny.
Nie zapisuje body ani nagłówków, a centralna redakcja usuwa wartości pól
związanych z kodem, tokenem, hasłem, kluczem lub sekretem. `fsync` kończy każdy
append. Admin otrzymał również CSP, anti-framing, no-referrer i nosniff.

Weryfikacja:

- pełny pakiet API: `215 passed, 16 skipped` w `51.48s`,
- ukierunkowane security/OpenAPI/ingress: `16/16 passed`,
- Admin: `83/83 passed` oraz produkcyjny build zakończony powodzeniem,
- klient Admin API: `18/18 passed`, TypeScript build zakończony powodzeniem,
- `openapi:check`: artefakt i generowany klient aktualne,
- Ruff i focused mypy nowego modułu: zakończone powodzeniem.

Pominięte testy to istniejące, jawnie warunkowe integracje PostgreSQL oraz dwa
testy symlinków niedostępnych dla tego konta Windows; nowy audyt bezpieczeństwa
nie wymaga zmiany schematu bazy.
