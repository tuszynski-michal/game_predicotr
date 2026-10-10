---
title: TASK-0767 — Publiczne endpointy odczytu udostępnionej wyszukiwarki
status: done
last_updated: 2026-09-30
---

# TASK-0767 — Publiczne endpointy odczytu udostępnionej wyszukiwarki

## Status

`done`

## Goal

Endpointy publiczne z §4.3 zwracają dane wyłącznie gry z sesji, bez identyfikatorów wewnętrznych, z limitami żądań.

## Context

Punkt 5 zgłoszenia operatora z 2026-09-30, decyzja D-471. Pełna specyfikacja: plan §3 R4, §4.3–4.5 i §5 T8.

## Dependencies / entry conditions

- TASK-0763 i TASK-0766 done.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz taska w tabeli planu). Publiczna powierzchnia danych: izolacja gry, redakcja, limity. Audyt: niezależny agent `claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2 zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T8. Przed startem ponownie sprawdzić kod po etapie A i doprecyzować ten plik.

## Out of scope

Według planu §8.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T8 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §5 T8.

## Expected files

Patrz plan §5 T8.

## Test cases

Patrz plan §5 T8.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

Według planu §7.

## Outcome

### Changed

- Router `api/board_search_share_public.py` (`/board-search-shares`: unlock,
  context, symbols, obraz symbolu, search, approximate-win, szczegóły,
  widok) z wymaganym nagłówkiem proxy, cookie sesji, odrzuceniem parametru
  gry, zakresem magazynu gry z sesji i limitami na sesję.
- Dziennik zapytań: domena `domain/board_search_share_queries.py` (kształt i
  rozmiar wpisu per rodzaj), `application/board_search_share_queries.py`
  (zapis fail-closed, limiter), `storage/board_search_share_query_repository.py`
  (osobna transakcja zatwierdzana przed zwrotem danych).
- Szczegóły planszy: `include_cells=False` dla udostępniania (bez odczytu
  rekordów pól). `parse_board_search_cells` publiczne w `api/board_search.py`.
- Schematy publiczne bez identyfikatorów wewnętrznych i ścieżek; OpenAPI i
  wygenerowany klient.
- `API_CONTRACT.md`: sekcja powierzchni publicznej.

### Verification results

- `test_board_search_share_public_api.py`: 17/17 (proxy, cookie z
  atrybutami, brak cookie, token innej sesji czyta tylko swoją grę, parametr
  `gameId` odrzucony, rekurencyjny test zakazanych kluczy, dokładnie jeden
  wpis na zapytanie z pełnym wzorem, wpis błędu z kodem, błąd dziennika bez
  danych, unieważnienie w trakcie → 401, wygaśnięcie, 429, jedna kalkulacja
  naraz, obrazy symboli i widoku z nagłówkami cache, walidacja wpisów).
- Integracja PostgreSQL: 6/6 (w tym zapis wpisu pod routingiem magazynu gry).
- Regresja: szczegóły planszy, wyszukiwarka, sesje — 54/54; ruff czysto;
  mypy nowych modułów czysto; OpenAPI i klient aktualne, `admin-api-client`
  69/69.

- Audyt niezależnego agenta `claude-fable-5-1`: cykl 1 FAIL — P2 zbyt długi
  wzór wykonywał wyszukiwanie bez wpisu i kończył się 500; P2 odejście od
  D-472 (osobna transakcja) bez wpisu w DECISION_LOG. Poprawki: limit 15
  komórek po 67 znaków i walidacja wpisu przed odczytem (test), D-475, plan
  R5, kontrakt. P3 pozostawione: `details` błędów routingu magazynu na
  trasach publicznych (mało osiągalne), podwójne liczenie limitu JSON i
  kalkulacji, słabe ETagi bez 304.
- Cykl 2 audytu: PASS, bez otwartych P0–P2.

### Not completed / notes for later tasks

- Wspólny UI wysyła do wyszukiwania tylko znane symbole; aby dziennik miał
  pola `?`, klient musi je przesyłać (`cellIndex:?`) — do zrobienia w
  TASK-0771 razem z odtworzeniem.
- Wrapper klienta dla tras publicznych powstaje w TASK-0768 razem z
  adapterem Reviewera.
