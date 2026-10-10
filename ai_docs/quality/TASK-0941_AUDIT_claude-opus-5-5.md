# Audyt TASK-0941 — Kompaktowe punkty i maszyny z nawigacją w głąb

Werdykt: REVISE
Audytor: claude-opus-5-5, medium
Wykonawca: gpt-6-sol, medium
Zakres: 0625512d...0625512d4a37072f1d6d44f3f85ef225e7db1835 oraz zmiany niezacommitowane (snapshot `artifacts/audits/TASK-0941_STAGE/audit-source` z naniesioną korektą CSS), data 2026-10-09
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Zbadano wspólny workspace zarządzania, nowy moduł nawigacji URL i modal struktury, zmiany w operacjach oczekujących, sygnał anulowania nawigacji zewnętrznej w katalogu Admina, CSS z korektą geometrii oraz zmienione testy. Hierarchia punkt → maszyna → gra, parametry URL, podgląd przed usunięciem i atomowy zapis maszyny są zrobione zgodnie z planem. Ochrona przed równoczesną edycją (CAS) i ochrona szkicu mają jednak luki. Odświeżenie snapshotu podmienia rewizję w otwartym modalu, przez co zapis nadpisuje zmiany z innego okna. Brudny modal nie jest zgłaszany do zewnętrznego guardu Admina. Efekty odzyskiwania operacji oczekującej po każdym odświeżeniu nadpisują wybór użytkownika bez guardu. Brakuje też części testów wymaganych w sekcji Test cases.

## Znaleziska

### P0

Brak.

### P1

- [P1-1] `packages/board-search-ui/src/management/management-workspace.tsx:154-174` (używane w `:543` i `:558`) — `load()` przy każdym odświeżeniu (focus, `load(true)` po błędzie lub konflikcie) podmienia `editor.point` i `editor.machine` na świeży rekord. `save()` bierze `expectedRevision` właśnie z tego rekordu. Scenariusz: modal jest otwarty, w innym oknie ktoś zmienia nazwę, użytkownik wraca (focus), a jego zapis przechodzi z nową rewizją i nadpisuje cudzą zmianę bez konfliktu. Po 409 kolejny „Zapisz” też omija CAS. To łamie regułę planu „Zmiana z innego okna unieważnia preview zamiast kasować nowy stan” i kryterium „error/CAS zachowuje draft”. Poprawka: zapamiętać rewizję i bazowe przypisania w chwili `openEditor`, np. w polu `baseRevision` edytora albo w refie, i nie odświeżać ich w `setEditor`. Gdy świeży snapshot ma inną rewizję, pokazać konflikt i wymagać jawnego przeładowania formularza. Do tego test: modal otwarty → focus z nową rewizją → zapis używa starej rewizji i dostaje 409.
- [P1-2] `packages/board-search-ui/src/management/management-workspace.tsx:118-127` oraz `apps/admin/src/features/catalog/catalog-workspace.tsx:179-182` — o brudnym modalu wie tylko lokalne `navigationAllowed()`. `onDirtyChange` nie dostaje tej informacji, więc `managementDirty` w katalogu Admina pozostaje `false`. Kliknięcie innego workspace Admina albo zewnętrzny popstate porzuca wpisaną nazwę lub gry bez pytania. Lokalny `onPop` może wtedy zapytać dopiero po zmianie workspace, a odmowa i tak nie zatrzymuje odmontowania. To łamie zakres „Dirty guards wszystkich wyjść” i kryterium ochrony szkicu. Poprawka: wyliczać `modalDirty` i wywoływać `onDirtyChange(draftDirty || modalDirty)` przy każdej zmianie pól i przy otwarciu lub zamknięciu modala. Test w `apps/admin/test-interactions/management-cards.test.mjs`: brudny modal → kliknięcie innego workspace i popstate → jeden prompt, modal zachowany.
- [P1-3] `packages/board-search-ui/src/management/management-workspace.tsx:341-368` i `:370-411` — oba efekty odzyskiwania (operacja strukturalna i operacja slotu) uruchamiają się przy każdej zmianie `snapshot` i bezwarunkowo ustawiają lokalizację przez `replaceState`, bez `navigationAllowed()`. Ponieważ `navigate()` do poziomu bez maszyny wywołuje `load()` (`:250`), przy istniejącej operacji oczekującej „Punkty”/„Cofnij” natychmiast wraca do zakresu tej operacji, czyli powstaje pułapka nawigacyjna. Efekt strukturalny ustawia też `gameId: null` (`:356`). To odmontowuje `ManagementGameWorkspace` z brudnym szkicem stawki bez potwierdzenia, a dwa efekty walczą o `gameId`. Task wprost wymaga: „Restore zakresu służy odzyskiwaniu, nie zastępuje wyboru URL innymi danymi bez guardu”. Poprawka: odzyskiwać zakres jednokrotnie (flaga w refie po pierwszym snapshocie dla danej operacji lub namespace), z guardem szkicu, i nie zerować `gameId`, gdy bieżąca maszyna jest zgodna. Test: operacja oczekująca → „Punkty” → focus → lokalizacja pozostaje na liście punktów.
- [P1-4] `apps/admin/test-interactions/management.test.mjs:279-442`, `packages/board-search-ui/test-interactions/management-navigation.test.mjs:1-60` — brakuje testów z sekcji Test cases taska. Nie ma testu zmiany publicznej sesji lub namespace z operacją oczekującą („stara operacja nie przechodzi do nowej sesji”). Usunięcia w drugim oknie na poziomie komponentu (focus → `replaceState` do rodzica) też nie ma; jest tylko czysta funkcja. Brak również asercji reguł siatki (4/3/2/1, `max-width` 320 px, przyciski kontrolne 44 px) dla 1/4/40 kafelków, choćby statycznie na CSS, oraz testu, że `mpStake` z URL nie otwiera edytora. To naruszenie DoD („Nowe moduły muszą dostać własne testy”, Test cases). Poprawka: dodać te przypadki do istniejących suite'ów Admin/Reviewer lub board-search-ui; pomiar w prawdziwej przeglądarce może zostać w TASK-0943.

### P2

- [P2-1] `packages/board-search-ui/src/management/management-workspace.tsx:517-520` w połączeniu z `services/api/src/game_predictor_api/storage/management_repository.py:397-416,435-437` — początkowe `gameIds` modala zawierają też wiersze legacy `attached=false`. Sama zmiana nazwy maszyny po cichu ponownie dołącza odłączoną grę aktywną (`row.attached = True`). Jeśli odłączona gra jest nieaktywna, zapis kończy się błędem `MANAGEMENT_GAME_NOT_ACTIVE`, więc maszyny nie da się przemianować bez odpięcia, które czyści historię. Propozycja: jawny opis skutku w modalu i wpis decyzji. Ewentualnie zmiana kontraktu w osobnym tasku.
- [P2-2] `packages/board-search-ui/src/management/management-structure-modal.tsx:105-128` — odłączony wiersz gry nadal aktywnej w katalogu pojawia się dwa razy: w `activeGames` i w sekcji legacy. Dwa checkboxy sterują tym samym `gameId`, co może mylić. Propozycja: w sekcji legacy pominąć `gameId` obecne w `activeGames` albo oznaczyć stan na pojedynczym wierszu.
- [P2-3] `packages/board-search-ui/src/management/management-workspace.tsx:268-292` i `apps/admin/src/features/catalog/catalog-workspace.tsx:193-196` — działanie zależy od kolejności listenerów `popstate`. Listener panelu jest rejestrowany ponownie przy każdej zmianie zależności. Gdy katalog zaakceptuje wyjście z workspace z głębszego poziomu, lokalny `onPop` może wyświetlić drugi dialog, bo `draftDirty` nie został wyczyszczony. Gdy zdarzenie anulowania przyjdzie po lokalnym handlerze, flaga `outerNavigationCancelled` zostaje i połyka następny popstate. Propozycja: czyścić flagę w mikrotasku lub porównywać z parametrem `workspace`, a w panelu ignorować popstate zmieniający `workspace`.
- [P2-4] `packages/board-search-ui/src/management/management-workspace.tsx:841` i `:919` — tekst `🗑` ma wcięcie niezgodne z Prettierem, co podważa deklarację „Prettier zmienionych plików: PASS” i grozi błędem `format:check`. Dodatkowo pełne `@game-predictor/admin test:geometry` (171) uruchomiono przed ostatnim testem i wydzieleniem modala, a korekty CSS nie objął żaden przebieg testów. Propozycja: przed commitem uruchomić Prettier na pliku i pełne suite'y z sekcji Verification.
- [P2-5] `packages/board-search-ui/src/management/management.css:161-163,175-179` — `container-type: inline-size` na `.management-workspace`, w którym renderuje się modal `position: fixed`, oraz `max-width: min(100%, 320px)` dla wszystkich `input`/`select` w workspace. Pole nazwy w modalu szerokości 560 px zostaje więc zwężone do 320 px, a pozycjonowanie modala zależy od implementacji containment w przeglądarce. Propozycja: ograniczyć regułę 320 px do kafelków i sprawdzić centrowanie modala w odbiorze TASK-0943 (390/1440/1920 px).

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Tile nie rozciąga się; 4/3/2/1 kolumn; brak przewijania w poziomie przy 390 px | niezweryfikowane | Reguły w `management.css:1-15,146-163,175-179` są poprawne, ale brak testu ani pomiaru (P1-4, P2-5); pomiar w TASK-0943 |
| Home i Cofnij działają, zaznaczenie maszyny/stawki, ikony nie wybierają kafelka | spełnione częściowo | `management-workspace.tsx:728-771,809-843` (rodzeństwo przycisków); `management-cards.tsx` `data-selected`; Home zablokowany przy operacji oczekującej (P1-3) |
| Modal zapisuje name+games jednym żądaniem; błąd/CAS zachowuje szkic i wymaga świeżego preview | niespełnione | Jedno żądanie i zachowanie szkicu: `management-workspace.tsx:535-599`, test `management.test.mjs:300-358`; CAS omijany przez odświeżenie edytora (P1-1) |
| Reload/URL/popstate odtwarzają najbliższy poprawny poziom, mpStake nie otwiera edytora, parametry rodzica zachowane | spełnione częściowo | `management-navigation.ts:20-68`, test `management-navigation.test.mjs`; odzyskiwanie nadpisuje URL bez guardu (P1-3); brak testu komponentu dla mpStake (P1-4) |
| Pending scope i stara sesja nie przechodzą na innego aktora; recovery bez autoretry | niezweryfikowane | Klucze z namespace `management-operation.ts`, `management-workspace.tsx:327-339`; brak autoretry potwierdzony testem `management.test.mjs:360-398`; brak testu zmiany sesji (P1-4) |
| Focus/back/zapis/notfound/conflict odświeżają snapshot; usunięcie w innym oknie nie zostawia aktywnego celu | spełnione częściowo | `management-workspace.tsx:175-187,212-218,482,491`; brak testu komponentu (P1-4) |
| Dirty draft chroniony na Home/back/popstate/game/zamknięcie modala; legacy archived usuwalne, archiwizacja niewidoczna | niespełnione | Lokalne guardy: test `management.test.mjs:400-442`; wyjścia zewnętrzne nie widzą brudnego modala (P1-2); efekty odzyskiwania odmontowują szkic (P1-3); archiwalne sekcje `:848-867,925-950` spełnione |
| Admin i Reviewer używają tego samego UI; link controls tylko lokalnie | spełnione | Wspólny `ManagementWorkspace`, `headerActions` w nagłówku `:772`; testy Reviewer `management-panel.test.mjs` |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P1-1, P1-2, P1-3, P1-4, P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- Modal otwarty → snapshot z wyższą rewizją przez focus → „Zapisz” wysyła pierwotną `expectedRevision`, a przy 409 szkic zostaje (`apps/admin/test-interactions/management.test.mjs`, `npm run test:geometry --workspace @game-predictor/admin`).
- Brudny modal + kliknięcie innego workspace Admina i zewnętrzny popstate → dokładnie jeden prompt, modal zachowany (`apps/admin/test-interactions/management-cards.test.mjs`).
- Operacja strukturalna lub slotu oczekująca → „Punkty” → focus → lokalizacja pozostaje; brudny szkic stawki nie jest odmontowany bez potwierdzenia.
- Zmiana `storageNamespace` lub sesji publicznej z zapisaną operacją → brak przycisku ponowienia w nowej sesji (`apps/reviewer/test-interactions/management-panel.test.mjs`, `npm run test:geometry --workspace @game-predictor/reviewer`).
- Usunięcie punktu lub maszyny w „innym oknie” (snapshot bez obiektu) → focus → `replaceState` do najbliższego rodzica, bez komunikatu błędu.
- `?mpStake=120` przy reloadzie → stawka oznaczona, edytor zamknięty.
- Statyczna asercja reguł CSS siatki dla 1/4/40 kafelków (np. w `packages/board-search-ui/test-interactions`).

## Zakres przeglądu i ograniczenia

Przeczytano z snapshotu audytu pełne `management-workspace.tsx` i `management.css` (z korektą CSS) oraz fragment `catalog-workspace.tsx:150-219`. Z briefu przeczytano diffy i nowe pliki `management-navigation.ts`, `management-structure-modal.tsx`, test nawigacji, zmiany w `management-operation.ts`, `management-game-workspace.tsx`, `management-cards.tsx` i testach Admin/Reviewer. Kontekst backendu sprawdzono w `services/api/src/game_predictor_api/storage/management_repository.py:385-442`. Nie uruchamiano testów, lintu, typechecku, Prettiera ani przeglądarki. Wyniki testów wykonawcy przyjęto jako deklarowane dowody. Nie czytano pełnych `CURRENT_STATE.md` ani `DECISION_LOG.md`. Zachowania CSS (containment, pozycjonowanie modala, szerokości 390/1440/1920 px) nie da się rozstrzygnąć statycznie.
