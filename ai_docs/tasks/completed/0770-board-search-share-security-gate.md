---
title: TASK-0770 — Bramka bezpieczeństwa i odbiór udostępniania wyszukiwarki
status: done
last_updated: 2026-09-30
---

# TASK-0770 — Bramka bezpieczeństwa i odbiór udostępniania wyszukiwarki

## Status

`done`

## Goal

Nowa powierzchnia jest opisana w modelu zagrożeń, dokumentacji i odebrana na lokalnym buildzie produkcyjnym.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T12.

## Dependencies / entry conditions

- TASK-0765–0769 i TASK-0771 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Bramka bezpieczeństwa i spójność dokumentacji z kodem. Audyt: niezależny agent `claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T12. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T12 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T12.

## Expected files

Patrz plan §5 T12.

## Test cases

Patrz plan §5 T12.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

### Changed

- `REMOTE_REVIEWER_THREAT_MODEL.md`: opis trzeciej powierzchni
  (`/board-search`, `/board-search-api`), lista kontrolna bramki
  bezpieczeństwa z dowodami, reakcja na incydent z linkiem.
- `LOCAL_OPERATION_GUIDE.md`: procedura udostępnienia wyszukiwarki online
  (przygotowanie, tworzenie linku, dziennik, zatrzymanie, wyłącznik).
- Testy bramki: `apps/reviewer/test/board-search-share-security-gate.test.mjs`
  (allowlista proxy równa publicznym trasom OpenAPI w obie strony, trasy
  Admina udostępnień — sesje, dziennik, odtworzenie — niedostępne, publiczne
  schematy bez identyfikatorów, ścieżek i dziennika) i
  `apps/reviewer/test-interactions/review-api-share-cookie.test.mjs`
  (ciasteczko udostępnienia nie autoryzuje `/review-api`).
- `CURRENT_STATE.md`: etap B zakończony.

### Verification results

- Lista kontrolna (model zagrożeń, sekcja „Bramka bezpieczeństwa
  udostępnionej wyszukiwarki”): allowlista zgodna z OpenAPI, izolacja celu
  sesji, cookie i pochodzenie, limity, redakcja odpowiedzi, stabilne błędy,
  dziennik zapytań (kompletność, brak IP, informacja dla odbiorcy, brak
  publicznego odczytu) — każdy punkt ma test w repozytorium.
- Reviewer: testy 192/192, `test:geometry` 7/7; `next build` OK.
- Odbiór na lokalnym buildzie produkcyjnym (`next start` na
  `127.0.0.1:3012`, bez tunelu, instancja zatrzymana po odbiorze): strona
  `/board-search` 200 z CSP bez adresu API i bez `unsafe-eval`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`; trasy Admina,
  odświeżanie, `%2e%2e` i parametr `gameId` → 403; brak cookie → 401;
  unlock z obcego pochodzenia → 403; ciasteczko udostępnienia na
  `/review-api` → 401.

- Audyt niezależnego agenta `claude-fable-5-1`: PASS w pierwszym cyklu, bez
  P0–P2. P3 poprawione: test wartości domyślnych limitów i 429 dla zakresu,
  doprecyzowanie w modelu zagrożeń (wpis na wykonane zapytanie, dozwolone
  `gameId`/`rulesVersionId`).

### Not completed

- Uruchomienie publicznego Quick Tunnel i test z drugiego urządzenia —
  poza bramką, wymaga osobnej zgody operatora.
- Migracja `0130` na bazie deweloperskiej i odbiór w Adminie z prawdziwymi
  linkami — wymaga zgody operatora.
