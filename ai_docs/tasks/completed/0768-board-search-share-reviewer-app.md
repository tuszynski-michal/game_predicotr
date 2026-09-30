---
title: TASK-0768 — Aplikacja online wyszukiwarki w Reviewerze
status: done
last_updated: 2026-09-30
---

# TASK-0768 — Aplikacja online wyszukiwarki w Reviewerze

## Status

`done`

## Goal

Pod linkiem działa bramka kodu i pełna kopia sekcji z proxy, cookie, CSP i cache klienta.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T9.

## Dependencies / entry conditions

- TASK-0765 i TASK-0767 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Proxy, cookie, CSP i cache klienta na publicznym hoście. Audyt: niezależny agent `claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T9. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T9 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T9.

## Expected files

Patrz plan §5 T9.

## Test cases

Patrz plan §5 T9.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

### Changed

- Proxy `apps/reviewer/src/security/board-search-share-proxy.ts` i trasa
  `/board-search-api/[...path]` (GET, POST): dokładna allowlista tras i
  parametrów (unlock, context, symbols, obraz symbolu, search, approximate-win,
  szczegóły, widok), kontrola `Sec-Fetch-Site`/`Origin`, cookie
  `gp_board_search_token` (`HttpOnly`, `Secure`, `SameSite=Strict`,
  `Path=/board-search-api`) wydawane przez proxy po odblokowaniu i czyszczone
  po 401, nagłówek intencji do API, filtr kluczy wrażliwych i ścieżek w JSON
  (502; nazwy wpisane przez właściciela nie są traktowane jako ścieżki), obrazy buforowane do limitu 8 MiB z kontrolą typu, `ETag`/`304` i `Cache-Control`
  ograniczonym do 1 doby; flaga `GAME_PREDICTOR_BOARD_SEARCH_SHARE_ENABLED`;
  adres API przez `REVIEWER_INTERNAL_API_ORIGIN` (tylko loopback).
- Osobny CSP dla `/board-search` i `/board-search-api` bez
  `127.0.0.1:8000`; pierwsza reguła wyklucza nowe ścieżki.
- Strona `/board-search?share=<id>` z bramką kodu (informacja o zapisie
  zapytań, D-472), czasem do wygaśnięcia i ekranem po wygaśnięciu albo
  zatrzymaniu; sekcja z pakietu `@game-predictor/board-search-ui`.
- Adapter `board-search-share-data-source.ts`: cache wyszukiwań (5 min, 50
  wzorców), jedno pobranie symboli, szczegóły plansz do zmiany
  `dataFingerprintSha256` zakresu, zakres liczony zawsze od nowa, brak
  mutacji i zasobów pełnego zdjęcia (okno planszy tylko do odczytu).
- Pakiet UI: `BoardSearchDataSource` jako typ strukturalny (wynik
  `{ data?, error? }`), aby adapter nie udawał wygenerowanego klienta;
  eksport typów publicznych w `admin-api-client`.

### Verification results

- Reviewer: testy 187/187 (w tym proxy: allowlista i parametry → 403 bez
  wywołania API, brak cookie i ciasteczka innych powierzchni → 401,
  ciasteczko udostępnienia nie autoryzuje zdalnej selekcji, nagłówki do API,
  odrzucenie odpowiedzi z identyfikatorami i ścieżkami, cookie po
  odblokowaniu, kontrola pochodzenia, obrazy, 304, wyłączona flaga; adapter:
  cache i jego wygaśnięcie, limit 50, szczegóły do zmiany danych, symbole,
  URL-e, brak mutacji, 401; CSP). Zmiana stawki bez żądania pokrywa test
  interakcji pakietu.
- Lint i typecheck Reviewera czyste, `next build` Reviewera OK; typecheck
  pakietu UI i Admina czysty.
- Ręcznie: lokalny Reviewer z worktree na `127.0.0.1:3011` (bez tunelu)
  pokazuje bramkę kodu z informacją o zapisie, osobny CSP i odrzuca trasy
  spoza allowlisty. Test end-to-end z odblokowaniem wymaga migracji `0129`
  na bazie deweloperskiej (zgoda operatora).

- Audyt niezależnego agenta `claude-fable-5-1`: PASS w pierwszym cyklu, bez
  P0–P2. P3 poprawione: fałszywy alarm ścieżki w etykiecie/nazwie gry
  (test), licznik czasu w osobnym komponencie (bez przerysowania sekcji co
  30 s), opis buforowania obrazów. P3 pozostawione dla TASK-0770: brak testu
  jednostkowego, że `/review-api` ignoruje ciasteczko udostępnienia
  (sprawdzone sondą).

### Not completed

- Opis powierzchni w modelu zagrożeń i odbiór bezpieczeństwa — TASK-0770.
