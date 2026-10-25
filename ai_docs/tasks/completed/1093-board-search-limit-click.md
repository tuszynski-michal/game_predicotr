---
title: Jedno kliknięcie wyszukiwania po zmianie wzoru i limitu
status: done
---

# TASK-1093 — Jedno kliknięcie wyszukiwania po zmianie wzoru i limitu

## Status

`done`

## Goal

Usunąć P2-4: zmiana limitu i natychmiastowe kliknięcie Szukaj ma wysłać aktualny wzór z nowym limitem za pierwszym razem.

## Context

Polecenie operatora 2026-10-25: poprawić P2-4, dodać odtworzenie, sprawdzić regresje i zrobić commit. P2-3 zostawić. Bez migracji bazy operatora, restartów, merge ani push. Niezależna mała poprawka po zamknięciu TASK-1092, na tej samej gałęzi roboczej.

## Dependencies / entry conditions

Punkt startu: v1.7.469 / 921921fc, czysty worktree. Numer 1093 sprawdzony w lokalnych refs i aktywnych worktree. P2-4 pochodzi z audytu R2; dotychczas był wnioskiem statycznym. Najpierw test rzeczywistych zdarzeń w przeglądarce na niezmienionym kodzie, potem poprawka i ponowienie.

## Recommended execution

gpt-6.1-sol / high. Mała zmiana współdzielonego React UI, wymagająca testu kolejności blur/click oraz regresji kalkulatora i management. Pierwotne wykonanie bez delegowania i nowego audytu. Po commicie operator osobno zatwierdził 2026-10-25 audyt tej poprawki i koszt: Claude Code claude-opus-5-5 / medium, maksymalnie 480 s, tylko do odczytu.

## Relevant docs

- AGENTS.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/requirements/ADMIN_APP.md — wyszukiwarka, D-573
- ai_docs/architecture/API_CONTRACT.md — kontrakt ciągu D-573 (bez zmian)
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — zachowanie B
- ai_docs/quality/TASK-1092_AUDIT_claude-opus-5-5.md — P2-4
- ai_docs/quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md

## Scope

- Odtworzenie pointer/blur/click w istniejącym skończonym browser fixture.
- Przy zmienionym drafcie zatwierdzenie limitu tylko zapisuje limit; jawne Szukaj wysyła bieżący draft. To świadoma korekta zachowania po P2-1: nie ponawiamy już automatycznie starego snapshotu dla brudnego draftu.
- Przy niezmienionym drafcie zachować automatyczne odświeżenie widocznego snapshotu, wybór wyniku i oczekiwanie na kalkulator.
- Regresje wspólnego UI, obu publicznych adapterów, restore i management.

## Out of scope

P2-3, API, schemat/migracje, dane operatora, restarty, merge i push. Po osobnej zgodzie operatora zakres rozszerzono wyłącznie o jeden audyt poprawki P2-4 po commicie, medium/480 s.

## Acceptance criteria

- [x] Test rzeczywistych zdarzeń odtwarza błąd na kodzie sprzed poprawki.
- [x] Pierwsze kliknięcie po edycji wzoru i limitu wysyła wyłącznie nowy wzór z nowym limitem w Adminie, pojedynczym linku i panelu.
- [x] Brudny draft nie powoduje automatycznego żądania ze starego snapshotu przy zatwierdzeniu limitu; czysty draft nadal odświeża wyniki i czeka na kalkulator.
- [x] Lint/format/typy, testy jednostkowe/interakcji i browser fixture PASS; dokumentacja, mapa i commit rozliczone.

## Technical notes

Oddzielić porównanie draftu z widocznym zapytaniem od ogólnego stale (który obejmuje także limit/loading/error). commitLimit nie kolejkuje repeatWithLimit, gdy zmieniły się komórki wzorów. Nie ingerować w identity resultClient (P2-3). Zachować snapshot, scope, limity, busy i ochronę starych odpowiedzi.

## Expected files

Istniejące: packages/board-search-ui/src/use-board-search-sequence.ts, src/board-search-workspace.tsx, test-interactions/board-search-sequence.test.mjs i test-browser/board-search-sequence.mjs. Dokumentacja taska, odbioru, wymagania i mapa. Nie są planowane nowe moduły aplikacji.

## Test cases

Browser: udane wyszukiwanie, edycja wzoru, wpisanie limitu, pojedynczy rzeczywisty click przy fokusie w polu limitu; liczba i treść żądań, brak drugiego click. Także czysty wzór i Enter. Interakcje: brudny draft podczas kalkulacji nie kolejkuje starego snapshotu, czysty zachowuje kolejkę i wybór.

## Verification

Istniejące npm test/test:interactions/typecheck board-search-ui, ESLint zmienionych plików; node packages/board-search-ui/test-browser/board-search-sequence.mjs. Każda komenda subprocess timeout=120 s. Browser fixture wymaga loopback i izolowanego headless Edge poza sandboxem, nie uruchamia usług aplikacji.

## Risks / open questions

Brak pytań blokujących i nowych decyzji domenowych. Fizyczny Android poza zakresem; mobilny viewport to emulacja. P2-3 nadal odłożone na wyraźne polecenie operatora.

## Outcome

Commit: v1.7.470 / `efaa3c507721c427fa8c3978d9871d132b6a3779`.

### Changed

- Hook udostępnia draftChanged jako porównanie komórek z widocznym snapshotem, niezależnie od limitu, loading i error. Ogólny baner stale zachowuje wcześniejsze warunki.
- commitLimit zapisuje limit bez automatycznego żądania, gdy draft jest zmieniony. Dzięki temu blur nie rozpoczyna starego zapytania przed docelowym click. Niezmieniony wzór nadal automatycznie odświeża wyniki przez tę samą kolejkę busy.
- Dodano rzeczywisty test pointer/blur/click w headless Edge z opóźnieniem 100 ms w fixture oraz wariantem natychmiastowej odpowiedzi. Sprawdzane są dokładna liczba i treść żądań, nowy limit i zachowanie wybranego wyniku przy czystym wzorze.
- Świadomie skorygowano test starego zachowania P2-1: automatyczne odświeżenie jest teraz sprawdzane dla czystego wzoru, a osobny test brudnego wzoru potwierdza brak starego zapytania także po zakończeniu kalkulacji i pełne body po jawnym Szukaj. To zmiana kontraktu UX zlecona poprawką P2-4, nie osłabienie testu dla zielonego wyniku.

### Verification results

- RED na kodzie aplikacji z v1.7.469: nowy browser test kończy się asercją FAIL. Przy szybkiej odpowiedzi otrzymano dwa żądania (stary i nowy wzór), przy opóźnieniu 100 ms tylko stary wzór bez nowej komórki; docelowe click przepadało. Oba logi lokalnie: artifacts/board-search-sequence-browser/p2-4-before-fix.log oraz p2-4-before-fix-slow.log. To oczekiwana porażka odtwarzająca, nie błąd środowiska.
- GREEN tym samym testem po poprawce: browser fixture 14 kontroli PASS, zero błędów strony. Admin GET, oba linki POST, pojedynczy rzeczywisty click, szybka/opóźniona odpowiedź; czysty limit i Enter zachowują wybór. Zachowane wcześniejsze kontrole localStorage po nowym procesie oraz desktop/mobile viewport 390 px.
- Dedykowany plik interakcji: 20 PASS. Pełny pakiet board-search-ui: 108 jednostkowych PASS (1,00 s), 114 interakcji PASS (20,50 s), w tym management, badże, replay/restore, kalkulator, korekty, supergry i wcześniejsze race conditions.
- ESLint wszystkich czterech zmienionych plików UI/testów PASS, końcowy lint browser harness i Prettier --check PASS. Typecheck board-search-ui, Admina i Reviewera PASS.
- Produkcyjne buildy Admina i Reviewera PASS. Pozostało wcześniejsze ostrzeżenie Next o wielu lockfile w zagnieżdżonym worktree; konfiguracji innych obszarów nie zmieniano.
- Mapa zregenerowana i aktualna, docs:check oraz git diff --check PASS. Kontrole dokumentacji powtórzono po zamknięciu taska.
- Wszystkie skończone komendy miały timeout ≤120 s. Browser fixture działał poza sandboxem z loopback i nowym profilem Edge, bez usług aplikacji i danych operatora. Po wprowadzeniu opóźnienia uściślono oczekiwanie na odpowiedź przed nawigacją wyników w harnessie; nie zmieniano asercji odtwarzającej błąd.

### Audit po commicie — zgoda 2026-10-25

Operator zlecił jeszcze audyt Claude Code poprawki P2-4 i zatwierdził koszt: claude-opus-5-5 / medium, maksymalnie 480 s. Audyt statyczny, tylko do odczytu; bez migracji operatora, restartów i merge.

Zakres dla audytora: commit efaa3c507721c427fa8c3978d9871d132b6a3779 względem 921921fc6cb23ba39da9e6d61182cc115ad30a5a, odpowiadające fragmenty use-board-search-sequence.ts i board-search-workspace.tsx oraz zmienione testy test-interactions/board-search-sequence.test.mjs i test-browser/board-search-sequence.mjs. Sprawdzić usunięcie P2-4, trafność asercji rzeczywistych zdarzeń, zachowanie brudnego/czystego draftu, busy oraz brak naruszenia wyboru wyniku i innych konsumentów. P2-3 pozostaje świadomie odłożone; nie jest przedmiotem tej poprawki. Wyniki testów w Outcome należą do wykonawcy, audytor nie ma ich uruchamiać. To runda 1 audytu TASK-1093, odrębna od R1/R2 TASK-1092.

Wynik: [PASS — audyt Claude Code TASK-1093](../../quality/TASK-1093_AUDIT_claude-opus-5-5.md), runda 1, claude-opus-5-5 / medium, zakończony w limicie 480 s. Brak P0/P1. Audytor potwierdził minimalny zakres poprawki, usunięcie przyczyny blur/click dla brudnego draftu oraz zachowanie odświeżania czystego wzoru. Nie uruchamiał testów ani nie zmieniał plików; po audycie wykonawca również nie zmieniał kodu aplikacji i testów. Bez automatycznego ponawiania audytu.

Nowe uwagi z tego raportu (identyfikatory lokalne dla TASK-1093, odrębne od TASK-1092):

- P2-1: odświeżenie zakolejkowane przy jeszcze czystym wzorze i zajętym kalkulatorze nie jest anulowane, jeśli dopiero później użytkownik zmieni wzór. Po zakończeniu kalkulatora może ruszyć stary snapshot i na krótko zablokować Szukaj. To węższe resztkowe ryzyko, wskazane statycznie; nie było przedmiotem testu odtwarzającego P2-4. Zalecana dalsza poprawka: anulowanie takiego odświeżenia i osobny test kolejności commit limitu → edycja → koniec kalkulatora.
- P2-2: browser test powinien ponownie sprawdzać dokładną liczbę żądań po zakończeniu całego wyszukiwania, aby wykluczyć dodatkowe spóźnione żądanie; obecna asercja występuje po pierwszym wpisie w fixtureRequests.
- P2-3: browser test czystego wzoru obejmuje Enter, ale warto dodać też prawdziwy click po blur limitu z asercją jednego równoważnego żądania. Jest to uwaga o pokryciu testowym, nie odłożona wcześniej uwaga TASK-1092/P2-3 dotycząca identity resultClient.

Pozostawiono je jako jawne P2 po audycie-only, bez deklarowania akceptacji ryzyka przez operatora. Nie uruchamiano nowych testów ani kolejnej rundy audytu. Aktualne zlecenie obejmowało przegląd, nie kolejne poprawki. P2-3 z TASK-1092 pozostaje osobno odłożone na polecenie operatora.

### Not completed

- P2-3 pozostaje odłożone na wyraźne polecenie operatora; resultClient i porty korekt bez zmian.
- Nie wykonywano migracji, restartów, merge, push ani wdrożenia na usługach operatora. API, OpenAPI i schemat nie zmieniały się; testów PostgreSQL nie powtarzano.
- Fizyczny Android nieodebrany; mobile viewport to emulacja. Przy pierwotnym commicie nie uruchamiano nowego audytu Claude; późniejszą osobną zgodę i wynik opisuje sekcja Audit powyżej. Historyczne audyty R1/R2 zachowano bez zmian.

### Documentation updates

- Wymagania zachowania limitu, aktualizacja raportu odbioru i planu nadrzędnego, CURRENT_STATE oraz niniejszy task. Mapa kodu wygenerowana; brak potrzeby nowej decyzji domenowej lub zmiany kontraktu API.
- Definition of Done: kryteria funkcjonalne pokryte testem RED→GREEN, trwałość sprawdzona po nowym procesie, kod/lint/typy/build i regresje zaliczone, dokumentacja i ograniczenia jawne. P2-3 oraz brak fizycznego odbioru Androida nie są raportowane jako naprawione/zaliczone.

### Recommended next task

Odbiór operatora i osobno uzgodnione wdrożenie z migracją 0169. P2-3 może być osobnym przyszłym usprawnieniem; brak zgody na merge/restart.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1093 — P2-4 limit i kliknięcie | gpt-6.1-sol | high | Kolejność zdarzeń React i realnej przeglądarki, mały zakres regresji. | Claude Code claude-opus-5-5 / medium, do 480 s; osobna zgoda operatora 2026-10-25 na audyt po commicie. |
