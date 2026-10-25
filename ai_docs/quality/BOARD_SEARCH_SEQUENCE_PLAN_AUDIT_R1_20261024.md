# Próba audytu planu — runda 1

Status: PRZERWANY PO 480 S. Raport częściowy, bez zakończonego werdyktu. Wliczony do limitu 3 prób. Poniższy tekst jest niezmienionym, niedokończonym wyjściem Claude Code.

# Audyt planu — Wyszukiwanie po maksymalnie czterech kolejnych układach

Werdykt: REVISE
Audytor: claude-opus-5-5, reasoning high
Wykonawca planu: autor planu (Codex), rewizja 1
Zakres: `ai_docs/delivery/BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` (plik nieśledzony), gałąź `codex/selector-games-updates` @ `91c253bb`, data 2026-10-24
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików. Nie uruchamiał testów ani innych agentów. Oceniana jest gotowość planu do implementacji, a nie działanie funkcji.

## Streszczenie

Plan porównałem z ustaleniami użytkownika, z wymaganiami (ADMIN_APP, API_CONTRACT, model zagrożeń), z decyzjami D-548 i D-570 oraz z kodem: ranking SQL, API Admina i linku, dziennik zapytań, korekty, proxy Reviewera i `BoardSearchWorkspace`.

Zachowanie z perspektywy użytkownika jest opisane zgodnie z jego ustaleniami. Kierunek techniczny jest wykonalny: pełny skan fast documents bez top-N, a jeden dokument na `(game_id, sequence_number)` upraszcza złączenie.

Plan zostawia jednak wykonawcy kluczowe decyzje:
- algorytm rankingu, zakres i cykl,
- kształt kontraktu,
- nowy format dziennika i fingerprint korekt,
- kontekst korekt plansz wcześniejszych niż ostatnia,
- limit body w proxy,
- migrację i kolejność wdrożenia,
- pierwszeństwo między odtworzeniem z dziennika a odtworzeniem z pamięci przeglądarki.

Brakuje też konkretnych plików i komend testów. Opis budżetu audytów jest sprzeczny z ustaleniem użytkownika.

Największe ryzyko: dziennik i korekty identyfikują wzór przez `request.cells`. Po dodaniu nowego formatu wszystkie wpisy wielowzorowe dostaną ten sam fingerprint, `sorted([])`, i zmieszają się w grupowaniu, filtrze poprawek oraz w usuwaniu „całego wzoru”.

## Znaleziska

### P0

Brak.

### P1

- **[P1-1]** `BOARD_SEARCH_SEQUENCE_PLAN_20261024.md:30-34` — **algorytm rankingu ciągu nie jest opisany.**
  - Brakuje pseudokodu lub kształtu SQL i skali. Gra 7 ma ok. 88 260 plansz (CURRENT_STATE:26), a filtr `_positive_evidence_expression` (`board_search_projection_repository.py:1502-1536`) nie zawęża kandydatów, gdy dowód może pochodzić z dowolnej pozycji ciągu, więc każde zapytanie przelicza 4×15 wyrażeń CASE dla wszystkich dokumentów.
  - Brakuje czystej funkcji domenowej obok `rank_board_search_candidates` (`domain/board_search.py:356-389`), czego wymaga AGENTS.md:142-144.
  - Plan nie mówi, że łączny procent liczy się z niezaokrąglonych punktów, a nie ze średniej z `score`. Dziś `score` jest zaokrąglany do 0,1 w `_search_score_expressions` (`:1488-1491`).
  - Brakuje testu zgodności SQL z domeną na PostgreSQL. Dzisiejsze testy repozytorium tylko kompilują SQL na mockach (`test_board_search_projection_repository.py:385,431,447`).
  - **Skutek:** wykonawca projektuje rdzeń sam; grozi rozjazd SQL z domeną i nieprzewidywalny czas odpowiedzi publicznego endpointu.
  - **Korekta:**
    - Opisać jedno rozwiązanie: jeden skan, który liczy surowe punkty każdego wzoru na dokument, potem `LEAD`/złączenie po PK z warunkiem kolejnych numerów i doklejonymi pierwszymi `k-1` pozycjami dla zawinięcia, potem `ORDER BY … LIMIT`.
    - Podać wzór: `round(Σ punktów / Σ znanych pól × 100, 1)`.
    - Dodać czystą funkcję referencyjną i test parytetu na PostgreSQL.
    - Dodać kryterium „1 wzór przez POST = identyczna lista i kolejność jak GET”.
    - Podać ograniczony pomiar na istniejących danych; jego uruchomienie wymaga zgody, bez benchmarku.

- **[P1-2]** `BOARD_SEARCH_SEQUENCE_PLAN_20261024.md:31,38` — **cykl i zakres ciągu nie są rozstrzygnięte.**
  - Źródłem długości `L` w kalkulatorze jest `games.expected_layout_count` (`board_search_approximate_win_repository.py:81-89`), a start musi mieścić się w `1..L` (`domain/board_search_approximate_win.py:178-189`). Plan nie wskazuje tego źródła.
  - Nie mówi, co z dokumentami o `sequence_number > L`. Dopasowanie kończące się poza `L` da `APPROXIMATE_WIN_START_OUT_OF_RANGE` dla „wygranej od ostatniego układu”.
  - Nie mówi, co gdy `L < liczba wzorów`: poz