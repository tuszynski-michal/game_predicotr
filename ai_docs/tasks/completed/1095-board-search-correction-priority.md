---
title: Pierwszeństwo korekty i zakończone odpowiedzi fixture
status: done
---

# TASK-1095 — Pierwszeństwo korekty i zakończone odpowiedzi fixture

## Status

`done`

## Goal

Poprawić obie nowe uwagi TASK-1094/P2-1–2 i poddać poprawki jednemu audytowi Claude Code przed commitem.

## Context / entry conditions

Operator 2026-10-25: „popraw wszystko i wykonaj audyt”, w odpowiedzi na dwie nowe uwagi TASK-1094. Dawne TASK-1092/P2-3 pozostaje odłożone zgodnie z poprzednią instrukcją. Bez migracji bazy operatora, restartów, merge i push. Punkt startu: czysty worktree, v1.7.475 / 28a86ce2. Numer 1095 sprawdzony w historii wszystkich lokalnych refs i plikach aktywnych worktree; brak kolizji. Brak pytań blokujących ani zmian kontraktu API.

## Recommended execution

gpt-6.1-sol / high; mała poprawka React i synchronizacji fixture. Jeden wymagany audyt Claude Code claude-opus-5-5 / medium, do 480 s, tylko do odczytu. Po jednej rundzie poprawek bez automatycznej pętli audytów. Zakres i zgoda na audyt wynikają z bieżącego polecenia, konfiguracja zachowana z poprzedniego audytu.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md i TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ADMIN_APP.md — D-573, limit i korekty
- ai_docs/architecture/API_CONTRACT.md — bez zmian
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — zachowanie B
- ai_docs/quality/TASK-1094_AUDIT_claude-opus-5-5.md
- ai_docs/quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md

## Scope / Technical notes

- P2-1: repeatWithLimit używa funkcyjnej aktualizacji kolejki; zachowuje reason=correction, jeśli taka przyczyna już czeka. Zmienia tylko limit opcji i zachowuje snapshot korekty. Zwykła kolejka limitu nadal jest anulowana po edycji.
- P2-2: fixture rejestruje zakończone odpowiedzi wyszukiwania dla Admina i obu publicznych adapterów. Końcowe asercje czekają na zakończenie konkretnego żądania, potem na stan gotowego UI; sam obecny nagłówek nie dowodzi zakończenia. Wyłącznie w fixture ocena wyniku dla limitów 7/8/9 ma odpowiednio 7/8/9 procent: test musi zobaczyć nową wartość w metryce dopasowania, więc stary przycisk/nagłówek nie wystarczą również w mikroszczelinie przed renderem loading. Nie zmienia to logiki ani oceny w aplikacji.
- Zachować Enter, prawdziwe click, pojedyncze żądania, wybór wyniku, dirty draft, korekty, restore i management.

## Out of scope

TASK-1092/P2-3, API, schemat, dane operatora, restarty, migracje, merge, push, fizyczny Android. Bez nowych zależności i szerokich refaktorów.

## Expected files

Istniejące packages/board-search-ui/src/use-board-search-sequence.ts (repeatWithLimit), test-interactions/board-search-sequence.test.mjs (regresja kolejki), test-browser/board-search-sequence.mjs (fixture i limitClickRegression). Wymagania, raport odbioru, CURRENT_STATE, task i raport audytu; generowana mapa, jeśli zmieniona. Brak nowych modułów aplikacji.

## Acceptance criteria / Test cases

- [x] Test RED odtwarza korekta → limit → edycja → koniec kalkulacji. Po poprawce dokładnie jedno odświeżenie snapshotu korekty z najnowszym limitem i ponowne obliczenie zakresu; draft nadal zmieniony.
- [x] Kolejność limit → korekta oraz zwykłe anulowanie limitu nie regresują.
- [x] Browser fixture czeka na zakończoną odpowiedź i gotowe UI przed końcową asercją liczby/treści żądań; Admin/share/panel, Enter/click, odpowiedzi natychmiastowe i opóźnione.
- [x] Unit/interactions, lint/format, typy, buildy, docs/map PASS. Jeden audyt rozliczony, bez otwartych P0/P1, zamknięcie skryptem i commit.

## Verification

Istniejące npm test i test:interactions board-search-ui, test Reviewer, typecheck board-search-ui/Admin/Reviewer, ESLint/Prettier trzech plików. Browser: node packages/board-search-ui/test-browser/board-search-sequence.mjs, skończony fixture i izolowany Edge, bez usług aplikacji. Buildy Admin i Reviewer. scripts/generate_code_map.py, code-map:check, docs:check, diff --check. Każda skończona komenda przez subprocess.run(timeout=120); git/odczyty do 30 s. Audyt scripts/audit_task.ps1 -Task 1095 -Auditor claude -Model claude-opus-5-5 -Effort medium -TimeoutSec 480 z wrapperem 600 s, ograniczony do plików taska.

## Risks / open questions

Zwykły limit nie może zmienić przyczyny oczekującej korekty. Licznik odpowiedzi fixture jest dowodem zakończenia transportu; osobno trzeba poczekać na render UI. Fizyczny Android pozostaje nieweryfikowany.

## Outcome

Commit: v1.7.476 (hash dopisuje kolejny commit).

### Changed

- TASK-1094/P2-1: repeatWithLimit aktualizuje kolejkę funkcją, zachowuje reason=correction oraz jej options, zmieniając limit i zachowanie wyboru. Nie zmieniono zwykłego anulowania oczekującego limitu.
- Dwa testy interakcji: korekta przed limitem i limit przed korektą, potem kolejny limit 9, edycja wzoru i koniec kalkulacji. Dokładnie jedno odświeżenie widocznego snapshotu z limitem 9 i ponowna kalkulacja od tego samego końca; draft pozostaje zmieniony.
- TASK-1094/P2-2: wspólny fixtureSearch rejestruje żądanie oraz gotową odpowiedź dla Admina i publicznego adaptera. waitForSearchResponse czeka na odpowiedź i metrykę z nowego renderu, następnie na gotowy przycisk; asercje weryfikują dokładnie jedną odpowiedź i dokładnie jedno żądanie. Ocena równa limitowi jest wyłącznie syntetycznym znacznikiem fixture, bez zmian w domenie aplikacji.

### Verification results

- RED: oba nowe testy na starym hooku wykazały 1 żądanie zamiast 2, czyli brak odświeżenia korekty. Log artifacts/board-search-sequence-browser/task-1095-red.log. Po poprawce oba PASS.
- board-search-ui: npm run test 108/108 PASS, test:interactions przed audytem 118/118 PASS, po rundzie poprawek 119/119 PASS, w tym dotychczasowe anulowanie limitu, dirty commit, korekty, replay/restore, busy i management. Końcowy log task-1095-interactions-final.log.
- Browser fixture: 18/18 kontroli PASS, failures=[], Admin/share/panel, realne Enter/click, odpowiedzi 100 ms i natychmiastowe, wybrany wynik, desktop oraz viewport 390×844, przywrócenie po nowym procesie Edge. Powtórzony po zmianie indeksu odpowiedzi: 18/18 PASS. Logi task-1095-browser.log, task-1095-browser-final.log i verification.json w ignorowanym artifacts/board-search-sequence-browser/.
- Reviewer: npm run test 293/293 PASS, w tym adaptery, proxy i izolacja dostępu.
- ESLint i Prettier --check trzech zmienionych plików PASS, ponowione po poprawkach testów. Typecheck board-search-ui/Admin/Reviewer PASS; kod produkcyjny i typy nie zmieniały się po tym wyniku.
- Buildy Admina i Reviewera PASS. Znane ostrzeżenie Next.js o wielu lockfile w zagnieżdżonym worktree poza zakresem. Logi task-1095-build-admin.log i task-1095-build-reviewer.log.
- Mapa kodu wygenerowana, wynik identyczny; code-map:check i diff --check PASS. docs:check oraz kontrole zamknięcia sprawdzane przed commitem.
- Wszystkie skończone komendy weryfikacji miały timeout 120 s; testy i buildy w nowych procesach, Edge z nowym izolowanym profilem. Brak usług operatora i operacji na bazie.

### Audit

Wymagany audyt przed commitem: Claude Code claude-opus-5-5 / medium, jedna runda, limit 480 s, tylko do odczytu. [Raport](../../quality/TASK-1095_AUDIT_claude-opus-5-5.md): PASS, brak P0/P1, w limicie 480 s. Potwierdzone statycznie usunięcie obu uwag TASK-1094/P2-1–2, zachowanie reason=correction i dowód nowego renderu po odpowiedzi. Dawne TASK-1092/P2-3 poza zakresem. Wyniki testów należą do wykonawcy; audytor nie uruchamiał testów i nie zmieniał plików.

Jedna runda poprawek po audycie, bez kolejnej płatnej rundy:

- TASK-1095/P2-1: doprecyzowano ADMIN_APP — aktualizacja limitu oczekującej korekty zachodzi przy niezmienionym wzorze. Po edycji nowy limit jest zapamiętywany dla jawnego wyszukiwania. Dodano trzeci wariant draft-before-limit: korekta odświeża snapshot z limitem 15, a jawne Szukaj wysyła edytowany wzór z limitem 9. Pierwotna asercja tego dodatkowego wariantu błędnie zakładała dopisanie pola; replay zaznacza pole 0, więc poprawiono pełne oczekiwanie na świadome zastąpienie B przez A. Kod aplikacji bez zmian po audycie.
- TASK-1095/P2-2: browser test pobiera osobny stan początkowy fixtureResponses.length przed każdą akcją. Żądania i odpowiedzi mają niezależne indeksy; zachowano pełne asercje ich liczby i treści oraz nowej metryki.

Obie uwagi rozliczone przez wykonawcę w zakresie zlecenia „popraw wszystko”; historyczny raport zachowano bez edycji. Końcowe zmiany dokumentacji i testów sprawdza wykonawca; brak deklaracji drugiego niezależnego audytu. Nie zmieniano kodu produkcyjnego po werdykcie.

### Not completed

Dawne TASK-1092/P2-3 nadal odłożone. Nie wykonywano migracji bazy operatora, restartów, merge, push ani wdrożenia. Brak zmian API/schematu, bez powtarzania PostgreSQL. Fizyczny Android nieodebrany; mobilny viewport to emulacja.

### Documentation updates / Definition of Done

ADMIN_APP doprecyzowuje, że limit nie usuwa potrzeby odświeżenia po korekcie. Raport odbioru i CURRENT_STATE rozliczają poprawki oddzielnie od historycznych audytów. Brak nowych decyzji domenowych lub architektonicznych. AC1–2: RED→GREEN oraz pełne żądanie i kotwica zakresu. AC3: nowy receipt odpowiedzi i wyrenderowana metryka, 18 kontroli Edge PASS. AC4: kontrole kodu i buildy PASS, audyt i zamknięcie przed commitem. Zachowania planu B pokrywają istniejące regresje, trwałość sprawdzona w nowym procesie.

### Recommended next task

Po rozliczeniu audytu odbiór operatora oraz osobno uzgodnione wdrożenie. Migracja 0169, restarty i merge mają osobne zgody. Dawne TASK-1092/P2-3 pozostaje na później.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1095 — Dwie P2 z TASK-1094 | gpt-6.1-sol | high | Mała zmiana priorytetu kolejki i dowodu zakończenia odpowiedzi w fixture. | Wymagany Claude Code claude-opus-5-5 / medium, jedna runda do 480 s przed commitem. |
