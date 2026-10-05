---
title: Symbol review save and queue performance
status: done
last_updated: 2026-10-05
---

# TASK-0852 — szybki zapis symboli i widok 2000 cropów

## Status

`done`

## Goal

Potwierdzony zapis 1–30 symboli oznacza pola jako zapisane bez ponownego pobrania miniatur; zamrożona strona mieści 2000 cropów i pozwala wybierać następne pola podczas zapisu.

## Context

Operator zgłosił 2–5 minut blokady po zapisie ośmiu Mumii i zażądał widoku 2000 zamiast 500. Kod ponownie składa całą kolejkę po zapisie, również przez zmianę `enabled`. Ograniczony odczyt istniejących danych: 30 cropów 2,059 s z profilerem; 50 etykiet 3,335 s. 500 cropów wymaga 17 odczytów, czasem dwóch serii przy zachowanym offset.

## Dependencies / entry conditions

- Gałąź feat/grid-engine-v3, HEAD v1.7.197 / 9916f7922d6045f7a7bb988151ae6122473c2d0c.
- TASK-0851 i jawna zgoda operatora na poprawę panelu. Bieżące decyzje człowieka są zachowywane.
- Zastane zmiany metadanych innych tasków pozostają poza commitem.

## Recommended execution

gpt-6.1-sol, high. Spójny pion wymaga API, klienta i odtwarzania CAS/receipt w UI. Własny osobny audyt; bez delegowania. Eskalacja przy niezgodności tożsamości bindingów lub bramek holdout.

## Relevant docs

- AGENTS.md
- ai_docs/README.md
- ai_docs/process/CURRENT_STATE.md
- ai_docs/process/PLAN_STANDARD.md
- ai_docs/process/TASK_TEMPLATE.md
- ai_docs/requirements/VISION_LAB.md
- ai_docs/architecture/VISION_LAB.md
- ai_docs/delivery/VISION_LAB_SYMBOL_LABELS_CONTRACT.md
- ai_docs/process/DEFINITION_OF_DONE.md

## Scope

- Istniejący lab_queue dopuszcza limit do 2000, domyślny 30 pozostaje. API przyjmuje jedną stronę; renderer czyta każde źródło raz. Łączna pula PNG ograniczona do 48 MiB przed dalszym renderowaniem; błąd nie zwraca części strony.
- Klient składa stronę 2000 jednym żądaniem. OpenAPI i klient generowane z backendu.
- Operator doprecyzował zamrożenie strony do jawnego odświeżenia. Po zgodnym, potwierdzonym label_cells_decide UI oznacza dokładnie zapisane bindingi jako „Zapisany” i przenosi rewizję CAS. Wszystkie obrazy zostają. Zapisane pola nie są ponownie wybieralne. Następne pola i klasę można wybierać podczas zapisu; kolejny zapis, gra, słownik i nawigacja czekają na potwierdzenie. Utrata odpowiedzi wymaga identycznego retry; następny wybór zachowany.
- Stary token strony nie staje się aktualnym tokenem. Nawigacja pobiera świeży pierwszy odczyt i jego token po lokalnym potwierdzeniu. Pełny odczyt/zmiana gry unieważnia pamięć panelu.
- Utracona odpowiedź zachowuje identyczne żądanie i blokadę; replay z inną rewizją lub nieważną decyzją wymaga ponownego odczytu. Żadne niepotwierdzone etykiety nie znikają.
- Stara lista etykiet ukryta do jawnego odczytu; inne workflowy pozostają zgodne. Zwalidowany grant wersji nie wykonuje drugi raz nieużywanego sprawdzenia historycznego splitu w queue.
- Otwarta cała plansza zachowuje snapshot bez konkurencyjnego odczytu po zapisie kolejki; jej edycja wymaga jawnego read. Kolejka pozostaje dostępna.

## Out of scope

Baza, migracje, etykiety testowe na danych użytkownika, trening, aktywacja, shadow, push/merge, nowe usługi i długotrwały cache danych.

## Acceptance criteria

- [x] Widok 2000 i ograniczony pojedynczy odczyt, bez osłabienia limitu zapisu 30.
- [x] Dwie kolejne partie bez ponownego pobierania poczekalni; zamrożone obrazy, wybór podczas zapisu i następna rewizja poprawne.
- [x] Retry po utracie odpowiedzi, drift i restart nie gubią decyzji i nie dopuszczają starego tokenu.
- [x] Holdout/wersja/renderowanie i dawny limit domyślny zachowane; regresje PASS.
- [x] Lint, typy, API/generowany klient, build i kontrolowany restart laboratoryjnego panelu PASS; odczytowe pomiary realnego zbioru zapisane. Stan człowieka niezmieniony przez weryfikację.
- [x] Dokumentacja, osobny audyt, Outcome i CURRENT_STATE aktualne. Osobny commit v1.7.198; hash dopisywany po commicie.

## Expected files

Istniejące: symbol_contracts.py (LabQueueRequest), symbol_crops.py (render_selected_bindings), symbol_store.py (validate_page/preview/queue_descriptors), packages/vision-lab-api-client/src/index.ts oraz OpenAPI/generowane typy, symbol-label-editor.tsx, symbol-candidate-queue.tsx, symbol-workflow.ts, symbol-queue-workflow.ts, odpowiadające testy i dokumenty Vision Lab. Harness workflow-interactions przypina app React dla renderera i współdzielonych komponentów; wykryto zastane dwie wersje React 19.2.3/19.2.8, uniemożliwiające uruchomienie testów.

## Test cases

Limit 2001 odrzucony; przekroczenie budżetu bez częściowego wyniku; domyślny 30; dwa zapisy na stronie zachowują niezapisane cropy; obcy request/rewizja/binding/receipt nie aktualizuje cache; przełączanie busy nie pobiera ponownie; świeży token przy nawigacji; utracona odpowiedź i retry; istniejące holdout i dataset-version testy.

## Verification

Istniejący runner run_step.py z absolutnymi ścieżkami, limity 60/120 s. Pytest test_vision_lab_symbol_labels/board/store/api/dataset_version; node test symbol-request i workflow-interactions; Ruff, scoped Mypy, TypeScript, OpenAPI drift i klient drift, Next build. Odczyty realnych cropów i checksumy przed/po restarcie; bez POST /symbols na danych użytkownika.

## Risks / open questions

2000 PNG zwiększa pamięć; limit 48 MiB danych PNG ogranicza odpowiedź bazową do 64 MiB plus metadane. Podgląd pozostaje atomowy. Pierwsze wczytanie wymaga renderowania; nie obiecujemy natychmiastowego odczytu. Niezapisane wybory przeglądarki wymagają ponownego wyboru po odświeżeniu strony.

## Outcome

### Changed

Addytywny podgląd 2000 w jednym żądaniu; PNG budget 48 MiB, domyślny limit 30 i writer 30 bez zmian. Zamrożona strona, receipt-confirmed oznaczenia, następny wybór podczas zapisu, CAS bez ponownego pobierania miniatur. Nawigacja otrzymuje świeży token; lost response zachowuje identyczny retry. D-497. Po zapisie kolejki listy etykiet/przypisań wymagają jawnego odczytu; pozostałe mutacje zachowują pełny reload.

### Verification results

73 Python + 37 UI + 5 klienta: PASS. Ruff/Prettier/ESLint/scoped Mypy/UI i client TypeScript/OpenAPI/drift/build PASS. Odczyt 2000 realnych cropów 5,464 s / 32,34 MiB base64. Restart z trwałej konfiguracji: API 18980, UI 18320, oba ready. Sumy symboli i geometrii identyczne przed/po. Browser: 2000 kafelków, 64 loaded/enabled, zero błędów; brak zapisu etykiet przez agenta. Pomocniczy wrapper końcowego restartu osiągnął timeout przez odziedziczoną rurę stdout; własny wrapper zakończony, usługi ready zweryfikowane osobno, pliki bez zmian. Helper zapisuje teraz stdout do plików. Własny osobny audyt DoD i kryteriów: PASS, bez P0–P2. Szczegóły i limity pomiarów w raporcie.

### Not completed

Bez DB/migracji/treningu/aktywacji/shadow/push/merge. Nie zmierzono zapisu na danych użytkownika ani restartu komputera. Pierwsze renderowanie nadal wymaga kilku sekund; niepotwierdzony zapis wymaga retry/read. Zastane ostrzeżenie Next o dwóch lockfiles pozostaje poza zakresem. Zastane metadane innych tasków nie są częścią commita.

### Documentation updates

Wymagania, architektura i kontrakt Vision Lab, D-497, CURRENT_STATE, raport ai_docs/quality/SYMBOL_REVIEW_PERFORMANCE_20261005.md. Task przeniesiony do completed. Commit: v1.7.198 — pełny hash dopisany po commicie.

### Recommended next task

Operator odświeża stronę raz po potwierdzeniu ewentualnego starego zapisu i kontynuuje wybór klas. Uczenie symboli wymaga osobnego etapu z istniejącymi bramkami pochodzenia i podziału danych.

## Przypisanie modeli do zadań

| Zadanie | Model | Reasoning | Uzasadnienie | Dodatkowy review |
|---|---|---|---|---|
| TASK-0852 | gpt-6.1-sol | high | Atomowy odczyt i bezpieczne potwierdzenie zapisu w istniejącym kontrakcie | Własny osobny audyt; bez delegowania |
