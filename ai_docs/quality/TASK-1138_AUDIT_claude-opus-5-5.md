# Audyt TASK-1138 — Widoczne odświeżanie stanu uczenia

Werdykt: PASS
Audytor: claude-opus-5-5, reasoning high
Wykonawca: gpt-6.1-sol, reasoning high
Zakres: HEAD...fa38a3cdedf4aa9f85cf62df0512330788f8dd6c oraz zmiany niezacommitowane, data 2026-11-03
Runda: 1

Przegląd statyczny. Audytor nie zmieniał żadnych plików.

## Streszczenie

Przejrzałem przebudowane `Learning.refresh` i `open` w panelu uczenia siatek, przycisk odświeżania z jego potwierdzeniem, pięć nowych testów interakcji oraz wpisy w ADMIN_APP, VISION_LAB i CURRENT_STATE. Zmiana spełnia cel taska. Sześć GET przyjmuje wyniki niezależnie przez `allSettled`. Przycisk ma własny stan `refreshing`, `aria-busy` i synchroniczną blokadę. Token `readSequence` poprawnie odrzuca spóźnione odpowiedzi po nowym odczycie i po unmount. Nie ma POST ani automatycznego replay komend. Zostają drobne ryzyka: przejściowe stany pośrednie, które powstały, bo odczyty kończą się teraz w różnym czasie, oraz luki w testach. Żadne z nich nie łamie kryterium akceptacji.

## Znaleziska

### P0

Brak.

### P1

Brak.

### P2

- [P2-1] `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:390` — Etykieta „Wspólny model” zależy tylko od `loading`. Ta flaga zmienia się teraz wyłącznie po odczycie gotowości (linie 134–136). Jeśli przy wejściu gotowość wróci przed `getGridModelDefault`, panel pokaże „Nie udało się ustalić wersji”, choć model domyślny jest jeszcze w drodze. Przy `Promise.all` taki stan nie występował. Skutek: chwilowo fałszywy komunikat o błędzie. Poprawka: przy `defaults === null` pokazywać „Wczytywanie…” także wtedy, gdy `refreshing` jest true, np. `loading || (refreshing && defaults === null)`.
- [P2-2] `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:116` — Każdy refresh podbija `generation`, więc unieważnia trwające jawne `open(B)` operatora. Odczyt B wznawia tylko handler listy (linie 150–154), przez `chosen.current`. Scenariusz: operator klika przebieg B, a potem „Odśwież stan uczenia”, zanim B się wczyta, a GET listy kończy się błędem. Wtedy `chosen` wskazuje B, raport jest wyczyszczony (linia 194), a widoczny `selected` nadal pokazuje A. Stan sam się naprawia przy kolejnym odczycie. Poprawka: w gałęzi błędu listy ponowić `open(chosen.current)`, gdy różni się od `selected`. Można też zaakceptować ryzyko i je odnotować.
- [P2-3] `apps/admin/src/features/model-quality/grid-correction-learning-panel.tsx:194` — Raport oceny zostaje teraz przy ponownym odczycie tego samego `learningId`. Gdy przebieg dostanie nowe `evaluationId` (np. po wznowieniu), a GET raportu się nie powiedzie (linie 216–225), pod nowym stanem przebiegu nadal widać stary raport, obok samego alertu. Raport tylko się wyświetla, a `GridCorrectionApplyPanel` korzysta z `selected` (linie 733–745), więc to nie jest błąd bramki publikacji. Poprawka: zachowywać `evaluation` tylko wtedy, gdy jego `evaluationId` jest równe `result.data.evaluationId`, a w innym razie czyścić przed odczytem raportu.
- [P2-4] `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:245` — Drugie kliknięcie trafia w przycisk już wyłączony. W JSDOM `click()` na wyłączonym przycisku nie wywołuje `onClick`, więc test sprawdza `disabled`, a nie synchroniczną blokadę `refreshInFlight` (`grid-correction-learning-panel.tsx:453`). Skutek: usunięcie tej blokady nie wywróci żadnego testu. Poprawka: wywołać dwa kliknięcia w jednym `act`, zanim React przerenderuje przycisk, albo wysłać zdarzenie wprost do handlera i sprawdzić, że `reads` równa się 2.
- [P2-5] `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs:267` — Test błędu gotowości sprawdza, że `RETAINED_WORKFLOW` zostaje. Ta wartość pochodzi jednak już z pierwszego odczytu, a lista i status przy drugim odczycie są takie same. Test nie dowodzi więc, że błąd gotowości nie blokuje świeżego stanu przebiegu w tym samym odczycie. Poprawka: przy drugim odczycie zwracać inny `errorCode` (np. `FRESH_AFTER_FAILURE`) i sprawdzić go razem z komunikatem błędu.

## Pokrycie kryteriów akceptacji

| Kryterium | Status (spełnione / niespełnione / niezweryfikowane) | Dowód (`ścieżka:linia` lub wynik polecenia) |
|---|---|---|
| Przycisk natychmiast zmienia etykietę, disabled i aria-busy; podwójne kliknięcie nie tworzy drugiego zestawu odczytów | spełnione | `grid-correction-learning-panel.tsx:116-118`, `:447-458`; test `grid-correction-learning-panel.test.mjs:210-265` (blokada ref nie jest pokryta testem, P2-4) |
| Wolna/błędna gotowość nie blokuje historii i świeżego stanu wybranego przebiegu | spełnione | `grid-correction-learning-panel.tsx:122-179`; testy `:177-208`, `:210-265`; świeży stan przy błędzie gotowości nie jest pokryty testem (P2-5) |
| Po sukcesie widoczne potwierdzenie; po błędzie przycisk ponownie dostępny i dane zachowane | spełnione | `grid-correction-learning-panel.tsx:180-190`, `:459-463`; test `grid-correction-learning-panel.test.mjs:267-299` |
| Stare odpowiedzi/unmount nie nadpisują nowych odczytów i wyboru; komendy bez automatycznego replay | spełnione | `grid-correction-learning-panel.tsx:120`, `:126`, `:180`, `:247-251`, `:150-154`; testy `:301-342`, `:344-412`, `:699-733`; wszystkie nowe testy sprawdzają, że wywołania to tylko `get`/`list` |
| Testy interakcji, lint/typecheck, build, docs/map i Opus; task-close i osobny commit | niezweryfikowane | `artifacts/task1138-interactions-final.log` (44 pass, 0 fail); końcówka `artifacts/task1138-admin-build-final.log` kończy się poprawnie; diff CODE_MAP/CODE_MAP_SYMBOLS zawiera tylko końce linii; lint, typecheck i docs:check deklaruje wykonawca; task-close i commit jeszcze nie wykonane |

## Listy zamknięte i otwarte

Zamknięte: nie dotyczy (runda 1).

Otwarte: P2-1, P2-2, P2-3, P2-4, P2-5.

## Proponowane testy

- `apps/admin/test-interactions/grid-correction-learning-panel.test.mjs`: odroczone `getGridModelDefault` przy szybkiej gotowości. Przed rozwiązaniem nie może się pojawić „Nie udało się ustalić wersji” (P2-1). Komenda: `npm run test:interactions --workspace @game-predictor/admin` albo odpowiadający skrypt interakcji Admina.
- Ten sam plik: wybór innego przebiegu, zanim przyjdzie odroczona odpowiedź listy z ręcznego odświeżenia. Spóźniona lista ma otworzyć wybrany przebieg, a nie pierwszy. Wariant: lista kończy się błędem po kliknięciu wyboru (P2-2).
- Ten sam plik: dwa kliknięcia odświeżania w jednym `act`, żeby pokryć synchroniczną blokadę (P2-4), oraz zmieniony `errorCode` przy błędzie gotowości (P2-5).

## Zakres przeglądu i ograniczenia

Przeczytałem w całości brief, task, plik `grid-correction-learning-panel.tsx` oraz w testach fixture, helpery, pięć nowych testów i istniejący test późnej odpowiedzi przy jawnym wyborze. Przejrzałem log 44 testów interakcji, końcówkę logu builda i diff CODE_MAP/CODE_MAP_SYMBOLS, który zawiera tylko końce linii. Wpisy w ADMIN_APP, VISION_LAB i CURRENT_STATE przejrzałem w diffie z briefu. Nie uruchamiałem testów, lint, typecheck, builda ani `docs:check`. Wyniki tych kroków i weryfikację na rzeczywistym Adminie przyjmuję z deklaracji wykonawcy. Nie sprawdzałem `AGENTS.md` pod kątem kolejności zamknięcia taska, bo task-close i commit są dopiero przed nami. Plan nie został dołączony do briefu.
