---
title: Mumie — baza 10 kredytów i tymczasowe stawki wyszukiwarki
status: done
last_updated: 2026-10-19
---

# TASK-1063 — Mumie: baza 10 kredytów i stawki wyszukiwarki

## Status

`done`

## Goal

Kalkulator Mumii traktuje istniejące wypłaty jako kwoty dla 10 kredytów (1 zł),
a wyszukiwarka oferuje wyłącznie stawki 1, 2, 5, 10 i 20 zł.

## Context

Operator potwierdził 2026-10-19, że tabela wypłat dotyczy 10, nie 100 kredytów.
Polecił tymczasową konfigurację w kodzie; edycja dostępnych stawek w regułach
zostaje na później. Gra to `fea55cc1-ebf4-4cee-b3ab-a520017ed1be` (Mumie a1).

## Recommended execution

Rekomendacja: `gpt-6.1-sol`, reasoning `medium`; niewielka poprawka istniejących
przeliczeń i listy wyboru. Wykonuje bieżąca sesja bez delegowania. Audyt krzyżowy
nie jest wymagany przez żaden plan tego zadania. Eskalacja zakresu przy potrzebie
zmiany schematu lub kontraktu API.

## Relevant docs

- `AGENTS.md`
- `ai_docs/process/CURRENT_STATE.md`
- `ai_docs/process/PLAN_STANDARD.md`
- `ai_docs/process/TASK_TEMPLATE.md`
- `ai_docs/process/DEFINITION_OF_DONE.md`
- `ai_docs/requirements/ADMIN_APP.md`, sekcja „Stawka i jednostka”.
- `ai_docs/requirements/ALGORITHMS.md`, sekcja B i wypłaty serii supergry.
- `ai_docs/architecture/API_CONTRACT.md`, kalkulator zakresu i koszt pozycji.
- `ai_docs/process/decisions/DECISION_LOG_2026.md#d-565--tymczasowa-baza-wypłat-i-stawki-mumii`

## Scope

- Efektywna baza kalkulatora i szczegółów planszy Mumii: 10 kredytów.
- Stawki 1/2/5/10/20 zł w Adminie i udostępnionej wyszukiwarce.
- Zgodne formatowanie sum, wykresu, pinów, modala i dziennika wyszukiwania.
- Nowe migawki panelu mają spójną bazę z kalkulatorem; istniejące migawki bez zmian.
- Regresja pozostałych gier i dokumentacja tymczasowej decyzji.

## Out of scope

- Edytor stawek w regułach, zmiana schematu, migracje, publikacja reguł i zapis danych operatora.
- Zmiana stałych slotów panelu zarządzania (osobny interfejs stawek), aplikacja mobilna,
  prekomputacja wydań, scalenie, push i restart usług.

## Acceptance criteria

- [x] API kalkulatora i szczegółów Mumii raportuje `rules.spinCost = 10`;
      zwykły spin kosztuje 10 kredytów, spin serii 0; wypłaty z tabeli bez zmian.
- [x] Stawki wyszukiwarki Mumii to dokładnie 1, 2, 5, 10, 20 zł.
- [x] Wypłata 10 kredytów to 1 zł przy stawce 1 zł i 5 zł przy stawce 5 zł.
- [x] Wynik zakresu przykładu: 18 980 kredytów wypłat − 23 000 kosztów = −4 020 kredytów.
- [x] Gry 777 zachowują dotychczasowe przeliczenia, listę i walidację stawek.
- [x] Istniejące zapisane wyniki są odczytywane bez przeliczania.
- [x] Testy zmienionego pionu, lint, typy, mapa kodu i docs:check przechodzą.

## Technical notes

Źródłem jest jawna decyzja operatora D-565. Tymczasowy wyjątek identyfikowany
wyłącznie UUID Mumii normalizuje odczytaną konfigurację w
`resolve_rules_configuration`; wspólny kalkulator i szczegóły planszy już używają
tej funkcji. Adapter tworzący nowe migawki korzysta z tej samej funkcji.
Nie zmieniamy kwot wypłat ani mechaniki kolumn, sztuk, retriggerów i świeżości.
Pomocniki stawek dostają opcjonalne `gameId`; bez niego zachowują dotychczasowe
zachowanie. Widoki podają UUID odpowiedzi, w tym dla historycznych wykresów.
Historyczne wyniki zachowują swoją zapisaną bazę; lista stawek Mumii jest niezależna.

## Expected files

- `services/api/src/game_predictor_api/application/board_search_approximate_win.py`: resolve_rules_configuration.
- `services/api/src/game_predictor_api/storage/management_game_adapter.py`: _snapshot.
- `packages/board-search-ui/src/board-search-stake.ts`: opcje, walidacja, skalowanie.
- `packages/board-search-ui/src/board-search-approximate-win.tsx`: przekazanie gameId.
- Testy kalkulatora API, serii i pomocników oraz interakcji wyboru stawki.
- Dokumenty wymagań, decyzji, okno stanu i wygenerowana mapa kodu.

## Verification

Z katalogu repozytorium; każda komenda przez `subprocess.run(..., timeout=120)`:

```powershell
.venv\Scripts\python.exe -m pytest services/api/tests/test_board_search_approximate_win_api.py services/api/tests/test_super_game_payout_api.py services/api/tests/test_board_search_board_detail_api.py -q
npm run test --workspace @game-predictor/board-search-ui
npm run typecheck --workspace @game-predictor/board-search-ui
npm run lint --workspace @game-predictor/board-search-ui
npm run docs:check
npm run code-map:check
```

## Risks / open questions

Nie ma pytań blokujących. Wyjątek w kodzie należy zastąpić konfiguracją reguł
w odrębnym zadaniu. Nie uruchamiamy ani nie restartujemy usług.

## Outcome

Commit: v1.7.435 / `1121be3b9a52b52afd9f2bac8b1501966e344683`.

### Changed

- Wspólny resolver konfiguracji kalkulatora normalizuje bazę jedynie wskazanej
  gry Mumie do 10 kredytów. Obejmuje kalkulator, szczegóły planszy, linki
  udostępniania i konfigurację nowych migawek panelu. Nie zapisuje zmian w bazie.
- Wyszukiwarka Mumii oferuje 1/2/5/10/20 zł. Opcjonalny identyfikator gry trafia
  do przeliczeń sum, wykresu, pinów, modala i dziennika. Inni konsumenci zachowują
  domyślne zachowanie. Historyczne stawki oraz stałe sloty panelu są poprawnie
  renderowane także wtedy, gdy ich kwota nie występuje na nowej liście wyboru.
- Kwoty tabeli wypłat, rozwinięcia, sztuki, darmowe spiny i świeżość bez zmian.
- Kryteria akceptacji porównano punkt po punkcie: wszystkie spełnione.

### Verification results

- Python: przypadki z trzech plików API kalkulatora, supergry i szczegółów
  planszy przeszły w dwóch przebiegach. Pierwszy przekroczył 120 s po zaliczonych
  przypadkach; pozostałe 10 przypadków (w tym nowy test modala Mumii) wykonano
  osobno: `10 passed, 15 deselected`. Testy nie były osłabiane ani usuwane.
- Pierwszą próbę bez postępu przerwano; sprawdzono brak osieroconych procesów.
- `npm run test --workspace @game-predictor/board-search-ui`: 104 passed.
  Po korekcie zachowania zapisanych stawek powtórzono tylko zmieniony plik:
  `board-search-stake.test.mjs`: 14 passed.
- Interakcje `board-search-approximate-win.test.mjs` przez `tsx` z jawnym
  `packages/board-search-ui/tsconfig.json`: 24 passed, w tym wybór 5 zł dla Mumii.
  Początkowe uruchomienie bez tego tsconfig zakończyło się błędem konfiguracji JSX;
  poprawiono komendę uruchomienia, bez zmiany testowanych kontraktów.
- Typecheck i lint board-search-ui, Prettier zmienionych czterech plików: PASS.
- Ruff check/format zmienionych plików Python: PASS. Mypy dwóch plików źródłowych
  z `--follow-imports=skip`: PASS. Próbę z analizą całego grafu importów przerwano
  po braku postępu; nie stanowi wyniku pełnego typechecku repozytorium.
- Nowy proces, lokalne dane operatora, transakcja `READ ONLY`: #3488 + 2500 spinów,
  baza 10, wypłaty 18 980, koszt 23 000, bilans −4 020 kredytów (−402 zł).
  Odczyt zapisanej konfiguracji nadal zwraca 100: brak modyfikacji danych reguł.
- Regeneracja mapy kodu: treść bez zmian; `npm run code-map:check`: PASS.
- `npm run docs:check`: PASS; wykonywane ponownie po zamknięciu zadania.

### Not completed

- Bez migracji, publikacji reguł, zapisów do danych operatora, scalenia, pushu
  i restartu usług. Nie uruchamiano pełnego builda ani całego zestawu quality.
- Brak ręcznego odbioru na urządzeniu Android; wybór stawki sprawdzony testem
  interakcji istniejącego natywnego selecta, bez zmian układu lub stylów.
- Audyt krzyżowy nie był wymagany przez plan; nie uruchamiano audytora.

### Documentation updates

- D-565, reguły stawek w ADMIN_APP, baza w ALGORITHMS i opis efektywnego
  `rules.spinCost` w API_CONTRACT. Brak zmian schematu OpenAPI lub klienta:
  zmieniają się wartości istniejących pól, nie ich struktura.
- CURRENT_STATE i archiwum zamykane skillem task-close.

### Recommended next task

Przenieść bazę wypłat oraz listę dozwolonych stawek do wersjonowanych reguł gry,
usunąć tymczasowe profile UUID i uzgodnić stawki stałych slotów panelu zarządzania.
