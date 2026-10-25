---
title: Wyszukiwanie ciągu plansz — badże i trwałość
status: done
---

# TASK-1092 — Wyszukiwanie ciągu plansz — badże i trwałość

## Status

`done`

## Goal

Udostępnić badże 1–4 wpisanych wzorów, wspólne wyniki i trwały lokalny zestaw w Adminie oraz obu linkach.

## Context

Zadanie B zaakceptowanego planu; operator zlecił cały plan i zaakceptował koszt 2026-10-24. Bez migracji operatora, restartów i scalenia do main.

## Dependencies / entry conditions

Zamknięty TASK-1091. Ponowny odczyt taska i zaakceptowanego planu przed kodowaniem B. Wspólny workspace zachowuje dotychczasowe zachowanie management.

## Recommended execution

gpt-6.1-sol / high. Stan kilku widoków, trwałość i race conditions. Audyt Claude Code claude-opus-5-5 / medium przed commitem; zakres/koszt zaakceptowany poleceniem całego planu. Niedostępność konfiguracji albo otwarte P0/P1 po poprawkach zatrzymują zadanie.

## Relevant docs

- AGENTS.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/process/DEFINITION_OF_DONE.md
- ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md — B i reguły UX
- ai_docs/requirements/ADMIN_APP.md
- ai_docs/architecture/API_CONTRACT.md
- ai_docs/architecture/CODE_MAP.md i CODE_MAP_SYMBOLS.md

## Scope

- Opcjonalna metoda sequence w data source, badże i przyciski, oddzielny stan edytora i wspólnych wyników.
- localStorage ze scope gry/linku/panelu, restore po dostępie, replay przed restore.
- Podgląd ostatniej planszy, detale pozostałych, korekty, wygrane od końca ciągu.
- Koordynacja kalkulatora i wyszukiwania, stare odpowiedzi, błędy, 401/429, brak storage.
- Pełna historia v2 w Adminie oraz liczba układów w widoku korekt.

## Out of scope

Synchronizacja urządzeń, inne aplikacje, offline APK, zmiana wypłat i management workflow, operator DB/restarty/merge/push.

## Acceptance criteria

- [x] Badże przełączają tylko wzór; wspólne wyniki i kotwica wygranej pozostają niezależne.
- [x] Następny/Resetuj/Nowe szukanie i limit 4 zgodne z planem, także puste końce i środkowe luki; usunięcie P1 zakresu potwierdzone w audycie R2.
- [x] Stan odtwarzany po nowym procesie, bez pomieszania gier/linków, bez trwałych odpowiedzi/sekretów.
- [x] Replay wygrywa z localStorage; spóźnione odpowiedzi nie wskrzeszają resetu.
- [x] Korekty, supergry, wygrane i management mają testy regresyjne; oba rodzaje linku działają.
- [x] Lint/typy/interakcje/docs/mapa i niezależny audyt rozliczone; R2 PASS, ograniczenia odbioru i P2 jawne.

## Technical notes

Stany, klucze, interakcje i błędy według planu 3.1 B. Opcje wspólnych komponentów są opcjonalne. Jeden wzór nadal korzysta z GET. Badż nie zmienia stawki/pinów/wyboru wyniku. Zapis ma nie utrwalać contextId, credential ani wyników API.

## Expected files

- Istniejące: packages/board-search-ui/src/board-search-workspace.tsx, board-search-data-source.ts, board-search-approximate-win.tsx, wspólny CSS i eksporty.
- Istniejące: adapter/gates Reviewera; wrapper/workspace Admina; replay/log/korekty Admina.
- Proponowane: board-search-sequence-state.ts i dedykowane testy stanu/interakcji.

## Test cases

Mapa B planu: wszystkie przyciski i 4 badże, luki i ?, stare odpowiedzi po reset/scope, restore i zły storage, replay>restore, 401/429, wygrane od końca, korekta wcześniejszej planszy, obie powierzchnie publiczne i management. Web mobile; fizyczny Android tylko gdy dostępny bez restartowania usług.

## Verification

Testy jednostkowe/interakcyjne board-search-ui oraz zmienionych hostów; lint i typecheck pakietów; docs/OpenAPI/mapa. Każda grupa przez timeout=120 s. Trwałość z nowego procesu przeglądarki albo jawny brak tego odbioru.

## Risks / open questions

Inny origin tunelu nie odzyska localStorage. Odbiór urządzenia i ewentualne blokery środowiskowe opisać bez fikcyjnego PASS.

## Outcome

Commit: v1.7.468 / `402477cdc1c4797fe7ab626b5c5bdbc6519d446c`.

### Changed

- Wspólny workspace obsługuje 1–4 kolejne układy, osobne edytory/undo, wspólne wyniki, Następny/Resetuj/Nowe szukanie i blokowanie luk/samych ?. Jeden wzór nadal używa GET; 2–4 POST.
- Odpowiedź i jej searchContextId są oddzielone od draftu. Badże zachowują wynik, stawkę, piny i kotwicę wygranych; korekty wcześniejszych plansz używają własnej pozycji. Każda plansza ciągu zachowuje akcje supergry.
- localStorage v1 rozdziela Admina, sesje i panele. Zapisuje tylko pola, badż, tryb, ostatnie zapytanie i start; nie zapisuje odpowiedzi, contextId, obrazów ani credential. Replay ma pierwszeństwo; nieaktywny symbol blokuje wysłanie bez cichego zastąpienia.
- Licznik wszystkich trwających kalkulacji i suspended koordynują search/debounce. Odświeżenie po korekcie czeka na koniec kalkulacji i przelicza także tę samą końcową planszę bez resetu stawki. Spóźnione odpowiedzi, reset, nowy scope, 429 i wygaśnięcie mają testy.
- Adapter obu linków posiada cache pełnego uporządkowanego zapytania i jego receipt; korekta/401 czyszczą cache, a starsza generacja nie może go ponownie zapełnić. Korekta jawnie dostaje context aktywnego wyniku.
- Historia v2 pokazuje wszystkie małe plansze, końce ciągów, odtwarza komplet wzorów i filtruje korekty searchEventId. Widok korekt pokazuje pochodne „Ciąg: N układów”. Management zachowuje stary przepływ także przy kliencie mającym metodę sequence.

### Verification results

- board-search-ui: 108 testów jednostkowych PASS; po poprawkach audytu pełne interakcje 113 PASS (21,55 s), w tym 19 nowych testów ciągu. Lint zmienionych plików UI i typecheck po poprawkach PASS. Nowe interakcje obejmują także StrictMode, replay zakresu i brak przejęcia draftu przez inną kartę.
- Reviewer: 293 PASS. Zmienione testy czyste historii/replay i adaptera: 27 PASS (zawierają też regresje legacy); interakcje historii/korekt Admina i rzeczywistego panel gate: 4 PASS.
- Typecheck board-search-ui, Admina i Reviewera PASS. Build produkcyjny obu aplikacji PASS. Next zgłasza istniejące w zagnieżdżonym worktree ostrzeżenie o wyborze katalogu root z wielu lockfile; nie zmieniano konfiguracji innych zadań.
- ESLint zmienionych plików bez błędów; dwa wcześniejsze ostrzeżenia w cleanup requestId Admina i nieużywanym _operationId adaptera. Końcowe lint/typecheck board-search-ui po poprawkach PASS. Prettier zmienionych plików PASS.
- Test przeglądarkowy `packages/board-search-ui/test-browser/board-search-sequence.mjs`: Admin 4 układy, oba publiczne adaptery 2 układy, izolacja, dirty draft i wybór; odczyt po zamknięciu Edge i uruchomieniu nowego procesu. Sześć kontroli PASS, zero błędów strony. Desktop 1280 px i mobile 390 px; wizualna kontrola zrzutów i brak poziomego overflow PASS. Wyłącznie fixture, bez usług aplikacji.
- Lokalny zapis dowodów: `artifacts/board-search-sequence-browser/verification.json`, screenshoty desktop/mobile i logi build/interakcji (ignorowane przez Git). Ograniczenia i mapa odbioru w `ai_docs/quality/BOARD_SEARCH_SEQUENCE_IMPLEMENTATION_20261024.md`.
- API/OpenAPI nie zmieniały się w B; pełny pion oraz kontrola obu klientów PASS w TASK-1091. Mapa kodu zregenerowana; docs i mapa kontrolowane przed zamknięciem.
- Build klienta API po addytywnym eksporcie typu BoardSearchPattern PASS. Po audycie usunięto queryScope, limit ponawia widoczny snapshot po zakończeniu busy, poprawiono walidację replay i łączne ostrzeżenie wildcardów. Dedykowane testy P1-1/P2-1/P2-2 i ostrzeżenia PASS; nie powtarzano audytu bez rozszerzenia zgody na koszt.

### Audit

Audyt Claude Code `claude-opus-5-5` / medium: [R1 REVISE](../../quality/TASK-1092_AUDIT_R1_claude-opus-5-5.md), następnie [R2 PASS](../../quality/TASK-1092_AUDIT_claude-opus-5-5.md), bez P0/P1. Audytor niezależnie potwierdził usunięcie P1-1 i P2-1/P2-2 oraz łączne ostrzeżenie wildcardów. [Pełny zapis poprawek](../../quality/TASK-1092_AUDIT_FIXES_20261024.md). Zachowano oba raporty; nie zmieniano werdyktów audytora.

2026-10-24 operator zatwierdził dodatkowy audyt poprawek B i koszt: Claude Code medium, do 480 s; po PASS zamknięcie i lokalny commit. R2 zakończyła się w limicie. To trzeci audyt implementacji (A timeout, B R1 REVISE, B R2 PASS), nie czwarty audyt planu. Nie uruchamiano dalszych audytów.

R2 była wąskim statycznym audytem poprawek B, bez ponownego audytu backendu A i bez uruchamiania testów przez audytora. Wyniki testów w Verification results pochodzą od wykonawcy. W tej turze nie zmieniano kodu po PASS i nie powtarzano zaliczonych testów bez potrzeby; ponowiono kontrole dokumentacji, mapy i diffu.

### Porównanie z Definition of Done i planem

| Obszar | Rozliczenie |
|---|---|
| Funkcjonalność i kryteria taska | Wszystkie sześć kryteriów odhaczone; mapa wymagań A/B i dowody w raporcie odbioru, brak otwartych P0/P1 po R2. |
| Kod i trwałość | Oddzielne czyste funkcje stanu i hook, opcjonalne porty, lint/format/typecheck PASS; localStorage odczytany po nowym procesie Edge. |
| Dane | Migracja 0169 i chroniony downgrade sprawdzone w A na *_test; baza operatora niezmieniona. |
| Kontrakt | OpenAPI, wygenerowany klient i wrapper pochodzą z pionu A; B nie zmienia API. Build klienta PASS. |
| Testy i narzędzia | Jednostkowe/interakcje/hosty, lint/typy/build, docs/mapa i niezależny audyt rozliczone powyżej. |
| UX | Loading/empty/error, mobile viewport, klawiatura, brak duplikacji submitu i jawne komunikaty sprawdzone; fizyczny Android nieodebrany zgodnie z dopuszczonym ograniczeniem planu. P2-3/P2-4 pozostają jawne. |
| Dokumentacja | Wymagania, kontrakt, D-573, mapa, Outcome i raporty; zamknięcie oraz hash według task-close. |
| Zakres wyłączony | Nie wykonywano migracji operatora, restartów, merge, push ani benchmarku na jego danych. |

### Not completed

- P2-3: możliwe dodatkowe odczyty otwartego modalu przy zmianie stanu wyszukiwania; publiczny detailCache je ogranicza. Audytor uznał pozostawienie jako uzasadnione P2; bez zmiany poprawnego context korekty.
- P2-4: według statycznej analizy audytora blur pola nowego limitu i natychmiastowe kliknięcie Szukaj przy brudnym wzorze mogą najpierw odświeżyć poprzedni snapshot; wtedy potrzebne jest drugie kliknięcie. Nie odtworzono tego testem. Pozostawiono jako znane P2, bez utraty draftu lub błędnego kontekstu; nie rozszerzano zakresu po PASS.
- Fizyczny Android i odbiór na usługach operatora: nie wykonano. Przeglądarka używa fixture i mobilnego viewportu, nie urządzenia.
- Nie wykonano migracji bazy operatora, restartów, merge ani push. Do uruchomienia funkcji na danych operatora konieczna jest migracja 0169 w osobnym uzgodnionym wdrożeniu.
- Benchmark na danych operatora poza zakresem. localStorage działa wyłącznie w tym samym origin i profilu przeglądarki.

### Documentation updates

Mapa kodu, raport odbioru i zadania; wymagania, kontrakt i D-573 zostały zapisane w A. Hash TASK-1091 uzupełniono skryptem record-hash do commita B.

### Recommended next task

Odbiór operatora oraz osobno uzgodniona migracja/wdrożenie. P2-3/P2-4 można rozważyć w odrębnym małym usprawnieniu UX. Brak zgody na merge i restart.
