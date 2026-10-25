# Audyt TASK-1092 — Wyszukiwanie ciągu plansz — badże i trwałość

Werdykt: REVISE
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6.1-sol, high
Zakres: HEAD...9319bde6392c2e913a49cccb08eafa7a3290ebed oraz zmiany niezacommitowane, data 2026-10-24
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem zmiany w kodzie. Zbadałem wspólny workspace i nowy hook `useBoardSearchSequence`, stan i walidację zapisu lokalnego, adapter obu linków Reviewera, kalkulator wygranej, wyniki ciągu oraz historię, replay i korekty Admina. Porównałem je z planem 3.1 (sekcja B) i kryteriami taska. Implementacja jest przemyślana: rozdziela draft, wysłany snapshot i widoczną odpowiedź, chroni przed spóźnionymi odpowiedziami licznikami requestId/epoch i generacją cache. Nie zapisuje contextId ani odpowiedzi, a testy pokrywają większość mapy B. Główne ryzyko: zakres (`scope`) z odtworzonego wpisu historii „przykleja się” do wszystkich kolejnych wyszukiwań. Dotyczy to także wyszukiwań po „Nowe szukanie”, a użytkownik nie widzi tego w interfejsie.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `packages/board-search-ui/src/use-board-search-sequence.ts:404` — Problem: `replaceDraft` ustawia trwały `queryScope` na zakres z odtwarzanego wpisu. Zwykłe wyszukiwanie używa go potem jako domyślnego (`:205`), restore przywraca go z `lastSubmitted.scope` (`:312`), a `clear()` (`:410`) go nie resetuje.
  Skutek: po odtworzeniu starego wpisu z `approved_only` każde kolejne ręczne wyszukiwanie po cichu ogranicza wyniki do zatwierdzonych plansz. Dotyczy to także wyszukiwań po „Nowe szukanie” (aż do przeładowania strony) i po restore z localStorage. Workspace nie ma wyboru zakresu (TASK-0784, komentarz w `board-search-workspace.tsx:570`: „Always every searchable board… the scope choice is gone”). Użytkownik nie ma więc jak zauważyć tego zawężenia ani go cofnąć. Plan wymaga, by „Nowe szukanie” usuwało cały lokalny zestaw.
  Poprawka: zakres replay przekazywać tylko do jednorazowego `search({ scope })`, bez zmiany domyślnego `queryScope`. Ewentualnie `clear()` i każde ręczne `search()` bez `options.scope` mają używać `'all_searchable'`. Do tego test interakcji: replay `approved_only`, a potem „Nowe szukanie” i ręczne wyszukiwanie wysyłają `all_searchable`.

### P2

- [P2-1] `packages/board-search-ui/src/board-search-workspace.tsx:640` — Problem: w trybie sequence zmiana limitu przy widocznych wynikach wywołuje `runSearch({ limit, preserveSelection: true })` na bieżącym drafcie, a nie na ostatnio wysłanym snapshocie.
  Skutek: gdy draft jest zmieniony („Wzór zmieniony — wyszukaj ponownie”), sama zmiana limitu wysyła niezatwierdzony wzór. Do tego `preserveSelection` przenosi wybrany start z innego zapytania. Gdy kalkulator jest zajęty, hook po cichu odrzuca wywołanie.
  Poprawka: przy zmianie limitu ponawiać `visibleSubmitted` z nowym limitem albo przy brudnym drafcie tylko oznaczyć wynik jako nieaktualny. Alternatywa: zaakceptować ryzyko i opisać to w Outcome.
- [P2-2] `packages/board-search-ui/src/use-board-search-sequence.ts:199` — Problem: `setNotice(input.error ?? validation.error)` przy replay (`options.patterns` podane) pokazuje błąd starego draftu z domknięcia, np. „Uzupełnij układ 1.”, zamiast błędu walidacji odtwarzanych wzorów (nieaktywny symbol).
  Skutek: mylący komunikat obok poprawnego `inputError`.
  Poprawka: gdy przekazano `options.patterns`, używać wyłącznie `validation.error`.
- [P2-3] `packages/board-search-ui/src/board-search-workspace.tsx:299` — Problem: `resultClient` z `useMemo` zmienia tożsamość przy każdej zmianie `searchState.kind` i `contextId`. Modal linii (`board-search-board-lines-modal.tsx:231`) i preload sąsiadów (`board-search-results.tsx:106`) mają `api` w zależnościach efektów.
  Skutek: dodatkowe pobrania szczegółów planszy, gdy otwarty modal zbiegnie się ze zmianą stanu wyszukiwania. Na publicznym linku zużywa to limit 429.
  Poprawka: stabilny obiekt klienta z odczytem `contextId` i flagi blokady przez ref. Alternatywa: zaakceptować ryzyko.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Badże przełączają tylko wzór; wspólne wyniki i kotwica wygranej niezależne | spełnione | `packages/board-search-ui/src/use-board-search-sequence.ts:138` (setEditor tylko aktywnego), `board-search-workspace.tsx:1203` (calculationKey bez indeksu badża); test `test-interactions/board-search-sequence.test.mjs:272` („badge sends no calculation”) |
| Następny/Resetuj/Nowe szukanie i limit 4, puste końce i środkowe luki | niespełnione (częściowo) | `board-search-sequence-state.ts:49` (luki, same `?`, pusty koniec), `use-board-search-sequence.ts:449` (canNext); „Nowe szukanie” nie resetuje zakresu — P1-1 |
| Stan po nowym procesie, bez mieszania gier/linków, bez trwałych odpowiedzi/sekretów | spełnione | `board-search-sequence-state.ts:28` (klucze scope), `board-search-workspace.tsx:142` (remount przy zmianie gry/scope), `use-board-search-sequence.ts:356` (zapis bez contextId/wyników); testy `:386`, `test/board-search-sequence-state.test.mjs`; test przeglądarkowy deklarowany przez wykonawcę |
| Replay wygrywa z localStorage; spóźnione odpowiedzi nie wskrzeszają resetu | spełnione | `use-board-search-sequence.ts:290`, `:392`, `:410`; reviewer `board-search-share-data-source.ts:121` (generacja cache); testy `:351`, `:424` |
| Korekty, supergry, wygrane i management mają testy regresyjne; oba rodzaje linku | spełnione (statycznie) | testy `test-interactions/board-search-sequence.test.mjs:532`, `:604`, `:699`, `:736`; `apps/reviewer/test/board-search-sequence-data-source.test.mjs:47`; `apps/admin/test/board-search-sequence-history.test.mjs:24`; `apps/admin/test-interactions/board-search-share-corrections.test.mjs:305` |
| Lint/typy/interakcje/docs/mapa i niezależny audyt rozliczone; ograniczenia jawne | niezweryfikowane | wyniki deklarowane w Outcome; audytor nie uruchamiał poleceń; ograniczenia (Android, migracja 0169, origin) opisane w `ai_docs/tasks/1092-board-search-sequence-ui.md` |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P2-1, P2-2, P2-3.

## Proponowane testy

- `packages/board-search-ui/test-interactions/board-search-sequence.test.mjs`: replay z `scope: 'approved_only'`, następnie „Nowe szukanie”, wpisanie wzoru i „Szukaj plansz”. Ostatnie żądanie ma `scope: 'all_searchable'`. To samo po restore zapisu z `lastSubmitted.scope = 'approved_only'` i ręcznej edycji. Komenda: `npm run test:interactions --workspace @game-predictor/board-search-ui` (lub odpowiednik pakietu).
- Ten sam plik: zmiana limitu przy brudnym drafcie nie wysyła niezatwierdzonego wzoru (albo test dokumentujący zaakceptowane zachowanie).
- Ten sam plik: replay z nieaktywnym symbolem przy pustym poprzednim drafcie pokazuje komunikat „nie jest już aktywny”, a nie „Uzupełnij układ 1.”.

## Zakres przeglądu i ograniczenia

Przeczytałem cały brief z diffem i nowymi plikami: `board-search-sequence-state.ts`, `use-board-search-sequence.ts`, test przeglądarkowy, testy interakcji i stanu. Dodatkowo przeczytałem fragmenty `board-search-workspace.tsx` (wyszukiwanie legacy, limit, klawiatura, wyniki), adaptera Reviewera, `board-search-panel-gate.tsx`, `board-search-panel-proxy.ts`, logu zapytań Admina, sekcję B planu `BOARD_SEARCH_SEQUENCE_PLAN_20261024.md` i sekcję audytu w `AGENTS.md`. Istnienie testów Admina i Reviewera sprawdziłem wyszukiwaniem, bez pełnej lektury. Nie uruchamiałem testów, lintu, typecheck ani buildu. Wyniki weryfikacji z Outcome (108/109 testów, Reviewer 293, test przeglądarkowy) są deklaracją wykonawcy, niepotwierdzoną przez audytora. Nie weryfikowałem zgodności z backendem TASK-1091 (POST `/search`, `searchEventId`, `patternCount`) poza typami i proxy. Odbioru na fizycznym Androidzie i na danych operatora nie było, zgodnie z Outcome.
