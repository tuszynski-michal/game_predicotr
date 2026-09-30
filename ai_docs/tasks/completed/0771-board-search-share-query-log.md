---
title: TASK-0771 — Dziennik zapytań udostępnionego linku i odtworzenie w Adminie
status: done
last_updated: 2026-09-30
---

# TASK-0771 — Dziennik zapytań udostępnionego linku i odtworzenie w Adminie

## Status

`done`

## Goal

Operator widzi w Adminie, kiedy i jakie zapytania wykonano przez dany link, i
jednym przyciskiem odtwarza każde z nich w swojej sekcji „Wyszukaj plansze”.

## Context

Dopisek operatora z 2026-09-30 do punktu 5 (punkt 6), decyzja D-472.
Specyfikacja: plan §3 R5, §4.3–4.4 i §5 T11.

## Dependencies / entry conditions

- TASK-0766, TASK-0767 i TASK-0769 done. Wykonywany po TASK-0769, przed
  TASK-0770.
- Etap B wymaga osobnego polecenia operatora.

## Recommended execution

`claude-opus-5-5`, reasoning `high` (wiersz T11 w tabeli planu). Migracja,
dane o odbiorcy i odtworzenie stanu wyszukiwarki. Audyt: niezależny agent
`claude-fable-5-1` (`high` warunkowo). Dwa nieudane cykle poprawek P0–P2
zatrzymują etap.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md`
- `ai_docs/process/DECISION_LOG.md`
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md`
- `ai_docs/architecture/API_CONTRACT.md`

## Scope

Zakres, pliki, przypadki testowe i kryteria według planu §5 T11. Przed
startem ponownie sprawdzić kod po TASK-0765–0769 i doprecyzować ten plik.

## Out of scope

- Zapis adresu IP i nagłówków przeglądarki.
- Automatyczna retencja i usuwanie wpisów.
- Odtwarzanie stawki i jednostki odbiorcy.

## Acceptance criteria

- [ ] Kryteria akceptacji planu §5 T11 spełnione.
- [ ] Brak otwartych uwag P0–P2 audytu.

## Technical notes

Patrz plan §3 R5 i §5 T11.

## Expected files

Patrz plan §5 T11.

## Test cases

Patrz plan §5 T11.

## Verification

```powershell
# komendy według planu §5 (wspólne polecenia weryfikacji)
```

Wszystkie komendy z katalogu worktree, timeout 120 s każda.

## Risks / open questions

- Dziennik zawiera dane o zachowaniu odbiorcy; zakres zapisu ograniczony
  przez D-472.

## Outcome

### Changed

- Zapis wpisów, tabela i walidacja powstały w TASK-0766/0767 (D-475). Tu:
  odczyt dla Admina — kursor `(occurred_at, id)` w domenie,
  `BoardSearchShareQueryLogService` (lista 50/stronę, odtworzenie z
  najbliższym wcześniejszym udanym wyszukiwaniem i zakresem),
  `SqlAlchemyBoardSearchShareQueryRepository`, trasy
  `GET /admin/board-search-shares/sessions/{id}/queries` i
  `GET /admin/board-search-shares/queries/{eventId}`, OpenAPI, klient i
  wrapper (`listBoardSearchShareQueries`, `getBoardSearchShareQueryReplay`).
- Wspólna sekcja: wyszukiwanie wysyła też pola `?` (zapis pełnego wzoru);
  prop `replay` odtwarza wzór (nieaktywny symbol → `?` z ostrzeżeniem),
  zakres i limit, jedno wyszukiwanie, potem wybiera planszę startową i
  otwiera „Przybliżoną wygraną” z zakresem, a dla szczegółów planszy jej
  okno; braki są komunikowane zamiast zgadywania.
- Admin: „Dziennik zapytań” w panelu dla każdego linku (mini-plansza 3 × 5
  z ikonami, zakres, limit, wynik, błąd, „Starsze zapytania”), przycisk
  „Odtwórz w wyszukiwarce” (`?boardSearchReplay=<id>`); katalog pobiera
  odtworzenie, przełącza na grę i sekcję wpisu, zużywa parametr; brak
  wcześniejszego wyszukiwania → komunikat z parametrami wpisu.
- `API_CONTRACT.md`, `ADMIN_APP.md`.

### Verification results

- API: `test_board_search_share_query_log.py` 7/7 (stronicowanie bez
  duplikatów przy równym czasie, obca sesja poza listą, limity, kursor,
  odtworzenie wszystkich rodzajów i brak wcześniejszego wyszukiwania,
  HTTP); integracja PostgreSQL 7/7 (stronicowanie i odtworzenie na
  prawdziwych wierszach, brak kolumn IP/nagłówków); ruff, mypy nowych
  modułów czyste; OpenAPI i klient aktualne, `admin-api-client` 70/70.
- Pakiet UI: testy 77/77, interakcje 38/38 (w tym odtworzenie: ten sam
  wzór, zakres i limit, jedno wyszukiwanie; zakres z planszą startową i
  oknem planszy; brak planszy startowej; nieaktywny symbol; ręczne
  wyszukiwanie wysyła `?`).
- Admin: testy 597/597, interakcje panelu 6/6 (dziennik, mini-plansza,
  odtworzenie), typecheck czysty, lint bez nowych uwag, `next build` OK;
  typecheck Reviewera czysty.
- Audyt niezależnego agenta `claude-fable-5-1`: cykl 1 FAIL — P2
  odtworzenie wracało po każdym ponownym zamontowaniu sekcji (zwinięcie,
  zmiana gry) i nadpisywało ręczną pracę. Poprawka: sekcja zgłasza przejęcie
  (`onReplayApplied`), katalog porzuca plan (`consumeBoardSearchReplay`,
  test). P3 poprawione: komunikat dla szczegółów planszy bez wcześniejszego
  zakresu, komunikat przy błędzie wczytania odtworzenia, błąd „Starszych
  zapytań” nie usuwa wczytanych wpisów.
- Cykl 2 audytu: PASS, bez otwartych P0–P2 (pozostałe P3: brak zamykania komunikatów odtworzenia).
- Ręczny odbiór z prawdziwymi wpisami wymaga migracji `0129` na bazie
  deweloperskiej (zgoda operatora).
