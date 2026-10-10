---
title: Korekty symboli przez link wyszukiwarki i przegląd operatora
status: done
last_updated: 2026-10-05
---

# TASK-0845 — Korekty symboli przez link wyszukiwarki i przegląd operatora

## Status

`done` — operator zaakceptował Q1/Q2 2026-10-05. Pełny pion zaimplementowany
i zweryfikowany w izolowanym worktree, bez wdrożenia na danych operatora.

## Goal

Odbiorca trwale poprawia symbole plansz przez link online, a operator
odnajduje każdą zmienioną planszę i otwiera jej edytor jednym kliknięciem.

## Context

Operator 2026-10-05 zlecił edycję symboli przez udostępnioną wyszukiwarkę,
oznaczenie korekt przy wyszukiwaniu/stawce oraz łatwy przegląd zmian także
innych plansz w zakresie do 100 000 spinów. D-471 i publiczny proxy obecnie
dopuszczają tylko odczyt; lokalny modal ma już „Popraw symbole”.

## Dependencies / entry conditions

- Q1 zaakceptowane: natychmiastowa zmiana danych.
- Q2 zaakceptowane: również zatwierdzone plansze operacyjne.
- Spójny zaakceptowany zakres planu oraz aktualizacja decyzji D-471/D-473.
- Ponowne sprawdzenie kodu, migracji i zmian zastanych przed implementacją.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`; jeden pion obejmuje publiczny zapis,
atomowość audytu i lokalny przegląd. Istniejący writer obsługuje ponowną
agregację zatwierdzonych plansz; zakres Q1/Q2 jest potwierdzony. Zalecany niezależny
review: `gpt-6-astra`, reasoning `high`, po wyraźnym zleceniu delegowania.

## Relevant docs

- `AGENTS.md`
- `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/delivery/BOARD_SEARCH_SHARE_SYMBOL_CORRECTIONS_PLAN.md`
- `ai_docs/requirements/ADMIN_APP.md` — modal, udostępnianie, dziennik.
- `ai_docs/architecture/API_CONTRACT.md` — powierzchnia udostępniania.
- `ai_docs/architecture/DATA_MODEL.md` — bieżące komórki i audyt decyzji.
- `ai_docs/architecture/SYSTEM_ARCHITECTURE.md` — granica Reviewera.
- `ai_docs/security/REMOTE_REVIEWER_THREAT_MODEL.md` — D-471/bramka TASK-0770.
- `ai_docs/process/DECISION_LOG.md` — D-471, D-472, D-473, D-475, D-478,
  D-486, D-487 i D-492.
- `ai_docs/delivery/BOARD_SEARCH_SHARE_EXECUTION_PLAN.md` — R4–R6.

## Scope

Jeden spójny pion: zapis symboli odbiorcy, trwały audyt z kontekstem i stawką,
oznaczenia dziennika, stronicowana lista plansz do przeglądu oraz istniejący
modal z historią pól i jawnym domknięciem przeglądu. OpenAPI, wygenerowany
klient i jego wrapper pozostają zgodne z backendem.

## Out of scope

Geometria, archiwum, zwiększenie zakresu spinów, trening, usuwanie danych,
wdrożenie, migracja na żywej bazie, restart usług, push i merge.

## Acceptance criteria

- [x] Odpowiedzi Q1/Q2 są zapisane jako decyzje; plan jest spójny z taskiem.
- [x] Odbiorca poprawia startową oraz inną dozwoloną planszę online.
- [x] Audyt i zmiana są atomowe; restart i retry po utracie odpowiedzi działają.
- [x] Korekty i stawka są widoczne w dzienniku, także przy grupowaniu wzoru.
- [x] Lista obejmuje wszystkie zmienione plansze linku, bez liczenia zakresu.
- [x] Klik otwiera modal konkretnej planszy z historią zmienionych pól.
- [x] Jawny przegląd dotyczy rewizji; nowsza korekta pozostaje do przejrzenia.
- [x] Usunięcie wyszukiwania oraz revoke nie kasują audytu korekt.
- [x] Publiczna izolacja i lokalny workflow mają testy regresyjne.
- [x] Dokumentacja, Outcome, Current State i osobny commit są uzupełnione.

## Technical notes

Szczegóły kontraktu, transakcji, idempotencji, skali, błędów i testów znajdują
się w zaakceptowanym planie. Odpowiedzi Q1/Q2 zapisano w D-492.

## Expected files

Sprawdzone istniejące ścieżki i proponowane nowe moduły wymieniono w planie.
Kod obejmuje API, domenową mutację komórki, audyt sesji, wspólne UI,
Reviewer, Admin i klient OpenAPI. Zastane modyfikacje `CURRENT_STATE.md`,
ukończonych tasków i `package-lock.json` należą do użytkownika.

## Test cases

Mapa wymaganie → test w planie. Szczególnie: kilka kart, dalsza plansza,
zapis audytu z rollbackiem, utracona odpowiedź, restart, revoke podczas
zapisu, konkurencyjna korekta i usunięcie wyszukiwania bez utraty historii.

## Verification

Sprawdzone nazwy istniejących suites i poleceń znajdują się w planie.
Wyniki wykonanych kontroli znajdują się w Outcome.

## Risks / open questions

- Q1/Q2 zapisano w D-492; otwartych decyzji produktowych brak.
- Wariant natychmiastowy wpływa na wyszukiwanie przed przeglądem operatora.
- Odbiór fizycznego Androida i publicznego tunelu wymaga osobnego wdrożenia.

## Outcome

### Changed

- Publiczny zapis jednej komórki po pozycji z opaque SHA, kodem aktywnego
  symbolu i UUID operacji. Gra i aktor pochodzą z sesji. Edycja również
  zatwierdzonych bieżących plansz używa istniejącego writera.
- Atomowa decyzja, domenowy audyt, projekcja i receipt linku; migracja
  `0141_share_symbol_corrections` rozszerza metadane oraz pięć indeksów.
  Bez obrazów, drugiej tabeli etykiet lub zmiany zamrożonych manifestów.
- Jawny kontekst wyszukiwania, snapshot wzoru/zakresu/stawki i cache karty;
  trwały request w sessionStorage pozwala jawnie odzyskać utracony zapis.
- Liczniki przy grupowanym wzorze i stronicowana lista całego linku;
  startowa/dalsza plansza, stawka, czas i filtry. Modal otwiera się w trybie
  edycji z historią przed/po i wyróżnieniem pól.
- Przegląd porównuje monotoniczną rewizję linku i SHA wszystkich aktualnych
  komórek. Zegar nie ustala granicy przeglądu. Zatwierdzenie oczekującego
  pola jest zmianą; semantyczny no-op nie tworzy nowej pracy. Historia
  pozostaje po usunięciu wyszukiwania i revoke.
- Backend, OpenAPI, wygenerowany klient, wrapper i testy żądań są spójne.
- Commit implementacji: `v1.7.190` — `c61c1e65f87e89e7669507cb902e6348fe3cc48e`.

### Verification results

- PostgreSQL: `test_board_search_share_corrections.py` — PASS (66,32 s).
  Mały fixture 3 plansz; faktyczny HTTP i writer, zawinięty dystans 100 000,
  startowa/dalsza oraz zatwierdzona plansza, jawny kontekst dwóch kart,
  exact retry także w nowym procesie API, różne body UUID, konflikty,
  no-op, nieczytelność/siatka, cofnięty zegar, przegląd/nowsza poprawka,
  paginacja, usunięcie wzoru, rollback audytu/503 i revoke pod blokadą.
- API: public share, query log, board detail i schema readiness — 62 PASS;
  asercja nowego ID kontekstu została zaktualizowana i przeszła osobno (1 PASS).
- Frontend: klient API 80/80, shared pure 77/77, shared interactions 39/39,
  Reviewer 214/214 i Admin pure 624/624. Nowa kolejka przeszła test
  otwarcia/edycji, pozostawienia pending po zamknięciu i konfliktu przeglądu.
- Ruff check/format zmienionych plików; lint czterech workspace; TypeScript
  klienta, shared UI, Reviewera i Admina; scoped strict Mypy 10 modułów;
  eksport OpenAPI `--check` i `check:generated` — PASS.
- Build Admina 26,9 s i Reviewera 21,4 s — PASS; bez uruchamiania usług.
- UI w Chromium na danych testowych: desktop 1280×900 i telefon 390×844,
  lista → modal → paleta → lokalny zapis → jawny przegląd, bez poziomego
  overflow. Przyciski przeglądu 44 px; tekstowa historia niezależna od koloru.
  Podgląd: `artifacts/task0845-preview-mobile.jpg` w głównym checkoutcie.
- Szerszy strict Mypy wykrył wcześniejsze cieniowanie `list` w grupowaniu
  `BoardSearchShareQueryLogService`; odtworzono je z pliku HEAD sprzed taska.
  Szersze Admin interactions: 33 PASS, 6 wcześniejszych FAIL w
  `symbol-review-partial`, przez dwie wersje Reacta 19.2.3/19.2.8.
  Nowy test używa trwałego loadera zgodnego z pojedynczym runtime Nexta;
  nie zmieniano zależności ani niezwiązanych testów.
- Logi w izolowanym `artifacts/task0845-checks/`. Definition of Done i
  zaakceptowany plan porównano punkt po punkcie; zakres funkcjonalny spełniony.

### Not completed

- Bez wdrożenia, migracji na bazie operatora, restartu usług i push.
  Scalenie zostało osobno zlecone i opisane poniżej.
  Migrację wykonano wyłącznie w nowej bazie testowej, automatycznie usuniętej
  przez istniejący fixture. Nie wykonywano benchmarku ani fixture 100 000 plansz.
- Nie wykonywano niezależnego review innym modelem (brak zlecenia delegacji),
  odbioru na fizycznym Androidzie ani przez publiczny tunel.
- Niezwiązane błędy szerszych kontroli pozostawiono poza zakresem commita.

### Documentation updates

- D-492, zaakceptowany plan, wymagania Admina, API Contract, Data Model,
  System Architecture, threat model, Outcome oraz `CURRENT_STATE.md`.

### Recommended next task

- Po osobnym zleceniu wykonać migrację i wdrożenie, następnie odbiór
  fizycznego Androida i publicznego linku.

### Integration into the main development branch — 2026-10-05

- Operator explicitly requested merge into `v1.1-vision-lab-hybrid-geometry`
  and removal of the task worktree and `codex/share-symbol-corrections` afterwards.
- Merge preserves both parents: TASK-0846 (`222be446718c4655b51fe4bb54de0a3f3baeb045`)
  and TASK-0845 (`c61c1e65f87e89e7669507cb902e6348fe3cc48e`). Only documentation
  required conflict resolution; both decisions and task sections were retained.
- Uncommitted operator changes remain outside the merge commit. Verification logs
  were copied to the primary checkout before the requested worktree cleanup.
- Merge commit: `v1.7.191` — `317a07c91bc1429804187d7cc7eebd1a47691770`.
- No live database migration, deployment, service restart, or push.
- Post-merge verification: API/share 19 PASS, board detail/schema 29 PASS,
  grid-audit regression 15 PASS, isolated PostgreSQL correction/restart/revoke
  scenario 1 PASS (51.60 s), API client 80 PASS, Reviewer 214 PASS,
  shared interactions 39 PASS, owner queue interaction 1 PASS.
- Backend OpenAPI comparison, generated client comparison, and TypeScript for
  all four affected workspaces PASS. Existing TASK-0846 contract is retained.
- Initial combined API run reached the 110-second limit without an assertion
  failure; no orphan process remained. Smaller groups above completed normally.
  A Windows console encoding error affected only printing successful check logs;
  the saved logs and exit codes confirm the actual checks passed.
- Full builds were already verified for TASK-0845; they were not repeated during
  this merge to avoid replacing outputs of currently running applications.
- Cleanup completed: the app archived the managed worktree with a recoverable
  snapshot, removed the checkout from disk and the Git worktree registry, and
  `git branch -d` removed the merged `codex/share-symbol-corrections` branch.
  Separate process checks confirm the checkout path and branch no longer exist.
  Other worktrees and uncommitted operator/concurrent changes were preserved.
