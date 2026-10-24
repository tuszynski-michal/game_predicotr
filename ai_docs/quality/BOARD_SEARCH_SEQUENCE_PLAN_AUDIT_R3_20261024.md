Raport rundy 3 poniżej. Pliki bez zmian.

# Audyt planu: wyszukiwanie po maksymalnie czterech kolejnych układach

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning high
Wykonawca: n/d (audyt planu, rewizja 3)
Zakres: `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` (rewizja 3, niezacommitowana), gałąź `codex/selector-games-updates` @ `91c253bb`, data 2026-10-24
Runda: 3

Przegląd statyczny, bez zmian w plikach. Oceniam gotowość planu do implementacji, a nie działanie funkcji.

## Streszczenie

Sprawdziłem naprawę P1-1 i poprawki P2-1–P2-5 z rundy 2 w kodzie. P1-1 naprawiono inaczej niż sugerowałem w rundzie 2. Alternatywa poprawnie usuwa skutek i jest zgodna z wymaganiem użytkownika: wygrane liczone od ostatniego układu. Wszystkie poprawki P2 są wystarczające. Nie znalazłem nowych blokerów. Zostały dwa drobne ryzyka P2, które można odnotować.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- **[P2-1]** `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md:79-81` — limit czasu zapytania sekwencji jest ustawiony bezwzględnie na lokalne 10 s.
  - **Skutek:** jeżeli sesja albo rola ma już niższy `statement_timeout`, nowy ranking go podniesie. Plan zapamiętuje poprzednią wartość tylko po to, żeby ją przywrócić.
  - **Korekta:** ustawić mniejszą z dwóch wartości: zapamiętanej (gdy nie jest zerem) i 10 s. Można też świadomie zaakceptować ryzyko w `Outcome`.
- **[P2-2]** `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md:138-146` — korekta zapisana z ciągu przechowuje `startSequenceNumber = sequenceNumber`.
  - Widok korekt Admina pokaże ją jak korektę z pojedynczego wyszukiwania (`apps/admin/src/features/board-search/board-search-share-corrections.tsx:295-299`). Przynależność do ciągu wynika tylko z `searchSnapshot` v2.
  - **Skutek:** nie ma regresji, bo obecny fallback już tak działa. Operator może jednak nie zauważyć, że korekta pochodzi z ciągu.
  - **Korekta:** w sekcji Admina (`:163-166`) dopisać, że widok korekt oznacza liczbę układów na podstawie `searchSnapshot.version = 2`, a nie na podstawie `startSequenceNumber`. Dodać przypadek do istniejącego testu widoku korekt.

## Pokrycie kryteriów akceptacji

| Kryterium | Status | Dowód |
|---|---|---|
| 1–4 kolejne spiny, bez top-N, cykl, luki | spełnione | plan `:48-52, :62-71`; test „poza top100”, wrap, luka, k>L (`:287`) |
| Ocena % i tie-break | spełnione | plan `:50-51, :66-70`; test SQL = domena (`:288`) |
| Badże przełączają tylko wpisane wzory; wspólna sekcja stale poniżej | spełnione | plan `:33-38, :221-225` |
| Reset aktywnego wzoru / osobne „Nowe szukanie” | spełnione | plan `:36-37, :261` |
| Pamięć w przeglądarce, osobno gra i link | spełnione | plan `:244-258`; klucz panelu zgodny z `board-search-panel-gate.tsx:165` (R2) |
| Wygrane od ostatniego układu | spełnione | plan `:40, :139-146`; selektor wyniku kalkulatora `board-search-workspace.tsx:998` |
| Oba widoki i istniejące style | spełnione | plan `:42, :203` |
| Proxy, body, autoryzacja | spełnione | plan `:103-104, :289` |
| Historia, replay, korekty | spełnione | plan `:111-168, :290`; z P2-2 |
| Timeout i współbieżność | spełnione | plan `:79-92, :234-242, :294`; z P2-1 |
| Migracja i bramki wdrożenia | spełnione | plan `:172-193, :295`; `models.py:6969-6975` |
| Regresja management | spełnione | plan `:203, :242, :293` |
| Limit trzech audytów planu | spełnione | plan `:334-341` |

## Listy zamknięte i otwarte

**Zamknięte w tej rundzie:**

- **P1-1 (R2), kontekst korekty planszy z ciągu.** Kontekst korekty jest teraz oddzielony od kotwicy wygranych (plan `:138-155`).
  - Workspace spoza management przekazuje dziś `correctionContext = undefined` (`board-search-workspace.tsx:977-985`). Modal stosuje wtedy fallback `{ startSequenceNumber: sequenceNumber }` (`board-search-board-lines-modal.tsx:325`).
  - W tej sytuacji serwer liczy `distance = 0` i przyjmuje korektę (`board_search_share_correction_repository.py:185-189`).
  - `searchContextId` jest sprawdzany tylko pod kątem sesji, gry, `kind=search` i `outcome_code=ok` (`:168-180`). Serwer nie sprawdza, czy plansza należy do top-N, więc pełny kontekst v2 nie powoduje odrzucenia.
  - Korekty z tabeli wygranych zachowują start i `spinCount` (`board-search-approximate-win.tsx:874`). Reguła serwera i ścieżka Admina zostają bez zmian.
  - Planowane testy są konkretne (`:290`): plansza 1 z 4 bez `spinCount`, przypadek wrap, wygrane od ostatniej planszy, błędny zakres nadal 409, legacy i Admin bez zmian, retry receipt.
- **P2-1 (R2), timeout.** Plan opisuje SAVEPOINT, przywrócenie ustawienia, SQLSTATE 57014, kod `BOARD_SEARCH_SEQUENCE_TIMEOUT` → 503 oraz osobną sesję logu (`:79-88`). Test jest w `:294`.
- **P2-2 (R2), wspólny slot obliczeń.** Plan dodaje `onBusyChange`/`suspended`, komunikat dla 429, koszyk 120/min i ręczne ponowienie (`:89-92, :234-242`). Test jest w `:294`.
- **P2-3 (R2), mianownik i tie-break.** Plan określa mianownik jako długość wzorów zapytania, `unknown_count` przy 777a2, dokładną kolejność SQL i tie-break po `review_item_id` dokumentu `d0` z priorytetem zatwierdzenia (`:50, :66-70`).
- **P2-4 (R2), tożsamość wzoru.** Plan opisuje dwa adaptery legacy bit w bit, zgodne z kodem `_pattern_key` (`application/board_search_share_queries.py:238-239`) i `pattern_fingerprint` (`board_search_share_correction_repository.py:64, :281`). Zakazuje fallbacku `cells` dla v2 i wprowadza `firstEndSequenceNumbers`. Podsumowanie mieści się w 2 KiB zgodnie z `ck_bss_query_result_summary` (`models.py:6974-6975`). Konsument `describeBoardSearchQueryEntry` jest wskazany.
- **P2-5 (R2), nieudany merge po migracji.** Plan opisuje chroniony downgrade z checkoutu zawierającego nową migrację, blokadę przy wpisach >4096, zakaz uruchamiania Alembic ze starego `main` i usługi zatrzymane do czasu sprawdzenia rewizji (`:187-193`). Test jest w `:295`.

**Otwarte:** P2-1 i P2-2 z tej rundy. Żadne nie blokuje planu.

## Proponowane testy

- `integration/test_board_search_sequence_postgres.py`: ranking z niższym, wstępnie ustawionym `statement_timeout` nie podnosi limitu (jeśli P2-1 zostanie przyjęte).
- Test widoku korekt Admina: korekta z `searchSnapshot` v2 pokazuje liczbę układów (P2-2).

## Zakres przeglądu i ograniczenia

- **Przeczytane w tej rundzie:** `AGENTS.md`, plan (rewizja 3), raport R2, `PLAN_STANDARD.md`, `AUDIT_REPORT_TEMPLATE.md`.
- **Odczyty kodu:** 6 celowanych, w limicie 8:
  - fragment `board_search_share_correction_repository.py:150-199`,
  - fragment `board-search-workspace.tsx:965-1054`,
  - grep `correctionContext` w `board-search-ui`,
  - grep tożsamości wzoru w API,
  - grep constraintów `ck_bss_query_*`,
  - grep `startSequenceNumber` w Admin board-search.
- **Pominięte w tej rundzie:** `README.md`, `CURRENT_STATE.md`, `DECISION_LOG.md` i `TASK_TEMPLATE.md`. Zostały ocenione w rundach 1–2, a w rewizji 3 nie zmieniły się fragmenty planu, które od nich zależą. Nie czytałem ponownie `evidence-r1.txt`.
- Testów nie uruchamiałem. To audyt planu: PASS nie dowodzi poprawności implementacji i nie jest zgodą na implementację, migrację bazy operatora, restart, merge ani push.
