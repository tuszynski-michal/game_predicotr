# Audyt planu: wyszukiwanie po maksymalnie czterech kolejnych układach

**Werdykt: REVISE**
**Audytor:** claude-opus-5-5, reasoning high
**Runda:** 2 z 3
**Zakres:** `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` (rewizja 2), gałąź `codex/selector-games-updates` @ `91c253bb`, 2026-10-24

Audyt jest statyczny. Nie zmieniałem plików, nie uruchamiałem testów ani innych agentów. Oceniam gotowość planu, a nie działanie funkcji. Korzystałem z materiału `evidence-r1.txt` i 13 celowanych odczytów kodu, czyli o jeden więcej niż limit 12.

## Streszczenie

Rewizja 2 domyka prawie wszystkie luki z rundy 1: algorytm SQL bez top-N, cykl i `L`, wzór oceny, kontrakt, format dziennika v2, fingerprint, limity body, migrację, kolejność replay i restore, testy oraz budżet audytów. Zostaje jeden bloker. Plan każe przy korekcie wcześniejszej planszy wysyłać jako `startSequenceNumber` ostatnią planszę ciągu. Obecna walidacja zakresu na serwerze odrzuci takie żądanie kodem 409.

## Znaleziska

### P0

Brak.

### P1

- **[P1-1]** Plan `:117-120` kontra `board_search_share_correction_repository.py:181-189` — **korekta wcześniejszej planszy ciągu zostanie odrzucona.**
  - Serwer liczy `distance = (sequenceNumber - startSequenceNumber) % L`. Odrzuca korektę, gdy `distance != 0` i (`spinCount` jest pusty albo `distance > spinCount`).
  - Przykład: ciąg s..s+3, start = s+3, edytowana plansza = s. Wtedy `distance = L-3`, co daje 409 „outside the reported range”.
  - Dziś fallback `correctionContext ?? { startSequenceNumber: sequenceNumber }` (`board-search-board-lines-modal.tsx:325`) daje `distance = 0`. Plan ten fallback zakazuje, ale nie zmienia reguły serwera.
  - **Skutek:** wymaganych w planie korekt plansz 1..k-1 nie da się zapisać. Wykonawca sam wymyśli regułę zakresu dla publicznego endpointu.
  - **Korekta planu:**
    - Gdy `searchContextId` wskazuje wpis v2 z `patternCount = k`, serwer akceptuje planszę, jeśli `(start - sequenceNumber) % L <= k-1` albo spełnia dotychczasową regułę naprzód (`spinCount`).
    - Wpis legacy/single zachowuje dokładnie obecną regułę.
    - `startSequenceNumber` musi być końcem ciągu z tego wpisu.
    - Planowane testy: korekta planszy 1 z 4 bez `spinCount` i z nim, plansza spoza ciągu daje 409, ciąg zawinięty L→1, legacy bez zmian.
    - Wskazać, czy ścieżka korekt Admina (bez linku) ma analogiczne sprawdzenie. Nie zweryfikowałem tego.

### P2

- **[P2-1]** Plan `:77-80` — **timeout SQL nie jest wykonalny tak, jak go opisano.**
  - `SET LOCAL`/`statement_timeout` przerywa transakcję. „Przywrócenie przed kolejną operacją” wymaga rollbacku do SAVEPOINT albo osobnej transakcji.
  - Wrapper `logged()` (`board_search_share_public.py:206-221`) zapisuje nieudane zapytanie z `error.code`. Bez atrybutu `code` wpis dostaje `INTERNAL_ERROR`.
  - **Korekta:** określić SAVEPOINT/rollback. Wpis porażki ma kod `BOARD_SEARCH_SEQUENCE_TIMEOUT`, a nie `QUERY_LOG_UNAVAILABLE`. Dodać do tabeli testów test timeoutu (krótki limit w `*_test`) z asercją na wpis dziennika i brak danych.

- **[P2-2]** Plan `:80-81` — **wspólny `calculation_slot` zwraca 429 przy kolizji z kalkulatorem.**
  - Dziś GET wyszukiwania nie używa slotu (`board_search_share_public.py:358-407`), używa go tylko kalkulator wygranej (`:427`). Slot natychmiast odrzuca drugie równoległe obliczenie sesji (`application/board_search_share_queries.py:114-123`).
  - Automatyczne przeliczenie wygranej (D-462) i restore z auto-search mogą więc trafić na 429.
  - **Korekta:** określić, że UI nie wysyła wyszukiwania podczas trwającego obliczenia wygranej (albo je kolejkuje). Podać komunikat dla 429 i koszyk limitu (`JSON` 120/min). Dodać test kolizji.

- **[P2-3]** Plan `:50-51, :66-68` — **niejednoznaczny mianownik oceny i ostatni tie-break.**
  - „Suma znanych pól” można pomylić z `known_evidence_positions` dokumentu.
  - **Korekta:** mianownik = Σ długości zwalidowanych wzorów (pola bez `?`). Przy 777a2 `unknown_count` każdego aliasu doliczany jest do licznika (`board_search_projection_repository.py:1486-1491`). Kolejność: `(Σw * (100.0/Σn)).cast(Numeric(10,6))`, potem `round(…,1)`.
  - Ostatni tie-break to `review_item_id` dokumentu `d0`, jak w `:440-441`, a nie dowolny „UUID d0”. W domenie należy dodać priorytet statusu zatwierdzonego (`domain/board_search.py:384`).

- **[P2-4]** Plan `:103-113` — **tożsamość wzoru i podsumowanie w dzienniku.**
  - Dziś istnieją dwie różne tożsamości legacy:
    - `_pattern_key` = `json.dumps(cells)` (`application/board_search_share_queries.py:238-239`);
    - `pattern_fingerprint` = hash posortowanej listy (`board_search_share_correction_repository.py:64-65`).
  - **Korekta:** jedna normalizacja kanoniczna z dwoma wyjściami legacy, każde bit w bit jak dziś. Plus test: zapisane wcześniej `patternFingerprint` wierszy korekt nadal pasują do filtra `pattern`.
  - Nazwać klucz podsumowania v2 z numerami końcowymi. Nie używać ponownie `firstSequenceNumbers` (`domain/board_search_share_queries.py:65-69`) w innym znaczeniu bez wskazania konsumentów w Adminie.

- **[P2-5]** Plan `:146-152` — **brak ścieżki, gdy po migracji bazy merge się nie odbędzie.**
  - Baza na rewizji spoza `main` blokuje Alembic na `main`.
  - **Korekta:** dopisać decyzję. Albo chroniony downgrade (ze sprawdzeniem >4096), albo merge samej migracji. Bez uruchamiania starego kodu na nowym constraincie bez potwierdzenia, że to bezpieczne. Uwaga: luzowanie limitu jest wstecznie zgodne.

## Pokrycie wymagań

| Wymaganie | Stan |
|---|---|
| 1–4 kolejne spiny, bez top-N, cykl | Spełnione (`:48-49, :62-69`); test „poza top100” jest w planie. |
| Ocena % | Spełnione, z doprecyzowaniem P2-3. |
| Badże przełączają tylko wpisane wzory; wspólna sekcja stale poniżej | Spełnione (`:33-38, :180-184`). |
| Reset aktywnego wzoru / krótkie „Nowe szukanie” | Spełnione (`:36-37, :210`). |
| Pamięć w przeglądarce, osobno gra i link | Spełnione. Klucz panelu zgodny z istniejącym `scopeKey` `panel:${panelId}:${sessionId}` (`board-search-panel-gate.tsx:165`). |
| Wygrane od ostatniego układu | Spełnione; cykl gwarantuje koniec w `1..L`. |
| Oba widoki, istniejące style | Spełnione (`:42, :162`). |
| Proxy i limity body | Spełnione. Panel czyta body z limitem 4096 przed klasyfikacją trasy (`board-search-panel-proxy.ts:81-96`); wymóg planu wymusza zmianę tej kolejności. |
| Historia, replay, korekty | Częściowo: P1-1 i P2-4. |
| Migracja i bramki | Spełnione (`ck_bss_query_request` potwierdzony w `models.py:6969-6970` i `0130_*.py:134-135`), z P2-5. |
| Regresja management | Spełnione (`:162, :242`). |
| Limit 3 audytów planu | Spełnione (`:281-288`). |

## Otwarte i zamknięte

- **Zamknięte z rundy 1:**
  - P1-1 (algorytm, skala, parytet SQL z domeną, POST1 = GET);
  - P1-2 (`L = expected_layout_count`, k ≤ L, dokumenty spoza `1..L`, luki);
  - zakresy rundy 1 bez opisu z powodu przerwania: kontrakt, fingerprint v2 (zakaz fallbacku `cells`), limit 32 KiB w proxy i API, migracja z ochronnym downgrade, replay przed restore, konkretne pliki testów i komendy z timeoutem, budżet audytów.
- **Otwarte:** P1-1 (nowe, kontekst korekty), P2-1 … P2-5.

## Ograniczenia

- Nie sprawdziłem, czy dziennik zapytań używa osobnej sesji SQLAlchemy (wpływa na P2-1) ani czy korekty Admina bez linku mają regułę zakresu (P1-1).
- Nie sprawdziłem konsumentów `firstSequenceNumbers` w Adminie (P2-4).
- Wykonałem 13 celowanych odczytów kodu, czyli o jeden więcej niż limit 12. Nie robiłem szerokiej eksploracji repo.

Po poprawieniu P1-1 plan nie ma znanych blokerów. Runda 3 powinna sprawdzić tylko regułę zakresu korekt v2 i jej testy oraz ewentualne poprawki P2.
