---
title: TASK-0769 — Panel udostępniania wyszukiwarki w Adminie
status: done
last_updated: 2026-09-30
---

# TASK-0769 — Panel udostępniania wyszukiwarki w Adminie

## Status

`done`

## Goal

Przycisk „Udostępnij online” tworzy link i kod, pokazuje je do skopiowania i zatrzymuje sesję z potwierdzeniem.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T10.

## Dependencies / entry conditions

- TASK-0766 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Panel według istniejącego wzorca zdalnej selekcji. Audyt: niezależny agent `claude-opus-5-5` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T10. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T10 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T10.

## Expected files

Patrz plan §5 T10.

## Test cases

Patrz plan §5 T10.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

### Changed

- `apps/admin/src/features/board-search/board-search-share-panel.tsx`:
  przycisk „Udostępnij online” w nagłówku sekcji, formularz (etykieta, czas
  1/4/8/24 h, domyślnie 8 h), po utworzeniu link i kod z kopiowaniem,
  lista aktywnych linków gry (wygaśnięcie, ostatnie otwarcie, link, kod z
  pamięci przeglądarki), „Zatrzymaj” z potwierdzeniem w dwóch krokach,
  zakończone linki w rozwijanej liście, czytelne błędy (tunel, limit,
  gotowość gry, flaga).
- `board-search-share-code-cache.ts` (osobny klucz
  `game-predictor-board-search-share-codes-v1`, wzorzec kodów zdalnej
  selekcji) i `board-search-share-state.ts`.
- Pakiet UI: opcjonalne `headerActions` w nagłówku sekcji; Admin podaje
  panel tylko, gdy klient ma metody udostępniania (odbiorca nie ma panelu).
- Style panelu w `globals.css` Admina; `ADMIN_APP.md`.

### Verification results

- Admin: testy 591/591 (cache kodów: wygaśnięcie, usunięcie po
  zatrzymaniu, osobny klucz; stan: czasy, grupowanie aktywne/zakończone,
  komunikaty błędów w tym brak tunelu), interakcje panelu 5/5 (utworzenie,
  kopiowanie, lista, dwustopniowe zatrzymanie, błąd tunelu); typecheck
  czysty, lint bez nowych uwag.
- Pakiet UI: interakcje 33/33, lint czysty; Prettier czysty.
- Audyt niezależnego agenta `claude-opus-5-5`: cykl 1 FAIL — P1 otwarcie
  panelu jednej gry kasowało zapamiętane kody aktywnych linków innych gier;
  P2 kod nowego linku ginął, gdy panel odmontował się w trakcie tworzenia.
  Poprawki: usuwanie tylko kodów linków zakończonych z listy tej gry, zapis
  kodu od razu do pamięci przeglądarki (testy obu przypadków); P3: polskie
  komunikaty dla pozostałych błędów tunelu, blokada innych „Zatrzymaj” w
  trakcie zatrzymywania, `aria-controls`, lista w API działa mimo
  nieodczytanego statusu tunelu (linki bez adresu, test API).
- Cykl 2 audytu: PASS, bez otwartych P0–P2.
- Ręczny odbiór w Adminie wymaga migracji `0130` na bazie deweloperskiej i
  restartu API (zgoda operatora na granicy etapu).
