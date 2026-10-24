---
title: Audyt krzyżowy TASK-1092, runda 2
status: active
last_updated: 2026-10-24
---

# Audyt TASK-1092 — Wyszukiwanie ciągu plansz — badże i trwałość

Werdykt: PASS
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...9319bde6392c2e913a49cccb08eafa7a3290ebed oraz zmiany niezacommitowane, data 2026-10-24
Runda: 2

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Był to wąski ponowny audyt poprawek po rundzie 1. Zbadałem obecny `use-board-search-sequence.ts`, odpowiednie fragmenty `board-search-workspace.tsx` i `board-search-results.tsx` oraz raport poprawek. Przeczytałem też testy P1-1, P2-1, P2-2 i test ostrzeżenia o wildcardach w `test-interactions/board-search-sequence.test.mjs`.

P1-1 jest usunięte. Ręczne wyszukiwanie bez jawnego zakresu zawsze wysyła `all_searchable`. Zakres z replay i restore jest jednorazowy, a `replaceDraft` i `clear` nie mają już stanu zakresu. Poprawki P2-1 i P2-2 również działają.

Ostrzeżenie o wildcardach w ciągu korzysta ze score całego ciągu, który backend agreguje sumą i `any`, więc obejmuje także wcześniejsze plansze. Pozostawienie P2-3 jest uzasadnione i może zostać jako P2. Nowe ryzyko jest drobne: interakcja blur pola limitu z kliknięciem „Szukaj plansz” przy zmienionym wzorze.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-3] `packages/board-search-ui/src/board-search-workspace.tsx:299` — Problem: `resultClient` zmienia tożsamość przy każdej zmianie `searchState.kind` i `contextId`. Ten problem pozostaje bez zmian z rundy 1.
  Skutek: możliwe dodatkowe odczyty szczegółów planszy w otwartym modalu i dodatkowe zużycie limitu 429 na linku publicznym. Kontekst korekty nie staje się przez to błędny.
  Ocena: uzasadnienie w `TASK-1092_AUDIT_FIXES_20261024.md` jest rzeczowe. Porty korekty muszą zniknąć natychmiast po starcie wyszukiwania, a `detailCache` ogranicza powtórne wywołania. Akceptuję pozostawienie jako ryzyko P2. Jeśli kiedyś warto to poprawić, można zrobić stabilny klient czytający `contextId` i flagę blokady przez ref.

- [P2-4] `packages/board-search-ui/src/board-search-workspace.tsx:854` oraz `packages/board-search-ui/src/use-board-search-sequence.ts:465` — Problem: pole limitu zatwierdza się na `onBlur`. Gdy użytkownik zmieni wzór, wpisze nowy limit i od razu kliknie „Szukaj plansz”, `mousedown` wywołuje blur, a `commitLimit` → `repeatWithLimit` kolejkuje ponowienie widocznego snapshotu. Efekt kolejki uruchamia je w mikrozadaniu, czyli zanim przeglądarka wyśle `click`. `status` przechodzi w `loading`, przycisk staje się nieaktywny i kliknięcie przepada. Jeśli kliknięcie jednak dotrze, `search()` odrzuci je przez `loading.current`.
  Skutek: zamiast nowego wzoru wysyła się stary snapshot z nowym limitem i nadal widać baner „Wzór zmieniony — wyszukaj ponownie”. Użytkownik musi kliknąć drugi raz. Nie ma utraty danych ani złego kontekstu. To wniosek ze statycznej analizy kolejności zdarzeń, nieodtworzony testem.
  Proponowana poprawka: w `commitLimit` przy zmienionym drafcie (`sequence.stale` z różnym `inputKey`) tylko ustawiać limit, bez `repeatWithLimit`. Alternatywnie `search()` z draftu mógłby zastępować oczekujące ponowienie limitu. Można też odnotować to jako znane ograniczenie.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Badże przełączają tylko wzór; wspólne wyniki i kotwica wygranej niezależne | spełnione (bez zmian od R1) | `packages/board-search-ui/src/use-board-search-sequence.ts:137` (`setEditor` tylko aktywnego), `calculationKey` bez indeksu badża w `board-search-workspace.tsx` |
| Następny/Resetuj/Nowe szukanie i limit 4, puste końce i środkowe luki | spełnione | `use-board-search-sequence.ts:208` (domyślnie `all_searchable`), `:396` i `:409` (brak trwałego zakresu w `replaceDraft`/`clear`); test `test-interactions/board-search-sequence.test.mjs:779` (replay `approved_only` → Nowe szukanie → `all_searchable`; restore `approved_only` → edycja → `all_searchable`) |
| Stan po nowym procesie, bez mieszania gier/linków, bez trwałych odpowiedzi/sekretów | spełnione (bez zmian od R1) | zapis w `use-board-search-sequence.ts` bez `contextId` i wyników; test przeglądarkowy deklarowany przez wykonawcę |
| Replay wygrywa z localStorage; spóźnione odpowiedzi nie wskrzeszają resetu | spełnione | `use-board-search-sequence.ts:396` (epoch/requestId w `replaceDraft`), `:409`; testy `:351`, `:424`, `:849` |
| Korekty, supergry, wygrane i management mają testy regresyjne; oba rodzaje linku | spełnione (statycznie) | testy `:532`, `:604`, `:699`, `:736`, `:811`, `:869`; agregacja wildcardów w backendzie `services/api/src/game_predictor_api/domain/board_search_sequence.py:90` |
| Lint/typy/interakcje/docs/mapa i niezależny audyt rozliczone; ograniczenia jawne | niezweryfikowane (audyt: PASS w tej rundzie) | wyniki poleceń są deklaracją wykonawcy z Outcome; audytor ich nie uruchamiał; ograniczenia (Android, migracja 0169, origin) opisane w `ai_docs/tasks/1092-board-search-sequence-ui.md` |

## Listy zamknięte i otwarte

Zamknięte:
- **P1-1:** usunięte. Dowody: `use-board-search-sequence.ts:208` (`scope: options.scope ?? 'all_searchable'`), brak stanu zakresu w `replaceDraft` (`:396`) i `clear` (`:409`), test `board-search-sequence.test.mjs:779`.
- **P2-1:** usunięte. Zmiana limitu ponawia `visibleSubmitted` (`use-board-search-sequence.ts:522`), czeka na kalkulator (`:456`), a pole limitu jest nieaktywne podczas wyszukiwania (`board-search-workspace.tsx:850`). Test `:811` sprawdza komórki snapshotu, limit 7, zachowany draft i oczekiwanie na kalkulator.
- **P2-2:** usunięte. Przy jawnym `options.patterns` komunikat pochodzi tylko z walidacji snapshotu (`use-board-search-sequence.ts:198–202`). Test `:849` to potwierdza.

Otwarte: P2-3 (zaakceptowane ryzyko), P2-4.

## Proponowane testy

- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs`: przy widocznych wynikach zmienić wzór i wpisać nowy limit. Następnie wywołać blur pola, w tym samym kroku kliknąć „Szukaj plansz” i sprawdzić, czy wysłano nowy wzór. Test potwierdzi albo obali P2-4. Komenda: `npm run test:interactions --workspace @game-predictor/board-search-ui` (lub odpowiednik pakietu).
- Ten sam plik: test ostrzeżenia o wildcardach z fixture, w którym tylko plansza wcześniejsza ma `unknownCount > 0`, a łączny score pochodzi z odpowiedzi zgodnej z agregacją backendu. Obecny test ustawia score wyniku bezpośrednio.

## Zakres przeglądu i ograniczenia

Przeczytałem brief z diffem oraz raport R1 i raport poprawek. Przeczytałem w całości `use-board-search-sequence.ts` z briefu i fragmenty `board-search-workspace.tsx`: `commitLimit`, skróty klawiszowe, `applyReplay`, efekt replay i pole limitu. W `board-search-results.tsx` sprawdziłem `evidenceScore`. Przeczytałem też testy `:779–890` w `test-interactions/board-search-sequence.test.mjs`. Agregację `unknown_count`/`unknown_matches_all` w backendzie sprawdziłem wyszukiwaniem.

Nie uruchamiałem testów, lintu, typecheck ani buildu. Wyniki weryfikacji z Outcome są deklaracją wykonawcy. Zgodnie z zakresem rundy 2 nie powtarzałem audytu backendu TASK-1091 ani części B niezmienionych od rundy 1. P2-4 wynika z analizy kolejności zdarzeń przeglądarki i nie zostało odtworzone.
