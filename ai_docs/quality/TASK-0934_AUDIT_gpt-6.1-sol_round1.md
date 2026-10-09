# Audyt TASK-0934 - Sekcja „Supergry” w Adminie

Werdykt: REVISE
Audytor: gpt-6.1-sol / high
Wykonawca: claude-sonnet-5-5 / high
Zakres: HEAD...221e43ed0c645c218e84b2bee34785608ef04f1d oraz zmiany niezacommitowane w ścieżkach briefu, data 2026-10-09
Runda: 1

Przegląd statyczny, bez zmian w plikach. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano nawigację, stan listy i karuzeli, zapis CAS, skróty, testy oraz zgodność z dokumentacją. Podstawowe ścieżki są zaimplementowane, lecz obsługa opóźnionych odpowiedzi może uszkodzić stan otwartej serii lub przywrócić nieaktualne strony listy. Po zapisie lista może również pokazywać serie sprzeczne z aktywnym filtrem.

## Znaleziska

### P0

- [P0-1] `apps/admin/src/features/super-games/super-game-series-workspace.tsx:571` — Odpowiedź zapisu jest stosowana do dowolnego aktualnego `view`, bez sprawdzenia `savedSeriesId`. Operator może rozpocząć zapis serii A, wrócić do listy i otworzyć B przed zakończeniem żądania. Sukces zapisu A zastąpi wtedy `series` widoku B, pozostawiając jego karty; warunek `viewReady` przestanie być spełniony i ekran pokaże bezterminowo „Wczytuję serię”. Obsługa konfliktu i innych błędów również modyfikuje aktualny widok bez powiązania z żądaniem. Powiązać wszystkie odpowiedzi z identyfikatorem serii i operacji; ignorować odpowiedzi dla opuszczonego lub zastąpionego widoku. Dodać test opóźnionego zapisu podczas przejścia A → B.

- [P0-2] `apps/admin/src/features/super-games/super-game-series-state.ts:247` — `replaceSeriesInList` zastępuje wiersz bez ponownego sprawdzenia filtrów. Przy filtrze „Do zdefiniowania” otwarcie serii i zapis symbolu pozostawia ją na liście po powrocie, mimo że już nie spełnia filtru. Analogicznie wyczyszczenie symbolu pozostawia wiersz przy filtrze „Z super symbolem”. Sukces zapisu odświeża jedynie licznik, nie listę (`super-game-series-workspace.tsx:576`). Po zmianie symbolu unieważnić i pobrać listę z aktualnymi filtrami albo poprawnie usunąć wiersz niespełniający filtrów, zachowując spójność paginacji.

- [P0-3] `apps/admin/src/features/super-games/super-game-series-state.ts:208` — Akceptacja kolejnej strony sprawdza tylko filtr i kursor, bez identyfikatora przebiegu ładowania. Można rozpocząć „Wczytaj kolejne”, następnie odświeżyć listę i otrzymać nową pierwszą stronę z takim samym kursorem. Opóźniona odpowiedź sprzed odświeżenia zostanie dołączona do nowej listy. `loadMore` nie anuluje starego żądania, a dodatkowo bezwarunkowo ustawia jego `superGameState` (`super-game-series-workspace.tsx:482`). Powiązać odpowiedzi stron z generacją żądań zmienianą przy filtrach i odświeżeniu; odrzucać stare sukcesy i błędy przed aktualizacją listy oraz stanu świeżości.

### P1

- [P1-1] `apps/admin/test-interactions/super-game-series-workspace.test.mjs:322` — Test utrwala ignorowanie `0`, gdy katalog zawiera dziewięć zwykłych symboli i Mumię jako dziesiąty. Jest to przeciwieństwo przypadku wymaganego w `ai_docs/tasks/0934-super-game-admin-section.md:93`: `0` ma wybrać Mumię jako kandydata, a zapis ma zostać zablokowany. Nowa treść `ADMIN_APP.md:1684` opisuje mapowanie wyłącznie zwykłych symboli, więc dokumenty pozostają sprzeczne. Zgodnie z hierarchią źródeł pierwszeństwo mają wymagania, ale rozbieżność taska i zmiana oczekiwanego testu wymagają jawnego rozstrzygnięcia. Uzgodnić task, wymagania i testy oraz odnotować przyjętą decyzję lub założenie.

### P2

- [P2-1] `apps/admin/src/features/super-games/super-game-series-workspace.tsx:223` — Niepowodzenie pobrania symboli jest ignorowane. Widok pozostaje z pustym katalogiem, bez komunikatu i możliwości ponowienia; „Odśwież listę” nie pobiera symboli. Dodać jawny stan błędu katalogu oraz ponowienie albo odnotować ograniczenie jako zaakceptowane ryzyko.

- [P2-2] `apps/admin/src/features/super-games/super-game-series-workspace.tsx:1249` — Zdjęcie nie jest związane z `detail.view.revision`, choć nakładka wykorzystuje wielokąty z tego szczegółu. Zmiana geometrii pomiędzy odczytami może zestawić zdjęcie i oznaczenia z różnych rewizji. Istniejący modal przekazuje rewizję do tego samego wrappera (`packages/board-search-ui/src/board-search-board-lines-modal.tsx:816`). Po otrzymaniu szczegółu używać jego sumy kontrolnej i rewizji obrazu albo odnotować ryzyko niespójnej nakładki.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Lista stronicowana kursorem, działające filtry | niespełnione | `apps/admin/src/features/super-games/super-game-series-state.ts:208`, `apps/admin/src/features/super-games/super-game-series-state.ts:247`; P0-2 i P0-3 |
| Karuzela pokazuje wszystkie pozycje, w tym brakujące | spełnione | `apps/admin/src/features/super-games/super-game-series-state.ts:313`; dwadzieścia pozycji serii oraz dodatkowa karta wyzwalacza zgodnie z API |
| Sukces zapisu ustawia symbol, zachowuje oznaczenia; konflikt pokazuje aktualny stan | niespełnione | Podstawowa ścieżka CAS istnieje w `apps/admin/src/features/super-games/super-game-series-workspace.tsx:538`, ale odpowiedzi mogą zmienić niewłaściwy widok; P0-1 |
| Skróty nie działają w polach tekstowych i z modyfikatorami | spełnione | `apps/admin/src/features/super-games/super-game-series-keyboard.ts:40`, `apps/admin/src/features/super-games/super-game-series-keyboard.ts:59` |
| Gra `none` nie pokazuje zakładki | spełnione | `apps/admin/src/features/catalog/admin-navigation-state.ts:57`, `apps/admin/src/features/catalog/catalog-workspace.tsx:457` |

## Listy zamknięte i otwarte

Zamknięte (tylko w rundzie 2 lub później): Brak.

Otwarte: P0-1, P0-2, P0-3, P1-1, P2-1, P2-2.

## Proponowane testy

- W `apps/admin/test-interactions/super-game-series-workspace.test.mjs` dodać sterowane, opóźnione odpowiedzi zapisu A po otwarciu B: sukces, konflikt i błąd połączenia.
- W tym samym pliku sprawdzić powrót do listy po ustawieniu i wyczyszczeniu symbolu przy obu filtrach `defined`.
- W tym samym pliku sprawdzić odświeżenie listy podczas pobierania kolejnej strony, a następnie dostarczenie starej odpowiedzi z tym samym kursorem.
- W `apps/admin/test/super-game-series-state.test.mjs` dodać odrzucanie stron i błędów z poprzedniego przebiegu ładowania.
- Po rozstrzygnięciu P1-1 uzgodnić test `0` z obowiązującą mapą symboli.

Polecenia po poprawkach:

- Z katalogu głównego: `npm run test --workspace @game-predictor/admin`.
- Z `apps/admin`: `npx tsx --tsconfig tsconfig.json --test test-interactions/super-game-series-workspace.test.mjs`.

## Zakres przeglądu i ograniczenia

Przeczytano brief, task, odpowiednie fragmenty wymagań, kontraktu API, zaakceptowanego planu, decyzji i bieżącego stanu oraz kod i testy wskazane w briefie. Sprawdzono też istniejący modal i wrapper obrazu jako kontekst używanych kontraktów. Brief nie zawierał fragmentu planu; odczytano go z dokumentu wskazanego przez task.

Nie uruchamiano testów, serwerów ani poleceń zmieniających stan. Wyniki testów, lintowania i kontroli typów zapisane w `Outcome` są deklaracjami wykonawcy, nie wynikami niezależnej weryfikacji audytora. Nie zweryfikowano wyglądu CSS ani działania na rzeczywistym API. Zmiany poza ścieżkami TASK-0934 nie były przedmiotem audytu.