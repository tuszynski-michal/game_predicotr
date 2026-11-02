---
title: Uproszczenie ekranu wyszukiwania i modal supergry w Adminie
status: done
last_updated: 2026-11-01
---

# TASK-1115 — Uproszczenie ekranu wyszukiwania i modal supergry w Adminie

## Status

`done`

## Goal

Uprościć wspólny ekran wyszukiwania w Adminie i online zgodnie z ośmioma
punktami operatora; Admin ma edytować supergrę w miejscu, bez opuszczania ekranu.

## Dependencies / entry conditions

Operator zaakceptował zakres i koszt 45–90 minut 2026-11-01. Wyszukiwanie
pojedynczej planszy TASK-1114 jest na tej gałęzi. Początkowy worktree czysty.
Scalanie, push i cleanup zostały wstrzymane przez operatora do zakończenia
dodatkowych zmian. Bez uruchamiania i restartowania usług.

## Recommended execution

`gpt-6.1-sol`, reasoning `high`; jedno zadanie UI ze wspólnymi regresjami,
bez delegowania i osobnego audytu. Zmiana kontraktu API albo kosztu poza
zatwierdzonym zakresem wymaga zatrzymania zależnej części pracy.

## Relevant docs

- `AGENTS.md`, `ai_docs/README.md`
- `ai_docs/process/CURRENT_STATE.md`, `ai_docs/process/DECISION_LOG.md`
- [D-576](../../process/decisions/DECISION_LOG_2026.md#d-576--uproszczenie-wyszukiwarki-i-modal-supergry-w-adminie)
- `ai_docs/process/PLAN_STANDARD.md`, `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md` — wyszukiwanie, przybliżona wygrana i supergry
- `ai_docs/architecture/API_CONTRACT.md` — odczyt reguł i supergry
- `ai_docs/architecture/CODE_MAP.md`, `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- `.agents/skills/task-close/SKILL.md`

## Scope / acceptance criteria

- [x] Pod wykresem stoi tabela wygranych z przyciskami „Pokaż planszę”; suwak
  „Pokaż wygrane od” znajduje się pod tabelą i nadal ją filtruje.
- [x] Usunięto opis „Kasa na czysto: rozpoznane wygrane minus koszt…”.
- [x] Wyszukiwarka i jej okna nie mają selectu „Wersja reguł”; obliczenia
  używają najnowszej opublikowanej wersji, jak dotychczasowy domyślny GET.
- [x] Usunięto wskazany opis zakresu spinów i wyboru stawki.
- [x] Usunięto wskazaną sekcję „Wynik opiera się wyłącznie…”. Faktyczne błędy,
  liczniki kompletności, stany prowizoryczne i działanie obliczeń pozostają.
- [x] Jednostka ekranu to zawsze PLN, bez selectu. Dawny zapis „credits”
  nie wpływa na wynik ani po ponownym otwarciu. Stawki nadal działają.
- [x] Znaczniki supergry Admina otwierają wspólny edytowalny modal jak online,
  z istniejącym zapisem CAS. Zapis odświeża wynik. Sekcja „Supergry” pozostaje.
- [x] Przy co najmniej dziesięciu aktywnych symbolach `0` wybiera dziesiąty
  (np. Mumię), a `?` pozostaje nieznanym symbolem; paleta ma zgodne oznaczenia.
  Przy mniej niż dziesięciu symbolach zachowujemy dotychczasowe `0` jako `?`.
- [x] Regresje nawigacji, korekt, kalkulatora, panelu zarządzania i pełnej sekcji
  supergier, lint/typecheck/buildy, dokumentacja i zamknięcie taska.

## Technical notes / expected files

Zmiany w `packages/board-search-ui/src/board-search-approximate-win.tsx`,
`board-search-workspace.tsx`, `board-search-keyboard.ts` i użyciu formatowania
w `board-search-results.tsx`. Komponent wyboru reguł może pozostać dla innych
konsumentów; wyszukiwarka nie pobiera już listy reguł i nie oferuje wyboru.
Odczyt najnowszej wersji i kontrola zgodności okna z wierszem zachowują kontrakt.

Admin wykorzysta `SuperGameSeriesModal` przez adapter istniejącego klienta;
wspólne mapowanie z `features/super-games/super-game-series-workspace.tsx`
wydzielimy do proponowanego `super-game-series-client.ts`. API bez rozszerzeń.
Nie usuwamy funkcji ustawiania super symbolu ani osobnej listy serii.
W `super-game-series-panel.tsx` flaga montowania jest ponownie ustawiana
przy montowaniu efektu — konieczne, aby zapis modalu działał pod StrictMode.

Testy w `packages/board-search-ui/test/`, `test-interactions/` oraz
`apps/admin/test-interactions/`; dokumenty wymagań, decyzja D-576 i mapa kodu.

## Verification

Najpierw testy klawiatury i zmienionych interakcji, potem odpowiednie lint,
TypeScript oraz build Admina i Reviewera. Każda komenda z timeoutem 120 s.
`npm run docs:check`, `npm run code-map:check`, `git diff --check`.
Bez benchmarków, usług, migracji i danych operatora. Testy planowane, nie wyniki.

## Outcome

Commit: v1.7.511 / `3ad50668393c13c9b54d4ecee797b3de47f17b89`.

### Changed

- Wspólny ekran Admina i online: tabela bezpośrednio pod wykresem, suwak
  poniżej tabeli. Pozostało lokalne filtrowanie bez żądania i bez zmiany wykresu.
- Usunięto trzy wskazane opisy, select jednostki i select reguł. Ekran
  używa PLN, także po odtworzeniu starego zapisu `credits`. Wyszukiwarka nie
  pobiera listy reguł i nie wysyła `rulesVersionId`, więc backend rozwiązuje
  najnowszą opublikowaną wersję. Kontrola zgodności detalu z tabelą pozostaje.
- Admin otwiera istniejący edytowalny `SuperGameSeriesModal` bez nawigacji.
  Adapter istniejących tras jest wspólny z pełną sekcją „Supergry”, która
  zachowuje listę, edycję i wybór wersji. Zamknięcie po zapisie odświeża wyniki.
- Przy montowaniu efektu panelu supergry flaga `mounted` wraca do true;
  zapis CAS i zakończenie stanu zapisu działają pod StrictMode. Ten sam
  komponent pozostaje używany online i przez pełną sekcję.
- `0` wybiera dziesiąty aktywny symbol katalogu (Mumia w regresji); `?`
  jest nieznanym symbolem. Krótsze katalogi zachowują dotychczasowy fallback.

### Verification results

- PASS: 107/107 testów interakcji wspólnego UI. Wśród nowych regresji:
  kolejność wykres/tabela/suwak, brak usuniętych tekstów i selectów, filtrowanie,
  stawki w PLN, stary zapis kredytów i ponowne otwarcie, najnowsze reguły dla
  zakresu i detalu, dziesiąty symbol i odrębne `?`.
- PASS: 108/108 testów jednostkowych board-search-ui; osobno 2 testy
  zachowanej nawigacji Admina i braku linku opuszczającego wyszukiwarkę.
- PASS: rzeczywisty wrapper Admina pod StrictMode otwiera modal, zapisuje
  symbol dokładnie raz z `expectedRevision`, przechodzi do następnej serii,
  zwalnia blokadę i odświeża wyniki po zamknięciu, bez zmiany adresu strony.
- Pełna sekcja supergier Admina: 22 PASS / 10 wcześniejszych FAIL. Kontrola
  bazowa ładowała niezmieniony moduł workspace z `1575b335` przez hook tylko
  w teście, bez podmiany plików repo. Potwierdzono identyczny zbiór 10 porażek:
  stare fixture listy nie mają `counts`, odczyt `counts.undefined` rzuca błąd.
  Nie zmieniono testów ani produkcyjnego licznika dla uzyskania zielonego wyniku.
- PASS: ESLint board-search-ui i trzech zmienionych źródeł Admina;
  TypeScript board-search-ui, Admin i Reviewer.
- PASS: produkcyjne buildy Admina i Reviewera z Webpackiem oraz tą samą
  lokalną kopią Next co przy TASK-1114. Każda skończona komenda miała timeout
  120 s; nie uruchamiano usług.
- PASS: mapa kodu zregenerowana i `code-map:check`, cztery kontrole
  `docs:check`, format Prettier i `git diff --check`. Kontrole dokumentacji
  powtórzone po zamknięciu taska.

### Not completed

- Nie naprawiano 10 potwierdzonych wcześniejszych porażek fixture listy
  supergier; są poza tym zakresem. Bez testu na fizycznym Androidzie i na
  działających usługach operatora; regresje UI używają DOM i atrap API.
- Bez nowego API, migracji, operacji danych, benchmarków, audytu i delegacji.
- Zgodnie z najnowszym poleceniem operatora merge, push i cleanup są
  wstrzymane; nie ponowiono wcześniejszej integracji.

### Documentation updates

- D-576, wymagania ekranu, notatka o użyciu istniejącego kontraktu API,
  CURRENT_STATE i mapa kodu. Wymagania kalkulacji i reguły wypłat bez zmian.

### Definition of Done / recommended next task

- Wszystkie osiem punktów pokryte implementacją i regresjami. Wspólny
  komponent zachowuje pozostałe workflowy; ograniczenia pełnej listy i
  urządzenia jawnie opisano. Brak nowych otwartych P0/P1.
- Zamknięcie skillem `task-close`, osobny commit i hash w kolejnym.
- Odbiór ekranu przez operatora; integracja dopiero po nowym poleceniu.
