---
title: Mumie A2 — zgodność konfiguracji kalkulacji z A1
status: done
last_updated: 2026-11-17
---

# TASK-1244 — Zgodność kalkulacji Mumie A2 z A1

## Status

`done`

## Goal

Mumie A2 oferują te same stawki i stosują te same reguły kalkulacji co Mumie A1.

## Context

Operator polecił wyrównać wszystkie ustawienia potrzebne do kalkulacji.
Odczyt API wykazał zgodność najnowszych opublikowanych reguł: A1 v3 i A2 v1
mają planszę 3 × 5, koszt 10 kredytów, te same linie, progi, wypłaty i role
symboli oraz `wild_super_spins`. Tymczasowy profil D-565 obejmuje tylko A1.

## Dependencies / entry conditions

- Źródło: A1 `fea55cc1-ebf4-4cee-b3ab-a520017ed1be`.
- Cel: używana A2 `246a1f54-eee8-49d5-b11a-0fde70e5eecd` (`mumie-aktu2`).
- Archiwalna, pusta A2 `8563b353-9c5c-4282-bed5-825412d8bdd1` poza zakresem.
- Odrębne worktree od `main`; zastane zmiany operatora pozostają poza commitem.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/requirements/ADMIN_APP.md` — profil stawek D-565.
- `ai_docs/architecture/API_CONTRACT.md` — efektywna baza kalkulatora.
- `ai_docs/architecture/DATA_MODEL.md` — games i rules_versions.
- `ai_docs/architecture/CODE_MAP.md`
- `ai_docs/architecture/CODE_MAP_SYMBOLS.md`
- [D-565](../../process/decisions/DECISION_LOG_2026.md#d-565--tymczasowa-baza-wypłat-i-stawki-mumii)

## Scope

- Rozszerzyć istniejący profil stawek i efektywnej bazy na wskazaną A2.
- Zweryfikować bieżące zapisane konfiguracje obu gier, porównując symbole po
  kodzie domenowym i reguły po znaczeniu, niezależnie od technicznych ID.
- Testować listę 1/2/5/10/20 zł, skalowanie, bilans, modal planszy i supergrę.
- Zachować zapisane wyniki i stałe stawki panelu zarządzania obu gier.

## Out of scope

Grafiki referencyjne, zmiany kodów mobilnych w istniejących danych, geometria,
modele rozpoznawania, historyczne wyniki, aktywacja gier, migracje, restart
usług, merge i push. Grafiki oraz zgodne wewnątrz gry identyfikatory mobilne
nie są różnicą reguł kalkulacji; ich nadpisanie nie jest potrzebne.

## Acceptance criteria

- [x] A1 i A2 mają dokładnie stawki 1/2/5/10/20 zł przy bazie 1 zł.
- [x] Koszt spinu, linie, progi, wypłaty, Wild i supergra są zgodne semantycznie
  w świeżym odczycie bazy przez API; wynik porównania utrwalony w raporcie.
- [x] Regresje pokrywają oba ID w kalkulatorze, szczegółach i darmowych spinach.
- [x] Skalowanie, wcześniejsze zapisane stawki i pozostałe gry zachowują działanie.
- [x] Testy, lint, formatowanie, typy i dokumentacja zmienionych części sprawdzone.

## Technical notes

Zachować tymczasowy mechanizm D-565 i jawnie dopisać używaną A2 do obu list ID:
`resolve_rules_configuration` po stronie API oraz `gameStakesGrosze` i obsługa
zapisanej stawki w `effectiveApproximateWinStakeGrosze` we wspólnym UI Admina
i Reviewera. Nie rozpoznawać profilu po nazwie, koszcie ani podobieństwie gry.
Nie zmieniać formatu API ani przeliczać niezmiennych opublikowanych reguł.
Reguły są już zgodne; odczyt kontrolny musi to potwierdzić przed zamknięciem.
Nie ma blokujących pytań produktowych; rozszerzenie D-565 zlecił operator.

## Expected files

- `packages/board-search-ui/src/board-search-stake.ts` — prywatna lista ID profilu.
- `packages/board-search-ui/test/board-search-stake.test.mjs` — lista i przeliczenia.
- `services/api/src/game_predictor_api/application/board_search_approximate_win.py`
  — `resolve_rules_configuration`.
- `services/api/tests/test_board_search_approximate_win_api.py`
- `services/api/tests/test_board_search_board_detail_api.py`
- `services/api/tests/test_super_game_payout_api.py`
- Wymagania i kontrakt wskazane w Relevant docs, rozszerzenie wpisu D-565,
  okno stanu i generowana mapa kodu, jeżeli zmieni się jej wynik.
- Nowy raport: `ai_docs/quality/MUMIE_A2_CALCULATION_PARITY_20261117.json`.

## Verification

Z katalogu worktree; polecenia skończone z timeoutem do 120 s:

```powershell
node --experimental-strip-types --test packages/board-search-ui/test/board-search-stake.test.mjs
D:\game_predicotr\.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_approximate_win_api.py services/api/tests/test_board_search_board_detail_api.py services/api/tests/test_super_game_payout_api.py -q
npm run test --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/board-search-ui
npm run docs:check
```

Scoped Ruff, formatowanie i mypy zmienionego modułu API, odczyt porównawczy
z limitami żądań i nowy proces Node dla trwałości. Build Admina i Reviewera
po weryfikacji pionu, z uprzedzeniem, jeżeli wymaga dłuższego limitu.

## Risks / open questions

- Reviewer produkcyjny wymaga przebudowy i restartu operatora po integracji.
- Zgodność konfiguracji nie oznacza zgodności wyników różnych sekwencji plansz.
- Dodatkowy audyt niewymagany: zakres to rozszerzenie istniejącego profilu na
  jedno jawne ID, bez nowego kontraktu, schematu ani zmiany zapisanych reguł.

## Outcome

Commit: v1.7.667 (hash dopisuje kolejny commit).

### Changed

- Profil D-565 obejmuje A1 i używaną A2 w API oraz we wspólnym UI Admina
  i Reviewera. Dokładne stawki 1/2/5/10/20 zł i baza 10 kredytów są zgodne.
- Dotychczasowe zapisane stawki 1,20/4/6 zł pozostają odtwarzalne również
  dla A2. Historia zachowuje zapisaną bazę, a nieznana stawka wraca do bazowej.
- Świeży odczyt API potwierdził równoważność 10 symboli, 5 linii, wszystkich
  34 wypłat, progów, Wild i rodzaju supergry; oba skróty konfiguracji:
  `8f7df37a1ad146703a3481690ab3ae1724c1b863d44c168b5078bd200b774716`.
- Reguły A1 v3 i A2 v1 nie wymagały zapisu ani nowej publikacji.

### Verification results

- Nowa regresja stawek przed poprawką: FAIL A2, pozostałe 14 PASS; po poprawce
  15/15 PASS. Pełny pakiet board-search-ui: **116/116 PASS**, nowy proces Node.
- API, osobne komendy z timeoutem 120 s na plik: kalkulator **15 PASS**,
  szczegóły planszy **26 PASS**, supergra **25 PASS**. Razem **66 PASS**.
  Parametry A1 i A2 pokrywają bazę, bilans, zachowanie wypłat, rozwinięcia
  oraz koszt 0 w serii i 10 na planszy wyzwalającej; stare reguły bez mutacji.
- ESLint całego board-search-ui i `tsc --noEmit`: PASS. Prettier dwóch plików
  UI i raportu JSON: PASS. Ruff check i format czterech zmienionych plików
  Python: PASS; scoped mypy modułu API (`--follow-imports=skip`): PASS.
- Produkcyjne buildy Admina i Reviewera (`next build --webpack`, timeout
  120 s każdy): PASS z TypeScript. Oba wynikowe pakiety zawierają ID A2;
  resolver zależności wskazywał pliki tej gałęzi. Ostrzeżenie o kilku
  lockfile'ach wynika z zagnieżdżonego worktree, bez błędu builda.
- Odczyt porównawczy bazy: PASS wszystkich 8 obszarów; pełny raport
  `ai_docs/quality/MUMIE_A2_CALCULATION_PARITY_20261117.json`.
- Pierwsze testy API zatrzymały się na lokalnym `socketpair` z powodu
  ograniczeń środowiska; przerwane bez uznania za PASS, kontrola procesów bez
  osieroconych testów. Po dopuszczeniu komunikacji testowej wspólna komenda
  przekroczyła 120 s; osobne pliki zakończyły się prawidłowo (55/89/40 s).
- Regeneracja obu map kodu wykonana; brak różnicy treści względem HEAD
  (nie zmieniono publicznych symboli). `npm run docs:check`: PASS.

### Not completed

- Integracja do main, push i wdrożenie czekają na akceptację wyniku i zgodę
  operatora. Działające usługi nie były uruchamiane ani restartowane.
- Nie nadpisywano bazy, grafik, kodów mobilnych, geometrii, modeli ani historii.
  Różne kody Ra/Sarkofagu są poprawnie wiązane z regułami własnej gry.
- Bez pełnego `quality`, pełnego mypy, testu fizycznego Androida ani testu
  przeglądarkowego działającej usługi; zmiana dotyczy istniejących przeliczeń.
- Audyt krzyżowy niewymagany zgodnie z tabelą tego zadania.

### Documentation updates

Wymagania Admina, opis efektywnej bazy API, rozszerzenie D-565 i jego indeks,
katalog dokumentów, raport JSON, task i CURRENT_STATE.

### Definition of Done i zgodność zakresu

- Funkcjonalność: wszystkie 5 kryteriów akceptacji spełnione; bez zmiany
  sekwencji, danych plansz i konfiguracji rozpoznawania.
- Kod i trwałość: zapis w repo, nowe procesy testowe, dwa gotowe buildy.
- Dane i kontrakt: potwierdzona zgodność reguł; brak zmiany schematu lub
  kształtu API, migracja i regeneracja klienta niewymagane.
- Testy, typy i dokumentacja: wyniki powyżej; zmiana nie dodaje nowego flow UI.
- Zakres planu TASK-1244 wykonany; pozostaje odbiór i integracja operatora.

### Recommended next task

Po akceptacji scalić do main, a następnie operator wdraża nowy build Reviewera
i odświeża Admina; restart API/Reviewera wyłącznie na osobne polecenie.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-1244 | gpt-6.1-sol | high | Mała poprawka istniejącego profilu i regresje kalkulacji; bez delegowania. Eskalacja przy różnicy zapisanych reguł. | Niewymagany |
