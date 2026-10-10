# Audyt TASK-0934 - Sekcja „Supergry” w Adminie

Werdykt: REVISE
Audytor: gpt-6.1-sol / high
Wykonawca: claude-sonnet-5-5 / high
Zakres: HEAD...221e43ed0c645c218e84b2bee34785608ef04f1d oraz zmiany niezacommitowane wskazane w briefie, data 2026-10-09
Runda: 2

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Poprawki rozwiązują filtrowanie listy po zapisie, odrzucanie starych stron, obsługę błędu katalogu oraz powiązanie obrazu z rewizją. Dokumentacja i testy skrótów są zgodne. Zabezpieczenie odpowiedzi zapisu nadal pomija zmianę otwartej serii przez historię przeglądarki.

## Znaleziska

### P0

- [P0-1] `apps/admin/src/features/super-games/super-game-series-workspace.tsx:638` — Unieważnienie operacji następuje tylko w `openSeries` i `closeSeries`. Nawigacja Wstecz/Dalej zmienia `seriesId` przez `popstate` w `apps/admin/src/features/catalog/catalog-workspace.tsx:204`, bez wywołania tych funkcji. Po rozpoczęciu zapisu A operator może przez historię wrócić do B i wybrać tam kandydata. Spóźniony konflikt zapisu A nadal przejdzie `isCurrent()`: aktualizacja widoku zostanie pominięta, lecz linie 656–657 uruchomią odświeżenie B, które porzuci jej niezapisany wybór. Powiązać ważność operacji z cyklem otwarcia serii, także przy zmianie propsów przez historię, oraz sprawdzać tę ważność przed wszystkimi skutkami odpowiedzi. Rozszerzyć test regresyjny o nawigację poza `openSeries`/`closeSeries`.

### P1

Brak.

### P2

- [P2-3] `apps/admin/src/features/super-games/super-game-series-workspace.tsx:538` — Po błędzie pobrania kolejnej strony lista ma status `error`, lecz przycisk „Wczytaj kolejne” pozostaje aktywny (`:1033`). Kliknięcie niczego nie robi, ponieważ `loadMore` wymaga statusu `ready`. Dopuścić ponowienie tej strony po błędzie albo wskazać konieczność odświeżenia listy.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Lista stronicowana kursorem, działające filtry | spełnione | `apps/admin/src/features/super-games/super-game-series-state.ts:200`, `:286`; testy odrzucania starych odpowiedzi i listy po zapisie |
| Karuzela pokazuje wszystkie pozycje, w tym brakujące | spełnione | `apps/admin/src/features/super-games/super-game-series-state.ts:355`; karta wyzwalacza i wszystkie pozycje serii |
| Sukces zapisu ustawia symbol, zachowuje oznaczenia; konflikt pokazuje aktualny stan | niespełnione | Podstawowa ścieżka CAS działa statycznie, ale konflikt opuszczonej serii może odświeżyć inną serię; P0-1 |
| Skróty nie działają w polach tekstowych i z modyfikatorami | spełnione | `apps/admin/src/features/super-games/super-game-series-keyboard.ts:40`, `:59` |
| Gra `none` nie pokazuje zakładki | spełnione | `apps/admin/src/features/catalog/admin-navigation-state.ts:57`, `apps/admin/src/features/catalog/catalog-workspace.tsx:457` |

## Listy zamknięte i otwarte

Zamknięte:

- P0-2 — Wiersze są sprawdzane względem filtrów, a sukces zapisu ponownie pobiera listę: `super-game-series-state.ts:286`, `super-game-series-workspace.tsx:670`.
- P0-3 — Strony i błędy są odrzucane według generacji ładowania: `super-game-series-state.ts:204`, `:237`, `super-game-series-workspace.tsx:546`.
- P1-1 — Rozstrzygnięcie mapowania `0` zapisano w tasku i uzgodniono z wymaganiami: `ai_docs/tasks/0934-super-game-admin-section.md:91`, `ai_docs/requirements/ADMIN_APP.md:1684`.
- P2-1 — Błąd katalogu jest widoczny i można ponowić pobranie: `super-game-series-workspace.tsx:265`, `:789`.
- P2-2 — URL obrazu używa sumy kontrolnej i rewizji odczytu: `super-game-series-workspace.tsx:145`.

Otwarte: P0-1, P2-3.

## Proponowane testy

- W `apps/admin/test-interactions/super-game-series-workspace.test.mjs` rozpocząć opóźniony zapis A, zmienić `seriesId` przez nawigację historii na B, wybrać symbol B i dostarczyć konflikt A. Sprawdzić brak dodatkowego odczytu B oraz zachowanie jej kandydata.
- W tym samym pliku sprawdzić ponowienie „Wczytaj kolejne” po błędzie bieżącej strony.

Komenda z `apps/admin`: `npx tsx --tsconfig tsconfig.json --test test-interactions/super-game-series-workspace.test.mjs`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, poprzedni raport, task, właściwe fragmenty wymagań, kontraktu API, planu, decyzji i bieżącego stanu. Zbadano stan, widok, skróty, CSS, testy oraz nawigację jako kontekst obsługi otwartej serii. Brief nie zawierał fragmentu planu; odczytano dokument wskazany przez task.

Nie uruchamiano testów, serwerów ani poleceń zmieniających stan. Wyniki w `Outcome` są deklaracjami wykonawcy. Nie zweryfikowano wyglądu ani działania na rzeczywistym API. Zmiany innych tasków pozostają poza zakresem audytu.

## Nota leada po rundzie 2 (2026-10-09)

Pozostały P0-1 (unieważnianie zapisu przy zmianie serii przez historię przeglądarki) i P2-3 (ponowienie „Wczytaj kolejne” po błędzie) naprawione przez wykonawcę: ważność operacji zapisu związana z cyklem otwarcia serii (efekt na `seriesId`), wszystkie skutki odpowiedzi za tą samą bramką, test interakcji z trzema wariantami (konflikt, odmowa, sukces) potwierdzony przez tymczasowe cofnięcie poprawki; przycisk „Ponów wczytanie” dla tej samej strony. Admin 733/733, interakcje 19/19, typecheck/lint/prettier czyste. Pierwsza runda audytu w `TASK-0934_AUDIT_gpt-6.1-sol_round1.md`. Audyt pierwotnie zlecony `gpt-6-astra` (medium) nie wykonał się z powodu braku mocy modelu („at capacity”), zastąpiony `gpt-6.1-sol`. Commit bez trzeciej rundy zgodnie z regułą szybkiego audytu.
